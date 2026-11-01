"""The download queue: runs up to N jobs at once, retries failed playlist items, keeps the history."""
import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import replace

import engine
import model
import winutil

AUTO_RETRIES = 2          # extra passes over the failed items of a playlist, so each one is tried 3 times in all
HISTORY_MAX = 500


def _move_into(path, work, out_dir):
    """Moves a finished file from the work folder into the save folder, never overwriting a file already there."""
    dest = os.path.join(out_dir, os.path.relpath(path, work))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    stem, ext = os.path.splitext(dest)
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = f"{stem} ({n}){ext}"
    shutil.move(path, dest)
    return dest


class Job:
    def __init__(self, spec, merge_into=None):
        self.id = uuid.uuid4().hex[:12]
        self.url = spec["url"]
        self.title = spec.get("title") or self.url
        self.thumb = spec.get("thumb")
        self.site = spec.get("site") or ""
        self.options = dict(spec["options"])
        self.summary = spec.get("summary") or ""
        self.info_file = spec.get("info_file")
        self.total = int(spec.get("playlist_total") or 0)
        self.entry_titles = {int(k): v for k, v in (spec.get("entry_titles") or {}).items()}
        self.merge_into = merge_into          # history entry that a "retry failed items" run updates
        self.status = "waiting"               # waiting | running | failed | canceled
        self.progress = None
        self.phase = None                     # e.g. "Retrying 2 failed items…"
        self.error = None
        self.proc = None
        self.cancelled = False

    def to_dict(self):
        return {"id": self.id, "title": self.title, "thumb": self.thumb, "site": self.site, "summary": self.summary, "url": self.url,
                "status": self.status, "progress": self.progress, "phase": self.phase, "error": self.error, "mode": self.options.get("mode"),
                "merge_into": self.merge_into}


class Manager:
    def __init__(self, prefs):
        self.prefs = prefs
        self._lock = threading.RLock()
        self._queue = []
        self._history = []
        self._finished = 0
        self._file = engine.data_dir() / "history.json"
        try:
            self._history = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    # ---- queue
    def add(self, specs):
        with self._lock:
            jobs = [Job(s) for s in specs]
            self._queue += jobs
        self.pump()
        return [j.id for j in jobs]

    def pump(self):
        """Starts waiting jobs until the simultaneous-download limit is reached."""
        with self._lock:
            running = sum(j.status == "running" for j in self._queue)
            for j in self._queue:
                if running >= max(1, int(self.prefs.get("simul"))):
                    break
                if j.status == "waiting":
                    j.status = "running"
                    running += 1
                    threading.Thread(target=self._run, args=(j,), daemon=True).start()

    def remove(self, job_id):
        with self._lock:
            j = next((x for x in self._queue if x.id == job_id), None)
            if not j:
                return
            if j.status == "running":
                j.cancelled = True
                if j.proc:
                    engine.kill_tree(j.proc)
            else:
                j.status = "canceled"
                self._queue.remove(j)

    def retry(self, job_id):
        with self._lock:
            j = next((x for x in self._queue if x.id == job_id and x.status == "failed"), None)
            if j:
                j.status, j.error, j.progress, j.phase = "waiting", None, None, None
        self.pump()

    def cancel_all(self):
        for j in list(self._queue):
            self.remove(j.id)

    # ---- running one job
    def _out_dir(self, mode):
        d = self.prefs.get({"video": "dir_video", "audio": "dir_audio", "gif": "dir_gif"}[mode])
        os.makedirs(d, exist_ok=True)
        return d

    def _options(self, job):
        o = model.Options.from_dict(job.options)
        p = self.prefs
        return replace(o, fragments=int(p.get("fragments")), retries=int(p.get("retries")), rate_limit=(p.get("rate_limit") or None),
                       proxy=(p.get("proxy") or None), force_ipv4=bool(p.get("force_ipv4")))

    def _run(self, job):
        try:
            result = self._download(job)
        except engine.EngineError as e:
            result = {"error": str(e)}
        except Exception as e:  # never let a thread die silently
            result = {"error": model.friendly_error("ERROR: " + str(e))}
        with self._lock:
            if job.cancelled:
                job.status = "canceled"
                self._queue.remove(job)
            elif "error" in result:
                job.status, job.error = "failed", result["error"]
            else:
                self._queue.remove(job)
                self._finish(job, result)
        self.pump()

    def _download(self, job):
        o = self._options(job)
        out_dir = self._out_dir(o.mode)

        def on_progress(p):
            job.progress = p

        def on_proc(proc):
            job.proc = proc
            if job.cancelled:
                engine.kill_tree(proc)

        # A cut (trim or GIF) is made in a private folder first: if the full video is already in the save folder,
        # yt-dlp would reuse that file and ignore the cut. The result is moved into place afterwards.
        work = engine.data_dir() / "work" / job.id if (o.trim or o.mode == "gif") else None
        res = engine.run_download(job.url, o, str(work) if work else out_dir, on_progress, on_proc, job.info_file)
        if work:
            for f in res["files"]:
                f["path"] = _move_into(f["path"], str(work), out_dir)
            shutil.rmtree(work, ignore_errors=True)
        files = {f["path"]: f for f in res["files"]}
        errors = dict(res["errors"])
        selection = []
        if o.playlist:
            total = job.total
            selection = list(o.items) if o.items else model.playlist_selection(total, o.range_from, o.range_to) if total else []
        failed = model.failed_items(selection, [f["index"] for f in files.values()]) if selection else []
        attempt = 0
        while failed and attempt < AUTO_RETRIES and not job.cancelled:
            attempt += 1
            job.phase = f"Retrying {len(failed)} failed item{'s' if len(failed) != 1 else ''}… (attempt {attempt + 1} of {AUTO_RETRIES + 1})"
            job.progress = None
            again = engine.run_download(job.url, replace(o, items=failed), out_dir, on_progress, on_proc)
            for f in again["files"]:
                files[f["path"]] = f
            errors.update(again["errors"])
            failed = model.failed_items(selection, [f["index"] for f in files.values()])
        job.phase = None
        if job.cancelled:
            return {}
        if not files:
            if o.playlist and not selection and not res["tail"]:
                return {"error": "Download failed"}
            return {"error": model.friendly_error(res["tail"])}
        if not o.playlist and res["code"] != 0:
            return {"error": model.friendly_error(res["tail"])}
        return {"files": list(files.values()), "failed": [
            {"index": i, "title": job.entry_titles.get(i) or f"Item {i}", "reason": errors.get(i) or "Download failed"} for i in failed],
            "attempts": attempt + 1}

    def _finish(self, job, result):
        saved = [{"path": f["path"], "name": os.path.basename(f["path"]), "size": os.path.getsize(f["path"]) if os.path.exists(f["path"]) else 0}
                 for f in sorted(result["files"], key=lambda f: f["path"])]
        if job.merge_into:
            entry = next((h for h in self._history if h["id"] == job.merge_into), None)
            if entry:
                have = {f["path"] for f in entry["files"]}
                entry["files"] += [f for f in saved if f["path"] not in have]
                entry["failed"] = result["failed"]
                entry["date"] = int(time.time() * 1000)
                self._save()
                self._notify_idle(job, entry)
                return
        entry = {"id": job.id, "title": job.title, "thumb": job.thumb, "site": job.site, "summary": job.summary, "date": int(time.time() * 1000),
                 "url": job.url, "mode": job.options.get("mode"), "options": job.options, "files": saved, "failed": result["failed"],
                 "total": job.total, "entry_titles": job.entry_titles}
        self._history.insert(0, entry)
        del self._history[HISTORY_MAX:]
        self._save()
        self._notify_idle(job, entry)

    def _notify_idle(self, job, entry):
        self._finished += 1
        if any(j.status in ("waiting", "running") for j in self._queue):
            return
        n, self._finished = self._finished, 0
        if self.prefs.get("notify"):
            bad = len(entry["failed"])
            text = f"{n} downloads finished" if n > 1 else (f"{len(entry['files'])} saved, {bad} failed" if bad else "Download finished")
            files = [f["path"] for f in entry["files"]]
            target = files[0] if n == 1 and len(files) == 1 else (os.path.dirname(files[0]) if files else None)   # click: open the file, else its folder
            winutil.notify(entry["title"] if n == 1 else winutil.APP_NAME, text, target)

    # ---- history
    def retry_failed(self, history_id):
        """Re-runs only the failed items of a finished playlist; the history entry is updated when it ends."""
        with self._lock:
            e = next((h for h in self._history if h["id"] == history_id), None)
            if not e or not e["failed"]:
                return None
            items = [f["index"] for f in e["failed"]]
            opts = dict(e["options"], playlist=True, items=items)
            spec = {"url": e["url"], "title": e["title"], "thumb": e["thumb"], "site": e["site"], "summary": e["summary"], "options": opts,
                    "playlist_total": e["total"], "entry_titles": e.get("entry_titles") or {}}
            job = Job(spec, merge_into=history_id)
            self._queue.append(job)
        self.pump()
        return job.id

    def delete_files(self, history_id):
        """Moves the files to the Recycle Bin and drops the entry. Returns False if Windows refused."""
        with self._lock:
            e = next((h for h in self._history if h["id"] == history_id), None)
            if not e:
                return True
            ok = winutil.recycle([f["path"] for f in e["files"]])
            self._history.remove(e)
            self._save()
            return ok

    def clear_history(self):
        with self._lock:
            self._history.clear()
            self._save()

    def history_entry(self, history_id):
        with self._lock:
            return next((h for h in self._history if h["id"] == history_id), None)

    def _save(self):
        self._file.write_text(json.dumps(self._history), encoding="utf-8")

    def state(self):
        with self._lock:
            return {"jobs": [j.to_dict() for j in self._queue], "history": list(self._history), "simul": int(self.prefs.get("simul"))}
