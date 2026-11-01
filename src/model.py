"""Pure logic, no I/O: the user's choices -> yt-dlp arguments, progress parsing, playlist bookkeeping.

A port of the phone app's Model.kt. Covered by tests/test_model.py.
"""
import re
from dataclasses import dataclass, fields

CODEC_SORT = {"h264": "vcodec:h264", "vp9": "vcodec:vp9", "av1": "vcodec:av01"}
AUDIO_EXT = {"m4a": "m4a", "mp3": "mp3", "opus": "opus"}  # "original" means: no conversion


@dataclass
class Options:
    """Everything one download needs. Field names match the JSON the UI sends."""
    mode: str = "video"              # video | audio | gif
    height: int = 1080
    fps60: bool = True
    codec: str = "h264"
    container: str = "mp4"
    audio_format: str = "original"
    bitrate: int = 192
    gif_width: int = 480
    gif_fps: int = 15
    gif_loop: bool = True
    trim: bool = False
    start: float = 0.0
    end: float = 5.0
    subtitles: bool = False
    sub_lang: str = "en"
    auto_subs: bool = True
    embed_subs: bool = True
    custom_name: str | None = None   # a file name, or a folder name for playlists
    title: str | None = None         # cleaned online title, used as the file name of a single video
    playlist: bool = False           # one yt-dlp run over the whole playlist ("Batch")
    range_from: int | None = None
    range_to: int | None = None
    items: list | None = None        # exact playlist positions (retry pass); beats the range
    own_folder: bool = True
    index: int | None = None         # "Separate": this job is item N of a playlist
    playlist_title: str | None = None
    fragments: int = 4
    rate_limit: str | None = None
    retries: int = 10
    proxy: str | None = None
    force_ipv4: bool = False

    @classmethod
    def from_dict(cls, d):
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


def safe_name(s):
    """Characters Windows file systems reject."""
    return re.sub(r'[\\/:*?"<>|\n\r\t]', " ", s).strip()[:150]


def clean_title(t):
    """Drops links from titles: X uses the post text as title, often 'Name - https://t.co/...'."""
    cleaned = re.sub(r"\s*[-–|:]?\s*https?://\S+", "", t).strip().rstrip("-–|:").strip()
    return cleaned or t


def clock(sec):
    """75.5 -> '1:15.5', 3700 -> '1:01:40'. yt-dlp accepts both."""
    tenths = int(sec * 10 + 0.5)
    s, frac = divmod(tenths, 10)
    base = f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    return f"{base}.{frac}" if frac else base


def parse_clock(text):
    """'1:15.5', '75', '1:01:40' -> seconds; None if unreadable."""
    parts = text.strip().split(":")
    if not text.strip() or len(parts) > 3:
        return None
    total = 0.0
    for p in parts:
        try:
            v = float(p)
        except ValueError:
            return None
        if v < 0:
            return None
        total = total * 60 + v
    return total


def build_args(o, out_dir):
    """yt-dlp options (without the URL) that download into out_dir."""
    a = ["--yes-playlist" if o.playlist else "--no-playlist", "--no-mtime", "-N", str(o.fragments), "-R", str(o.retries)]
    if o.playlist:
        a.append("--ignore-errors")  # a bad item is skipped; the app retries it afterwards
    if o.rate_limit:
        a += ["-r", o.rate_limit]
    if o.proxy and o.proxy.strip():
        a += ["--proxy", o.proxy.strip()]
    if o.force_ipv4:
        a.append("-4")

    name = safe_name(o.custom_name) if o.custom_name else ""
    title_name = safe_name(o.title) if o.title else ""
    in_playlist = o.playlist or o.index is not None
    folder = name or (safe_name(o.playlist_title) if o.playlist_title else "") or "%(playlist_title).80B"
    directory = f"{out_dir}/{folder}" if in_playlist and o.own_folder else out_dir
    if o.index is not None:
        file = f"{o.index:03d} - %(title).120B"
    elif o.playlist:
        file = "%(playlist_index)03d - %(title).120B"
    else:
        file = name or title_name or "%(title).150B"
    a += ["-o", f"{directory}/{file}.%(ext)s"]
    if o.playlist and o.items:
        a += ["-I", ",".join(str(i) for i in o.items)]
    elif o.playlist and o.range_from is not None:
        a += ["-I", f"{o.range_from}:{o.range_to if o.range_to is not None else ''}"]

    if o.mode == "gif" or o.trim:
        a += ["--download-sections", f"*{clock(o.start)}-{clock(o.end)}"]
        # Exact cuts need a re-encode, and ffmpeg's defaults would replace the chosen codec (VP9 -> H.264).
        # So video/audio cut losslessly at the nearest keyframe; GIFs are re-encoded anyway and cut exactly.
        if o.mode == "gif":
            a.append("--force-keyframes-at-cuts")

    if o.mode == "video":
        sort = [f"res:{o.height}", f"fps:{60 if o.fps60 else 30}", CODEC_SORT[o.codec]]
        # AAC: plays everywhere MP4 does, and (unlike Opus) cuts cleanly when trimming
        if o.container == "mp4" or (o.trim and o.container != "webm"):
            sort.append("acodec:aac")
        a += ["-f", "bv*+ba/b", "-S", ",".join(sort)]
        a += ["--merge-output-format", o.container, "--remux-video", o.container]
        if o.subtitles:
            a += ["--write-subs", "--sub-langs", o.sub_lang]
            if o.auto_subs:
                a.append("--write-auto-subs")
            a += ["--embed-subs"] if o.embed_subs else ["--convert-subs", "srt"]
    elif o.mode == "audio":
        a += ["-f", "ba/b", "-x"]
        if o.trim:
            a += ["-S", "acodec:aac"]  # Opus streams ignore the cut start
        ext = AUDIO_EXT.get(o.audio_format)
        if ext:
            a += ["--audio-format", ext, "--audio-quality", f"{o.bitrate}K"]
    else:  # gif
        # palette per clip = proper colours instead of GIF's default dithered mess
        vf = (f"fps={o.gif_fps},scale={o.gif_width}:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];"
              "[b][p]paletteuse=dither=bayer:bayer_scale=4")
        a += ["-f", "bv*[height<=720]/b[height<=720]/bv*/b", "--recode-video", "gif"]
        # -an: sites like X serve sound and picture in one file, and GIF has no audio encoder
        a += ["--postprocessor-args", f"VideoConvertor:-an -vf {vf} -loop {0 if o.gif_loop else -1}"]
    return a


_ITEM = re.compile(r"Downloading item (\d+) of (\d+)")
_STREAMS = re.compile(r"Downloading \d+ format\(s\): (\S+)")
_PCT = re.compile(r"^\[download]\s+(\d+(?:\.\d+)?)%")
_SUBTITLE = re.compile(r"\.(vtt|srt|ass|ttml|srv\d|json3|lrc)$")


class ProgressTracker:
    """Turns yt-dlp's per-stream 0-100 % into one overall fraction.

    Video and sound download as separate streams, each counting to 100 %, so a raw bar would fill twice.
    Subtitle files are ignored. `items` maps yt-dlp's "item N of M" back to real playlist positions.
    """

    def __init__(self, mode, items=None):
        self.mode = mode
        self.items = items
        self.streams = 1
        self.stream = -1
        self.skipping = False
        self.part = None
        self.item = None
        self.item_number = None   # N of "item N of M"

    @property
    def playlist_index(self):
        if self.item_number is None:
            return None
        if self.items and 0 < self.item_number <= len(self.items):
            return self.items[self.item_number - 1]
        return self.item_number

    def feed(self, line):
        """Feed every output line; returns the overall fraction for download-progress lines, else None."""
        t = line.strip()
        m = _ITEM.search(t)
        if m:
            self.item, self.item_number = f"{m.group(1)} of {m.group(2)}", int(m.group(1))
            self.stream, self.skipping = -1, False
        m = _STREAMS.search(t)
        if m:
            self.streams = m.group(1).count("+") + 1
        if t.startswith("[download] Destination:"):
            self.skipping = bool(_SUBTITLE.search(t))
            if not self.skipping:
                self.stream += 1
                self.part = self._part_name()
        if self.skipping:
            return None
        m = _PCT.search(t)
        if not m:
            return None
        pct = float(m.group(1))
        stream = min(max(self.stream, 0), self.streams - 1)
        return min(max((stream + pct / 100) / self.streams, 0.0), 1.0)

    def _part_name(self):
        if self.streams < 2:
            return None
        if self.mode == "video" and self.streams == 2:
            return "Video" if self.stream == 0 else "Sound"
        return f"Part {self.stream + 1} of {self.streams}"


def playlist_selection(total, range_from, range_to):
    """The playlist positions a download will cover: all, or from..to (1-based, end clipped to the list)."""
    start = range_from if range_from is not None else 1
    end = min(range_to, total) if range_to is not None else total
    return list(range(max(start, 1), end + 1))


def failed_items(selected, succeeded):
    """Positions that were asked for but produced no file, in playlist order."""
    done = set(succeeded)
    return [i for i in selected if i not in done]


def friendly_error(text):
    """The last meaningful line of yt-dlp's output, in plain words."""
    low = (text or "").lower()
    if any(k in low for k in ("errno 11001", "unable to resolve", "failed to resolve", "getaddrinfo failed",
                              "network is unreachable", "no address associated", "name or service not known",
                              "connection refused", "timed out")):
        return "No internet connection"
    errors = [ln.strip() for ln in (text or "").splitlines() if ln.strip().startswith("ERROR")]
    if not errors:
        return "Download failed"
    msg = re.sub(r"^ERROR:\s*", "", errors[-1])
    msg = re.sub(r"^\[[^\]]+\]\s*(?:[\w-]+:\s*)?", "", msg)
    msg = re.sub(r"\s*\(caused by .*$", "", msg)
    msg = re.sub(r"^Unable to download webpage:\s*", "", msg)
    low = msg.lower()
    if "cloudflare" in low or "impersonat" in low:
        return "This site blocked the request (anti-bot protection)."
    if "private video" in low:
        return "This video is private"
    if "login" in low or "cookies" in low or "sign in" in low:
        return "This post needs a logged-in account to download."
    if "unsupported url" in low:
        return "This link isn't supported. See the Info tab for every supported site."
    if "no video formats" in low or "no video" in low:
        return "There's no video in this post."
    return msg[:200] or "Download failed"
