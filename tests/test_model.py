"""Port of the phone app's ModelTest.kt: the option -> yt-dlp argument logic is the spec."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from model import (Options, ProgressTracker, build_args, clean_title, clock, failed_items, friendly_error,
                   parse_clock, playlist_selection, safe_name)


def arg(a, flag):
    return a[a.index(flag) + 1]


class BuildArgs(unittest.TestCase):
    def test_video_args(self):
        a = build_args(Options(height=720, fps60=False, codec="vp9", container="mkv"), "/out")
        for x in ["--no-playlist", "-f", "bv*+ba/b", "-S", "res:720,fps:30,vcodec:vp9", "--merge-output-format", "mkv"]:
            self.assertIn(x, a)
        self.assertEqual("/out/%(title).150B.%(ext)s", arg(a, "-o"))

    def test_mp4_prefers_aac_and_subtitles(self):
        a = build_args(Options(subtitles=True, sub_lang="sk", embed_subs=False), "/out")
        self.assertEqual("res:1080,fps:60,vcodec:h264,acodec:aac", arg(a, "-S"))
        for x in ["--write-subs", "--write-auto-subs", "--convert-subs", "srt"]:
            self.assertIn(x, a)
        self.assertEqual("sk", arg(a, "--sub-langs"))

    def test_audio_original_vs_converted(self):
        self.assertNotIn("--audio-format", build_args(Options(mode="audio"), "/o"))
        a = build_args(Options(mode="audio", audio_format="mp3", bitrate=320), "/o")
        i = a.index("--audio-format")
        self.assertEqual(["--audio-format", "mp3", "--audio-quality", "320K"], a[i:i + 4])

    def test_gif_always_cuts_a_section(self):
        a = build_args(Options(mode="gif", start=12.0, end=18.5, gif_width=640, gif_fps=24, gif_loop=False), "/o")
        self.assertEqual("*0:12-0:18.5", arg(a, "--download-sections"))
        self.assertIn("--force-keyframes-at-cuts", a)
        # video trims stay lossless so the chosen codec survives
        v = build_args(Options(trim=True, start=1.0, end=4.0, codec="vp9"), "/o")
        self.assertIn("--download-sections", v)
        self.assertNotIn("--force-keyframes-at-cuts", v)
        # ...and pick AAC audio, because Opus ignores the cut start
        mkv = build_args(Options(trim=True, container="mkv"), "/o")
        self.assertTrue(arg(mkv, "-S").endswith("acodec:aac"))
        aud = build_args(Options(mode="audio", trim=True), "/o")
        self.assertEqual("acodec:aac", arg(aud, "-S"))
        pp = arg(a, "--postprocessor-args")
        self.assertTrue(pp.startswith("VideoConvertor:-an -vf fps=24,scale=640:-1") and pp.endswith("-loop -1"))

    def test_custom_name_and_playlist(self):
        named = build_args(Options(custom_name="my: clip?"), "/o")
        self.assertEqual("/o/my  clip.%(ext)s", arg(named, "-o"))
        pl = build_args(Options(playlist=True, range_from=3, range_to=7), "/o")
        for x in ["--yes-playlist", "-I", "3:7"]:
            self.assertIn(x, pl)
        self.assertEqual("/o/%(playlist_title).80B/%(playlist_index)03d - %(title).120B.%(ext)s", arg(pl, "-o"))

    def test_playlist_options(self):
        # a bad item is skipped, not fatal
        self.assertIn("--ignore-errors", build_args(Options(playlist=True), "/o"))
        self.assertNotIn("--ignore-errors", build_args(Options(), "/o"))
        # no own folder: files go straight into the save folder; a folder name only names the folder
        flat = build_args(Options(playlist=True, own_folder=False, custom_name="ignored"), "/o")
        self.assertEqual("/o/%(playlist_index)03d - %(title).120B.%(ext)s", arg(flat, "-o"))
        named = build_args(Options(playlist=True, custom_name="Study: beats"), "/o")
        self.assertEqual("/o/Study  beats/%(playlist_index)03d - %(title).120B.%(ext)s", arg(named, "-o"))
        # a retry pass asks for exactly the failed items
        retry = build_args(Options(playlist=True, items=[7, 15]), "/o")
        self.assertEqual("7,15", arg(retry, "-I"))

    def test_separate_item_keeps_playlist_numbering(self):
        a = build_args(Options(index=4, playlist_title="Lo-fi: beats"), "/o")
        self.assertIn("--no-playlist", a)
        self.assertEqual("/o/Lo-fi  beats/004 - %(title).120B.%(ext)s", arg(a, "-o"))
        flat = build_args(Options(index=4, playlist_title="x", own_folder=False), "/o")
        self.assertEqual("/o/004 - %(title).120B.%(ext)s", arg(flat, "-o"))

    def test_network_options(self):
        a = build_args(Options(fragments=8, rate_limit="2M", proxy="socks5://h:1", force_ipv4=True), "/o")
        for x in ["-N", "8", "-r", "2M", "--proxy", "socks5://h:1", "-4"]:
            self.assertIn(x, a)

    def test_unlabeled_x_post_and_titles(self):
        self.assertEqual("McGrilla 🦆", clean_title("McGrilla 🦆 - https://t.co/cVCgQ2xp64"))
        self.assertEqual("Look at this | wow", clean_title("Look at this https://t.co/a | wow"))
        self.assertEqual("https://t.co/a", clean_title("https://t.co/a"))  # nothing left: keep the original
        named = build_args(Options(title="McGrilla: duck"), "/o")
        self.assertEqual("/o/McGrilla  duck.%(ext)s", arg(named, "-o"))
        custom = build_args(Options(title="x", custom_name="mine"), "/o")
        self.assertEqual("/o/mine.%(ext)s", arg(custom, "-o"))
        gif = build_args(Options(mode="gif", start=0.0, end=10.0), "/o")
        self.assertIn("bv*[height<=720]/b[height<=720]/bv*/b", gif)


class Clocks(unittest.TestCase):
    def test_clocks(self):
        self.assertEqual("1:15.5", clock(75.5))
        self.assertEqual("1:01:40", clock(3700.0))
        self.assertEqual("0:05", clock(5.0))
        self.assertAlmostEqual(75.5, parse_clock("1:15.5"))
        self.assertAlmostEqual(3700.0, parse_clock("1:01:40"))
        self.assertIsNone(parse_clock("1:x"))
        self.assertIsNone(parse_clock("1:2:3:4"))


class Progress(unittest.TestCase):
    def test_progress_across_streams(self):
        t = ProgressTracker("video")
        self.assertIsNone(t.feed("[info] aqz: Downloading 1 format(s): 135+140"))
        # a subtitle file comes first and must not count as a stream
        t.feed("[download] Destination: /x/Film.en.vtt")
        self.assertIsNone(t.feed("[download] 100% of 50.00KiB"))
        t.feed("[download] Destination: /x/Film.f135.mp4")
        self.assertAlmostEqual(0.25, t.feed("[download]  50.0% of   27.00MiB at    5.63MiB/s ETA 00:02"), places=4)
        self.assertEqual("Video", t.part)
        self.assertAlmostEqual(0.5, t.feed("[download] 100% of   27.00MiB in 00:00:04"), places=4)
        t.feed("[download] Destination: /x/Film.f140.m4a")
        self.assertAlmostEqual(0.5, t.feed("[download]   0.0% of 9.00MiB at 1.00MiB/s ETA 00:09"), places=4)  # never goes backwards
        self.assertEqual("Sound", t.part)
        self.assertAlmostEqual(1.0, t.feed("[download] 100% of 9.00MiB"), places=4)
        self.assertIsNone(t.feed('[Merger] Merging formats into "/x/Film.mp4"'))
        a = ProgressTracker("audio")
        a.feed("[info] x: Downloading 1 format(s): 251")
        a.feed("[download] Destination: /x/a.webm")
        self.assertAlmostEqual(0.42, a.feed("[download]  42.0% of 4.00MiB"), places=4)
        self.assertIsNone(a.part)

    def test_playlist_item_counter(self):
        t = ProgressTracker("audio")
        t.feed("[download] Downloading item 4 of 24")
        self.assertEqual("4 of 24", t.item)
        self.assertEqual(4, t.item_number)


class Playlists(unittest.TestCase):
    def test_selection_and_failed_items(self):
        self.assertEqual(list(range(1, 25)), playlist_selection(24, None, None))
        self.assertEqual([3, 4, 5, 6, 7], playlist_selection(24, 3, 7))
        self.assertEqual([22, 23, 24], playlist_selection(24, 22, 99))  # end past the list stops at the list
        self.assertEqual([], playlist_selection(24, 30, None))
        self.assertEqual([7, 15], failed_items(list(range(1, 17)), [i for i in range(1, 17) if i not in (7, 15)]))
        self.assertEqual([], failed_items([1, 2, 3], [3, 2, 1]))
        # a retry pass selects a list: yt-dlp's "item N of M" counts inside that list
        t = ProgressTracker("audio", items=[7, 15])
        t.feed("[download] Downloading item 2 of 2")
        self.assertEqual(15, t.playlist_index)

    def test_friendly_errors(self):
        self.assertEqual("No internet connection", friendly_error("ERROR: [youtube] x: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed> Unable to resolve host"))
        self.assertEqual("Video unavailable", friendly_error("junk\nERROR: [youtube] abc123: Video unavailable"))
        self.assertEqual("This video is private", friendly_error("ERROR: [youtube] abc123: Private video. Sign in if you've been granted access to this video"))
        self.assertEqual("HTTP Error 404: Not Found", friendly_error("ERROR: [generic] Unable to download webpage: HTTP Error 404: Not Found (caused by <HTTPError 404: Not Found>)"))
        self.assertTrue(friendly_error("ERROR: [generic] Got HTTP Error 403 caused by Cloudflare anti-bot challenge; see https://x").startswith("This site blocked"))
        self.assertEqual("Download failed", friendly_error(""))
        self.assertEqual("This post needs a logged-in account to download.", friendly_error("ERROR: [Instagram] x: login required"))


if __name__ == "__main__":
    unittest.main()
