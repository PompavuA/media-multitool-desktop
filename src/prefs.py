"""Settings and 'last used' choices, saved as JSON the moment they change."""
import json
import threading

import engine
import winutil


def defaults():
    return {
        # last used download choices
        "mode": "video", "height": 1080, "fps60": True, "codec": "h264", "container": "mp4", "audio_format": "original",
        "bitrate": 192, "gif_width": 480, "gif_fps": 15, "gif_loop": True, "subtitles": False, "own_folder": True, "pl_run": "batch",
        "b_mode": "video", "b_height": 1080, "b_container": "mp4", "b_audio_format": "mp3", "b_pl_run": "batch",
        # settings
        "dir_video": winutil.known_folder("Videos", winutil.APP_NAME), "dir_audio": winutil.known_folder("Music", winutil.APP_NAME),
        "dir_gif": winutil.known_folder("Pictures", winutil.APP_NAME),
        "sub_lang": "en", "auto_subs": True, "embed_subs": True,
        "simul": 3, "fragments": 4, "rate_limit": "", "retries": 10, "proxy": "", "force_ipv4": False,
        "nightly": False, "dark": True, "notify": True, "clip": True, "sidebar_collapsed": False, "check_updates": True, "update_dismissed": "",
        # bookkeeping
        "last_update": 0,
    }


class Prefs:
    def __init__(self):
        self._lock = threading.Lock()
        self._file = engine.data_dir() / "prefs.json"
        self._data = defaults()
        try:
            self._data.update({k: v for k, v in json.loads(self._file.read_text(encoding="utf-8")).items() if k in self._data})
        except (OSError, ValueError):
            pass

    def get(self, key):
        with self._lock:
            return self._data[key]

    def all(self):
        with self._lock:
            return dict(self._data)

    def set(self, key, value):
        with self._lock:
            if key not in self._data:
                raise KeyError(key)
            self._data[key] = value
            self._file.write_text(json.dumps(self._data, indent=1), encoding="utf-8")
