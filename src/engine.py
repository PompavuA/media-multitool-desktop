"""Talks to the outside tools: yt-dlp.exe, ffmpeg and Deno. Finds them, downloads them on first run,
reads what a link offers, and runs one download as a child process while parsing its progress."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import model

WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if WIN else 0  # CREATE_NO_WINDOW: no console flash for every yt-dlp run
INFO_MAX_AGE = 4 * 3600               # YouTube's download links expire after ~6 h

TOOL_URLS = {
    "yt-dlp": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
    "ffmpeg": "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
    "deno": "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
}


class EngineError(Exception):
    pass


def _store_python():
    """The Microsoft Store build of Python silently redirects writes under %LOCALAPPDATA% into a private package folder,
    where a program started from there (yt-dlp.exe) can't find its own files."""
    return "WindowsApps" in (sys.base_prefix or "")


def data_dir():
    """Where the app keeps tools, settings, history and caches (MEDIA_DESKTOP_HOME overrides it for tests)."""
    env = os.environ.get("MEDIA_DESKTOP_HOME")
    if env:
        base = Path(env)
    elif _store_python():
        base = Path.home() / ".media-desktop"     # outside the redirected folders, so downloaded tools can run
    else:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MediaDesktop"
    base.mkdir(parents=True, exist_ok=True)
    return base


def bin_dir():
    return data_dir() / "bin"


def cache_dir():
    return data_dir() / "cache"


# ---------------------------------------------------------------- new versions of this app

REPO = "PompavuA/media-multitool-desktop"


def version_tuple(v):
    """'v1.2.3' -> (1, 2, 3). Anything after a dash (a pre-release tag) is ignored."""
    return tuple(int(n) for n in re.findall(r"\d+", str(v).lstrip("vV").split("-")[0]))


def feature_level(v):
    """The part of a version that means 'new features': major and minor (1.2.3 -> (1, 2)). The last number is for small fixes."""
    return (version_tuple(v) + (0, 0))[:2]


def check_app_update(current):
    """Asks GitHub for the latest release of this app. Returns {'version', 'url'} only if it brings new features, that is,
    its major or minor number is higher than `current`'s. A small-fix release (1.0.0 -> 1.0.1) stays silent.
    Any failure (offline, rate limit, no release published yet) just means 'nothing to report'."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "MediaMultiToolDesktop", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            j = json.load(r)
        tag = j.get("tag_name") or ""
        if j.get("draft") or j.get("prerelease") or feature_level(tag) <= feature_level(current):
            return None
        return {"version": tag.lstrip("vV"), "url": j.get("html_url") or f"https://github.com/{REPO}/releases/latest"}
    except (OSError, ValueError, AttributeError):
        return None


# ---------------------------------------------------------------- tools

# yt-dlp must be the app's own self-updating copy: one from pip or a package manager can't update itself.
# `app.py --dev` (or this variable) allows the copy on PATH, for development.
ALLOW_PATH_YTDLP = bool(os.environ.get("MEDIA_DESKTOP_USE_PATH_YTDLP"))


def find_tool(name):
    """The app's own copy first, then a copy bundled next to a frozen exe, then (ffmpeg and Deno only) whatever is on PATH."""
    exe = name + (".exe" if WIN else "")
    candidates = [bin_dir() / exe]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / "bin" / exe)
    for c in candidates:
        if c.is_file():
            return str(c)
    if name == "yt-dlp" and not ALLOW_PATH_YTDLP:
        return None
    return shutil.which(name)


def tool_status():
    paths = {n: find_tool(n) for n in ("yt-dlp", "ffmpeg", "deno")}
    missing = [n for n, p in paths.items() if not p]
    return {"paths": paths, "ready": not missing, "missing": missing}   # Deno too: without it YouTube links fail


def _extract(zip_path, wanted, dest):
    """Copies the files named in `wanted` (matched by file name, any folder inside the zip) into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    found = set()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            base = os.path.basename(info.filename)
            if base in wanted:
                with z.open(info) as src, open(dest / base, "wb") as out:
                    shutil.copyfileobj(src, out)
                found.add(base)
    missing = set(wanted) - found
    if missing:
        raise EngineError("Missing in download: " + ", ".join(sorted(missing)))


def download_file(url, dest, on_bytes=None):
    req = urllib.request.Request(url, headers={"User-Agent": "MediaDesktop"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as out:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 16):
            out.write(chunk)
            done += len(chunk)
            if on_bytes:
                on_bytes(done, total)


def setup_tools(missing, on_progress):
    """Downloads the missing tools into the app's bin folder. on_progress(step_text, fraction)."""
    bin_dir().mkdir(parents=True, exist_ok=True)
    steps = [n for n in ("yt-dlp", "ffmpeg", "deno") if n in missing]
    for i, name in enumerate(steps):
        def tick(done, total, i=i, name=name):
            on_progress(f"Downloading {name}…", (i + (done / total if total else 0)) / len(steps))
        url = TOOL_URLS[name]
        if name == "yt-dlp":
            tmp = bin_dir() / "yt-dlp.exe.part"
            download_file(url, tmp, tick)
            os.replace(tmp, bin_dir() / "yt-dlp.exe")
        else:
            with tempfile.TemporaryDirectory() as td:
                z = Path(td) / (name + ".zip")
                download_file(url, z, tick)
                _extract(z, {"ffmpeg.exe", "ffprobe.exe"} if name == "ffmpeg" else {"deno.exe"}, bin_dir())
    on_progress("Done", 1.0)


def _base(extra_cache=True):
    st = tool_status()["paths"]
    if not st["yt-dlp"]:
        raise EngineError("yt-dlp is not installed yet")
    cmd = [st["yt-dlp"], "--ignore-config", "--encoding", "utf-8", "--no-colors"]   # --ignore-config: a config file of the user's own must not change what the app asks for
    if st["ffmpeg"]:
        cmd += ["--ffmpeg-location", str(Path(st["ffmpeg"]).parent)]
    if st["deno"]:
        cmd += ["--js-runtimes", f"deno:{st['deno']}"]  # YouTube needs a JS runtime; the app brings its own
    if extra_cache:
        cmd += ["--cache-dir", str(cache_dir())]
    return cmd


def _run(cmd, timeout=None):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW)
    return p.returncode, p.stdout, p.stderr


def ytdlp_version():
    try:
        return _run([tool_status()["paths"]["yt-dlp"], "--version"], 20)[1].strip() or "?"
    except Exception:
        return "?"


def ffmpeg_version():
    p = tool_status()["paths"]["ffmpeg"]
    if not p:
        return "?"
    try:
        m = re.search(r"ffmpeg version (\S+)", _run([p, "-version"], 20)[1])
        return (m.group(1) if m else "?")[:24]
    except Exception:
        return "?"


def update_ytdlp(nightly):
    """Asks yt-dlp to update itself. A copy installed with pip or a package manager refuses, which is reported as 'managed'."""
    exe = tool_status()["paths"]["yt-dlp"]
    if not exe:
        return {"status": "failed", "message": "yt-dlp is not installed"}
    code, out, err = _run([exe, "--update-to", "nightly" if nightly else "stable"], 180)
    text = out + err
    clear_cache()
    low = text.lower()
    if "pip" in low or "package manager" in low:
        return {"status": "managed", "message": "This copy of yt-dlp is managed by pip or a package manager"}
    if code != 0:
        return {"status": "failed", "message": model.friendly_error(text)}
    if "updated yt-dlp" in low or "updating to" in low and "up to date" not in low:
        return {"status": "updated", "message": text.strip()[-200:]}
    return {"status": "current", "message": text.strip()[-200:]}


def clear_cache():
    shutil.rmtree(cache_dir(), ignore_errors=True)


def sites():
    """Every site yt-dlp supports, one name per site, cached until the next update."""
    f = data_dir() / "sites.txt"
    if f.exists():
        return f.read_text(encoding="utf-8").splitlines()
    code, out, _ = _run(_base() + ["--list-extractors"], 60)
    names = {}
    for line in out.splitlines():
        n = line.split(":")[0].split(" (")[0].strip()
        if n and not n.lower().startswith("generic"):
            names.setdefault(n.lower(), n)
    result = sorted(names.values(), key=str.lower)
    if result:
        f.write_text("\n".join(result), encoding="utf-8")
    return result


# ---------------------------------------------------------------- reading a link

_SITE_NAMES = {"Youtube": "YouTube", "Twitter": "X", "TikTok": "TikTok", "Vimeo": "Vimeo", "Reddit": "Reddit"}


def site_name(key):
    base = key or ""
    for suffix in ("Tab", "Playlist", "Search", "Clip"):
        base = base.removesuffix(suffix)
    return _SITE_NAMES.get(base) or base or key


def find_url(text):
    """Pulls the first link out of shared text: apps often send 'title + link'."""
    m = re.search(r"https?://\S+", text or "")
    if m:
        return m.group(0)
    m = re.match(r"^\s*((?:[\w-]+\.)+[a-z]{2,}/\S+)", text or "", re.I)  # "youtube.com/watch?v=..." without a scheme
    return "https://" + m.group(1) if m else None


def _codec(v):
    return "none" if v in (None, "", "none") else v


def _num(v):
    return v if isinstance(v, (int, float)) and v > 0 else None


def parse_info(j, url, info_file=None):
    """yt-dlp's JSON answer -> the small dict the UI works with."""
    formats = [{
        "id": str(f.get("format_id", "")), "ext": f.get("ext") or "", "height": f.get("height") or None, "width": f.get("width") or None,
        "fps": f.get("fps"), "vcodec": _codec(f.get("vcodec")), "acodec": _codec(f.get("acodec")),
        "size": _num(f.get("filesize")) or _num(f.get("filesize_approx")), "tbr": _num(f.get("tbr")), "abr": _num(f.get("abr")),
    } for f in (j.get("formats") or [])]
    is_pl = j.get("_type") == "playlist"
    raw = j.get("entries") or []

    def last_thumb(d):
        ts = (d or {}).get("thumbnails") or []
        return ts[-1].get("url") if ts else None

    thumb = j.get("thumbnail") or last_thumb(j) or (last_thumb(raw[0]) if raw and raw[0] else None)
    entries = []
    if is_pl:
        for i, e in enumerate(raw, 1):
            if not e:
                continue
            u = e.get("url") or e.get("webpage_url")
            if u and not u.startswith("http") and e.get("ie_key") == "Youtube":
                u = "https://www.youtube.com/watch?v=" + u
            entries.append({"index": i, "title": model.clean_title(e.get("title") or f"Item {i}"), "url": u,
                            "duration": e.get("duration"), "thumbnail": e.get("thumbnail") or last_thumb(e)})
    date = j.get("upload_date") or ""
    return {
        "url": url, "kind": "playlist" if is_pl else "video",
        "title": model.clean_title(j.get("title") or "Untitled"), "uploader": j.get("uploader") or j.get("channel") or "",
        "thumbnail": thumb, "seconds": j.get("duration") or 0, "date": f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else None,
        "site": site_name(j.get("extractor_key") or j.get("extractor") or ""), "formats": formats,
        "playlist_count": (j.get("playlist_count") or len(raw)) if is_pl else 0, "entries": entries,
        "info_file": None if is_pl else info_file,  # playlist entries still need their own analysis
    }


def get_info(url):
    def attempt():
        code, out, err = _run(_base() + ["--dump-single-json", "--flat-playlist", "--no-warnings", url], 120)
        if code != 0:
            raise EngineError(_info_error(err))
        return out
    try:
        out = attempt()
    except EngineError as e:
        if "isn't supported" in str(e) or not cache_dir().exists():
            raise
        clear_cache()  # stale helper data is the usual cause of a failure
        out = attempt()
    d = cache_dir().parent / "info"
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.json"):
        if time.time() - old.stat().st_mtime > INFO_MAX_AGE:
            old.unlink(missing_ok=True)
    f = d / f"{hashlib.md5(url.encode()).hexdigest()[:10]}-{int(time.time())}.json"
    f.write_text(out, encoding="utf-8")
    return parse_info(json.loads(out), url, str(f))


def _info_error(err):
    msg = model.friendly_error(err)
    return "Couldn't read this link." if msg == "Download failed" else msg


def preview(url):
    """YouTube's oEmbed answers in well under a second; None for other sites (they wait for the full info)."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not (host.endswith("youtube.com") or host == "youtu.be"):
        return None
    api = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")
    with urllib.request.urlopen(api, timeout=5) as r:
        j = json.load(r)
    return {"title": model.clean_title(j.get("title") or "Untitled"), "uploader": j.get("author_name") or "",
            "thumbnail": j.get("thumbnail_url"), "site": "YouTube"}


# ---------------------------------------------------------------- downloading

_OF = re.compile(r"of\s+~?\s*([\d.]+\s*[KMGT]?i?B)")
_AT = re.compile(r"at\s+([\d.]+\s*[KMGT]?i?B/s)")
_ETA = re.compile(r"ETA\s+(\d+(?::\d+){1,2})")
_ERROR = re.compile(r"^ERROR:")


def _eta_seconds(text):
    secs = 0
    for p in text.split(":"):
        secs = secs * 60 + int(p)
    return secs


def kill_tree(proc):
    if proc.poll() is not None:
        return
    if WIN:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, creationflags=NO_WINDOW)
    else:
        proc.kill()


def run_download(url, o, out_dir, on_progress, on_proc, info_file=None, selection=None):
    """Runs yt-dlp once. Returns {files: [{path, index}], errors: {index: reason}, code, tail}.

    `selection` lists the playlist positions this run covers (used to attribute failures)."""
    files_txt = Path(tempfile.mkdtemp(prefix="md-")) / "files.txt"
    use_info = info_file and Path(info_file).exists() and time.time() - Path(info_file).stat().st_mtime < INFO_MAX_AGE and not o.playlist
    cmd = _base() + ["--newline", "--print-to-file", "after_move:%(playlist_index|0)s\t%(filepath)s", str(files_txt)]
    cmd += model.build_args(o, out_dir) + (["--load-info-json", info_file] if use_info else [url])
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            bufsize=1, creationflags=NO_WINDOW)
    on_proc(proc)
    tracker = model.ProgressTracker(o.mode, o.items or None)
    tail, errors = [], {}
    for line in proc.stdout:
        line = line.rstrip("\n")
        tail = (tail + [line])[-80:]
        if _ERROR.match(line):
            errors[tracker.playlist_index or 0] = model.friendly_error(line)
        frac = tracker.feed(line)
        if frac is not None:
            m_of, m_at, m_eta = _OF.search(line), _AT.search(line), _ETA.search(line)
            on_progress({"fraction": frac, "speed": m_at.group(1) if m_at else None, "total": m_of.group(1) if m_of else None,
                         "eta": _eta_seconds(m_eta.group(1)) if m_eta else 0, "item": tracker.item, "part": tracker.part})
    code = proc.wait()
    files = []
    if files_txt.exists():
        for ln in files_txt.read_text(encoding="utf-8", errors="replace").splitlines():
            idx, _, path = ln.partition("\t")
            if path and os.path.isfile(path):
                files.append({"path": path, "index": int(idx) if idx.isdigit() else 0})
    shutil.rmtree(files_txt.parent, ignore_errors=True)
    return {"files": files, "errors": errors, "code": code, "tail": "\n".join(tail)}
