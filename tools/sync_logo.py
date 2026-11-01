"""Copies the few logo files the app itself uses from the full kit (logo/final) into ui/img, which is what gets bundled.
Run it again whenever the kit changes:  python tools/sync_logo.py"""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
final, out = root / "logo" / "final", root / "ui" / "img"
out.mkdir(parents=True, exist_ok=True)

USED = {
    "mmd-horizontal-mono-d1d2d6.svg": "logo-horizontal-dark.svg",   # sidebar, dark theme (silver)
    "mmd-horizontal-black.svg": "logo-horizontal-light.svg",        # sidebar, light theme (ink)
    "mmd-app-icon-small-rounded.svg": "app-icon.svg",               # sidebar when folded, favicon
    "mmd-app-icon.ico": "app.ico",                                  # window and taskbar icon
    "png/icon-256.png": "icon-256.png",                             # Windows notifications
}
for src, name in USED.items():
    shutil.copyfile(final / src, out / name)
    print(f"{src} -> ui/img/{name}")
