"""The queue's rules: concurrency limit, playlist failsafe (skip, retry, report), merging retries into history.
yt-dlp is replaced by a fake so failures are deterministic."""
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
TMP = tempfile.mkdtemp(prefix="md-test-")
os.environ["MEDIA_DESKTOP_HOME"] = TMP

import engine  # noqa: E402
import jobs  # noqa: E402
import prefs as prefs_mod  # noqa: E402
import winutil  # noqa: E402

winutil.notify = lambda *a: None


def wait_for(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=TMP)
        self.prefs = prefs_mod.Prefs()
        for k in ("dir_video", "dir_audio", "dir_gif"):
            self.prefs.set(k, self.dir)
        self.prefs.set("simul", 3)
        self.mgr = jobs.Manager(self.prefs)
        self.mgr._history = []
        self.calls = []
        self._orig = engine.run_download
        engine.run_download = self.fake

    def tearDown(self):
        engine.run_download = self._orig

    def make_file(self, name):
        p = os.path.join(self.dir, name)
        with open(p, "w") as f:
            f.write("x" * 10)
        return p

    def fake(self, url, o, out_dir, on_progress, on_proc, info_file=None, selection=None):
        raise NotImplementedError

    def spec(self, **o):
        options = {"mode": "audio", "playlist": True, **o}
        return {"url": "https://example.com/p", "title": "Playlist", "options": options, "playlist_total": 4,
                "entry_titles": {1: "One", 2: "Two", 3: "Three", 4: "Four"}}

    def done(self):
        return wait_for(lambda: not self.mgr.state()["jobs"] and self.mgr.state()["history"])


class PlaylistFailsafe(Base):
    def result(self, ok, errors=None, code=1):
        return {"files": [{"path": self.make_file(f"{i:03d}.opus"), "index": i} for i in ok], "errors": errors or {}, "code": code, "tail": ""}

    def test_failed_item_is_retried_then_reported_not_failed(self):
        def fake(url, o, out_dir, on_progress, on_proc, info_file=None, selection=None):
            self.calls.append(o.items)
            return self.result([1, 3, 4], {2: "Video unavailable"}) if o.items is None else self.result([], {2: "Video unavailable"})
        engine.run_download = fake
        self.mgr.add([self.spec()])
        self.assertTrue(self.done())
        entry = self.mgr.state()["history"][0]
        self.assertEqual([None, [2], [2]], self.calls)                       # the full run, then two retry passes of just item 2
        self.assertEqual(3, len(entry["files"]))
        self.assertEqual([{"index": 2, "title": "Two", "reason": "Video unavailable"}], entry["failed"])  # completed, with a failure report

    def test_retry_that_works_leaves_nothing_failed(self):
        def fake(url, o, out_dir, on_progress, on_proc, info_file=None, selection=None):
            self.calls.append(o.items)
            return self.result([1, 3, 4], {2: "Video unavailable"}) if o.items is None else self.result([2], code=0)
        engine.run_download = fake
        self.mgr.add([self.spec()])
        self.assertTrue(self.done())
        entry = self.mgr.state()["history"][0]
        self.assertEqual([None, [2]], self.calls)                            # no second retry once it worked
        self.assertEqual((4, []), (len(entry["files"]), entry["failed"]))

    def test_manual_retry_merges_into_the_same_history_entry(self):
        def fake(url, o, out_dir, on_progress, on_proc, info_file=None, selection=None):
            self.calls.append(o.items)
            return self.result([1, 3, 4], {2: "This video is private"}) if o.items is None else self.result([], {2: "This video is private"})
        engine.run_download = fake
        self.mgr.add([self.spec()])
        self.assertTrue(self.done())
        entry = self.mgr.state()["history"][0]
        self.assertEqual("This video is private", entry["failed"][0]["reason"])
        n = len(self.calls)
        engine.run_download = lambda *a, **k: self.result([2], code=0)
        self.assertTrue(self.mgr.retry_failed(entry["id"]))
        self.assertTrue(wait_for(lambda: not self.mgr.state()["jobs"] and not self.mgr.state()["history"][0]["failed"]))
        h = self.mgr.state()["history"]
        self.assertEqual(1, len(h))                                          # still one entry, now complete
        self.assertEqual(4, len(h[0]["files"]))

    def test_everything_failing_is_a_real_failure(self):
        engine.run_download = lambda *a, **k: {"files": [], "errors": {}, "code": 1, "tail": "ERROR: [youtube] x: Unable to resolve host"}
        self.mgr.add([self.spec()])
        self.assertTrue(wait_for(lambda: self.mgr.state()["jobs"] and self.mgr.state()["jobs"][0]["status"] == "failed"))
        j = self.mgr.state()["jobs"][0]
        self.assertEqual("No internet connection", j["error"])
        self.assertEqual([], self.mgr.state()["history"])

    def test_range_selection_limits_what_counts_as_failed(self):
        def fake(url, o, out_dir, on_progress, on_proc, info_file=None, selection=None):
            self.calls.append(o.items)
            return self.result([2, 3], code=0)
        engine.run_download = fake
        self.mgr.add([self.spec(range_from=2, range_to=3)])
        self.assertTrue(self.done())
        self.assertEqual([None], self.calls)                                 # items 1 and 4 were never asked for
        self.assertEqual([], self.mgr.state()["history"][0]["failed"])


class Concurrency(Base):
    def test_never_more_than_the_limit_run_at_once(self):
        self.prefs.set("simul", 2)
        lock, state = threading.Lock(), {"now": 0, "max": 0}
        gate = threading.Event()

        def fake(url, o, out_dir, on_progress, on_proc, info_file=None, selection=None):
            with lock:
                state["now"] += 1
                state["max"] = max(state["max"], state["now"])
            gate.wait(2)
            with lock:
                state["now"] -= 1
            return {"files": [{"path": self.make_file(os.path.basename(url) + ".mp4"), "index": 0}], "errors": {}, "code": 0, "tail": ""}
        engine.run_download = fake
        self.mgr.add([{"url": f"https://e.com/{i}", "title": str(i), "options": {"mode": "video"}} for i in range(5)])
        self.assertTrue(wait_for(lambda: state["now"] == 2))
        time.sleep(0.1)
        self.assertEqual(2, state["now"])                                    # the other three are waiting
        self.assertEqual(3, sum(j["status"] == "waiting" for j in self.mgr.state()["jobs"]))
        gate.set()
        self.assertTrue(wait_for(lambda: len(self.mgr.state()["history"]) == 5))
        self.assertEqual(2, state["max"])

    def test_raising_the_limit_starts_waiting_jobs(self):
        self.prefs.set("simul", 1)
        gate = threading.Event()

        def fake(url, o, out_dir, on_progress, on_proc, info_file=None, selection=None):
            gate.wait(3)
            return {"files": [{"path": self.make_file(os.path.basename(url) + ".mp4"), "index": 0}], "errors": {}, "code": 0, "tail": ""}
        engine.run_download = fake
        self.mgr.add([{"url": f"https://e.com/{i}", "title": str(i), "options": {"mode": "video"}} for i in range(3)])
        self.assertTrue(wait_for(lambda: sum(j["status"] == "running" for j in self.mgr.state()["jobs"]) == 1))
        self.prefs.set("simul", 3)
        self.mgr.pump()
        self.assertTrue(wait_for(lambda: sum(j["status"] == "running" for j in self.mgr.state()["jobs"]) == 3))
        gate.set()


class CutsAreMadeApart(Base):
    def test_a_cut_is_made_in_a_work_folder_and_moved_without_overwriting(self):
        seen = {}

        def fake(url, o, out_dir, on_progress, on_proc, info_file=None, selection=None):
            seen["dir"] = out_dir
            p = os.path.join(out_dir, "clip.gif")
            os.makedirs(out_dir, exist_ok=True)
            open(p, "w").write("cut")
            return {"files": [{"path": p, "index": 0}], "errors": {}, "code": 0, "tail": ""}
        engine.run_download = fake
        existing = self.make_file("clip.gif")                                # an earlier download with the same name
        self.mgr.add([{"url": "https://e.com/g", "title": "G", "options": {"mode": "gif"}}])
        self.assertTrue(self.done())
        files = self.mgr.state()["history"][0]["files"]
        self.assertNotEqual(self.dir, seen["dir"])                           # it did not work inside the save folder
        self.assertEqual(os.path.join(self.dir, "clip (2).gif"), files[0]["path"])
        self.assertEqual("x" * 10, open(existing).read())                    # the old file is untouched
        self.assertFalse(os.path.exists(seen["dir"]))                        # and the work folder is gone


class History(Base):
    def test_history_survives_a_restart(self):
        engine.run_download = lambda *a, **k: {"files": [{"path": self.make_file("a.mp4"), "index": 0}], "errors": {}, "code": 0, "tail": ""}
        self.mgr.add([{"url": "https://e.com/a", "title": "A", "options": {"mode": "video"}}])
        self.assertTrue(self.done())
        again = jobs.Manager(self.prefs)
        self.assertEqual("A", again.state()["history"][0]["title"])

    def test_delete_goes_through_the_recycle_bin(self):
        engine.run_download = lambda *a, **k: {"files": [{"path": self.make_file("b.mp4"), "index": 0}], "errors": {}, "code": 0, "tail": ""}
        self.mgr.add([{"url": "https://e.com/b", "title": "B", "options": {"mode": "video"}}])
        self.assertTrue(self.done())
        trashed = []
        winutil.recycle = lambda paths: trashed.extend(paths) or True
        self.assertTrue(self.mgr.delete_files(self.mgr.state()["history"][0]["id"]))
        self.assertEqual(1, len(trashed))
        self.assertEqual([], self.mgr.state()["history"])


if __name__ == "__main__":
    unittest.main()
