"""Engine pieces that need no network: reading yt-dlp's JSON, finding links, unpacking downloaded tools."""
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("MEDIA_DESKTOP_HOME", tempfile.mkdtemp(prefix="md-test-"))

import engine  # noqa: E402


class ParseInfo(unittest.TestCase):
    def test_single_video(self):
        j = {"title": "T - https://t.co/x", "uploader": "U", "duration": 19, "upload_date": "20050424", "extractor_key": "Youtube",
             "thumbnail": "http://t/1.jpg", "formats": [
                 {"format_id": "137", "ext": "mp4", "height": 1080, "width": 1920, "fps": 30, "vcodec": "avc1", "acodec": "none", "filesize": 5, "tbr": 100},
                 {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "abr": 128, "filesize_approx": 9}]}
        m = engine.parse_info(j, "https://y/watch?v=1", "info.json")
        self.assertEqual(("video", "T", "2005-04-24", "YouTube", "info.json"), (m["kind"], m["title"], m["date"], m["site"], m["info_file"]))
        self.assertEqual((1080, "none", 5), (m["formats"][0]["height"], m["formats"][0]["acodec"], m["formats"][0]["size"]))
        self.assertEqual((None, 9), (m["formats"][1]["height"], m["formats"][1]["size"]))   # approx size is used when exact is missing

    def test_playlist_keeps_positions_and_builds_youtube_urls(self):
        j = {"_type": "playlist", "title": "P", "extractor_key": "YoutubeTab", "playlist_count": 3,
             "entries": [{"title": "A", "url": "https://www.youtube.com/watch?v=aaa"}, None, {"title": "C", "url": "ccc", "ie_key": "Youtube"}]}
        m = engine.parse_info(j, "https://y/playlist?list=1", "info.json")
        self.assertEqual(("playlist", 3, "YouTube", None), (m["kind"], m["playlist_count"], m["site"], m["info_file"]))
        self.assertEqual([1, 3], [e["index"] for e in m["entries"]])                        # a dead entry keeps its slot
        self.assertEqual("https://www.youtube.com/watch?v=ccc", m["entries"][1]["url"])

    def test_find_url(self):
        self.assertEqual("https://a.com/x?y=1", engine.find_url("look at this https://a.com/x?y=1 now"))
        self.assertEqual("https://youtube.com/watch?v=1", engine.find_url("youtube.com/watch?v=1"))
        self.assertIsNone(engine.find_url("just words"))

    def test_site_names(self):
        self.assertEqual("X", engine.site_name("Twitter"))
        self.assertEqual("YouTube", engine.site_name("YoutubeTab"))
        self.assertEqual("Instagram", engine.site_name("Instagram"))


class Tools(unittest.TestCase):
    def test_extract_picks_files_from_any_folder_in_the_zip(self):
        with tempfile.TemporaryDirectory() as td:
            z = Path(td) / "ff.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("ffmpeg-master/bin/ffmpeg.exe", "a")
                zf.writestr("ffmpeg-master/bin/ffprobe.exe", "b")
                zf.writestr("ffmpeg-master/LICENSE.txt", "c")
            out = Path(td) / "bin"
            engine._extract(z, {"ffmpeg.exe", "ffprobe.exe"}, out)
            self.assertEqual({"ffmpeg.exe", "ffprobe.exe"}, {p.name for p in out.iterdir()})
            with self.assertRaises(engine.EngineError):
                engine._extract(z, {"deno.exe"}, out)


class DataFolder(unittest.TestCase):
    def test_store_python_keeps_data_outside_the_redirected_folders(self):
        old_env = os.environ.pop("MEDIA_DESKTOP_HOME", None)
        old_prefix, old_mkdir = sys.base_prefix, Path.mkdir
        Path.mkdir = lambda *a, **k: None          # only choosing the folder is tested, not creating it
        try:
            sys.base_prefix = r"C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_x64__abc"
            self.assertEqual(Path.home() / ".media-desktop", engine.data_dir())
            sys.base_prefix = r"C:\Python313"
            self.assertEqual("MediaDesktop", engine.data_dir().name)
        finally:
            sys.base_prefix, Path.mkdir = old_prefix, old_mkdir
            if old_env:
                os.environ["MEDIA_DESKTOP_HOME"] = old_env

    def test_the_users_own_yt_dlp_config_is_ignored(self):
        old = engine.ALLOW_PATH_YTDLP
        engine.ALLOW_PATH_YTDLP = True
        try:
            if engine.tool_status()["paths"]["yt-dlp"]:
                self.assertIn("--ignore-config", engine._base())
        finally:
            engine.ALLOW_PATH_YTDLP = old


class Notification(unittest.TestCase):
    def test_toast_xml_is_escaped_and_clicking_opens_the_target(self):
        import winutil
        from xml.dom import minidom
        x = winutil.toast_xml('Tom & "Jerry" <1>', "3 saved, 1 failed", r"C:\Users\me\Videos\clip & more.mp4")
        self.assertIn("Tom &amp; &quot;Jerry&quot; &lt;1&gt;", x)
        self.assertIn('activationType="protocol" launch="file:///C:/Users/me/Videos/clip%20%26%20more.mp4"', x)
        self.assertNotIn("launch", winutil.toast_xml("T", "x"))          # nothing to open: a plain notification
        minidom.parseString(x)                                            # and the XML is well-formed

    def test_the_notification_has_its_own_identity_and_icon(self):
        import winutil
        self.assertEqual("MediaDesktop.App", winutil.AUMID)
        self.assertTrue(winutil.ICON.is_file())


if __name__ == "__main__":
    unittest.main()
