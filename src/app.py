"""Media MultiTool Desktop: window, the API the page calls, and a dev-only HTTP bridge for testing the UI in a browser.

    python app.py              the app
    python app.py --dev 5190   serve the UI and API on 127.0.0.1:5190 (no window), for browser testing
"""
import json
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import engine
import jobs
import prefs as prefs_mod
import winutil

APP_VERSION = "1.1.0"
UI = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "ui"


class Api:
    """Everything the page can call. Public methods are exposed to JavaScript, so internals start with an underscore."""

    def __init__(self):
        self._window = None
        self._prefs = prefs_mod.Prefs()
        self._jobs = jobs.Manager(self._prefs)
        self._setup = {"running": False, "text": "", "fraction": 0.0, "error": None}

    # ---- start up
    def boot(self):
        st = engine.tool_status()
        threading.Thread(target=self._daily_update, daemon=True).start()
        return {"prefs": self._prefs.all(), "tools": {"ready": st["ready"], "missing": st["missing"]}, "app_version": APP_VERSION}

    def _daily_update(self):
        import time
        if not engine.tool_status()["paths"]["yt-dlp"] or time.time() - self._prefs.get("last_update") < 86400:
            return
        try:
            engine.update_ytdlp(self._prefs.get("nightly"))
        finally:
            self._prefs.set("last_update", time.time())

    def setup_tools(self):
        """Downloads yt-dlp, ffmpeg and Deno into the app's folder. Only called after the user presses the button."""
        if self._setup["running"]:
            return
        self._setup.update(running=True, error=None, text="Starting…", fraction=0.0)

        def work():
            try:
                engine.setup_tools(engine.tool_status()["missing"], lambda t, f: self._setup.update(text=t, fraction=f))
            except Exception as e:
                self._setup["error"] = f"Couldn't download the tools: {e}"
            self._setup["running"] = False
        threading.Thread(target=work, daemon=True).start()

    def setup_status(self):
        return dict(self._setup, ready=engine.tool_status()["ready"])

    # ---- links
    def clipboard_links(self):
        return self.links(winutil.clipboard_text())

    def links(self, text):
        """All the links in a pasted block, one per line or separated by spaces."""
        out = []
        for tok in re.split(r"[\s,]+", text or ""):
            u = engine.find_url(tok)
            if u and u not in out:
                out.append(u)
        return out

    def preview(self, url):
        try:
            return engine.preview(url)
        except Exception:
            return None

    def info(self, url):
        try:
            return {"media": engine.get_info(url)}
        except engine.EngineError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Couldn't read this link. ({e})"}

    # ---- queue
    def add_jobs(self, specs):
        return self._jobs.add(specs)

    def state(self):
        return self._jobs.state()

    def remove_job(self, job_id):
        self._jobs.remove(job_id)

    def retry_job(self, job_id):
        self._jobs.retry(job_id)

    def retry_failed(self, history_id):
        return self._jobs.retry_failed(history_id)

    def clear_history(self):
        self._jobs.clear_history()

    def delete_files(self, history_id):
        return self._jobs.delete_files(history_id)

    def open_file(self, history_id):
        e = self._jobs.history_entry(history_id)
        if e and e["files"]:
            winutil.open_path(e["files"][0]["path"])

    def reveal(self, history_id):
        e = self._jobs.history_entry(history_id)
        if e and e["files"]:
            winutil.reveal(e["files"][0]["path"])

    def reveal_folder(self, mode):
        winutil.reveal(self._prefs.get({"video": "dir_video", "audio": "dir_audio", "gif": "dir_gif"}[mode]))

    # ---- settings
    def set_pref(self, key, value):
        self._prefs.set(key, value)
        if key == "simul":
            self._jobs.pump()
        if key == "nightly":
            self._prefs.set("last_update", 0)

    def choose_folder(self, current):
        """The normal Windows folder picker. Returns the chosen path, or None."""
        if not self._window:
            return None
        import webview
        start = current if current and os.path.isdir(current) else str(Path.home())
        res = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start)
        return os.path.normpath(res[0]) if res else None

    # ---- info page
    # ---- new versions of this app
    def check_app_update(self):
        """A newer release on GitHub that the user hasn't dismissed, or None. Does nothing if the setting is off."""
        if not self._prefs.get("check_updates"):
            return None
        r = engine.check_app_update(APP_VERSION)
        if r and r["version"] != self._prefs.get("update_dismissed"):
            return dict(r, current=APP_VERSION)
        return None

    def dismiss_update(self, version):
        self._prefs.set("update_dismissed", str(version))

    def open_url(self, url):
        """Opens a page of this app's own GitHub repository in the browser. Nothing else can be opened from the page."""
        if str(url).startswith(f"https://github.com/{engine.REPO}"):
            webbrowser.open(url)

    def versions(self):
        return {"yt_dlp": engine.ytdlp_version(), "ffmpeg": engine.ffmpeg_version(), "app": APP_VERSION}

    def update_ytdlp(self):
        r = engine.update_ytdlp(self._prefs.get("nightly"))
        self._prefs.set("last_update", __import__("time").time())
        return dict(r, version=engine.ytdlp_version())

    def sites(self):
        try:
            return engine.sites()
        except Exception:
            return []

    def clear_cache(self):
        engine.clear_cache()


# ---------------------------------------------------------------- dev bridge

def serve_dev(api, port):
    """Serves ui/ and exposes the Api as POST /api/<method> with a JSON list of arguments. 127.0.0.1 only."""
    names = {n for n in dir(api) if not n.startswith("_") and callable(getattr(api, n))}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _local(self):
            return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

        def do_GET(self):
            path = self.path.split("?")[0].lstrip("/") or "index.html"
            f = (UI / path).resolve()
            if not self._local() or UI.resolve() not in f.parents or not f.is_file():
                self.send_error(404)
                return
            mime = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
                    ".png": "image/png", ".ico": "image/x-icon"}.get(f.suffix, "application/octet-stream")
            data = f.read_bytes()
            if f.name == "index.html":
                data = data.replace(b"<head>", b"<head><script>window.DEV_BRIDGE = true</script>", 1)  # tells the page to use fetch, not pywebview
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            name = self.path.removeprefix("/api/")
            if not self._local() or name not in names:
                self.send_error(404)
                return
            args = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or "[]")
            try:
                body = json.dumps({"ok": getattr(api, name)(*args)}).encode()
            except Exception as e:
                body = json.dumps({"error": f"{type(e).__name__}: {e}"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    print(f"Dev server on http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def main():
    api = Api()
    if "--dev" in sys.argv:
        engine.ALLOW_PATH_YTDLP = True
        serve_dev(api, int(sys.argv[sys.argv.index("--dev") + 1]))
        return
    import webview
    if sys.platform == "win32":   # taskbar: group and icon under this app, not under python.exe
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(winutil.AUMID)
    api._window = webview.create_window(winutil.APP_NAME, url=str(UI / "index.html"), js_api=api, width=1080, height=720,
                                        min_size=(900, 600), background_color="#000000")
    webview.start(icon=str(UI / "img" / "app.ico"), storage_path=str(engine.data_dir() / "webview"))


if __name__ == "__main__":
    main()
