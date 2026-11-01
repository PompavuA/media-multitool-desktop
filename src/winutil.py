"""Small Windows-only helpers: clipboard, Recycle Bin, Explorer, notifications, known folders."""
import ctypes
import html
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if WIN else 0

_FOLDER_IDS = {  # Windows known-folder GUIDs, so a redirected (OneDrive) Videos folder is respected
    "Videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}", "Music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "Pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
}


def known_folder(name, sub=""):
    path = None
    if WIN:
        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
        guid = GUID()
        buf = ctypes.c_wchar_p()
        try:
            ctypes.windll.ole32.CLSIDFromString(_FOLDER_IDS[name], ctypes.byref(guid))
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(buf)) == 0:
                path = buf.value
                ctypes.windll.ole32.CoTaskMemFree(buf)
        except Exception:
            path = None
    return str(Path(path or Path.home() / name) / sub) if sub else str(path or Path.home() / name)


def clipboard_text():
    """Plain text on the clipboard, or ''. Done with the Win32 API so the web view never asks for permission."""
    if not WIN:
        return ""
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    u.GetClipboardData.restype = wintypes.HANDLE
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = [wintypes.HANDLE]
    k.GlobalUnlock.argtypes = [wintypes.HANDLE]
    if not u.OpenClipboard(None):
        return ""
    try:
        h = u.GetClipboardData(13)  # CF_UNICODETEXT
        if not h:
            return ""
        p = k.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def recycle(paths):
    """Moves files to the Recycle Bin (undoable), never a permanent delete. Returns True if Windows did it."""
    if not WIN or not paths:
        return False

    class SHFILEOPSTRUCT(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR)]
    existing = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not existing:
        return True
    op = SHFILEOPSTRUCT()
    op.wFunc = 3                       # FO_DELETE
    op.pFrom = "\0".join(existing) + "\0\0"
    op.fFlags = 0x40 | 0x10 | 0x4 | 0x400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted


def reveal(path):
    """Opens Explorer with the file selected (or the folder if the file is gone)."""
    if not WIN:
        return
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)


def open_path(path):
    if WIN and os.path.exists(path):
        os.startfile(path)


APP_NAME = "Media MultiTool Desktop"
AUMID = "MediaDesktop.App"        # the identity Windows shows notifications under
ICON = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "ui" / "img" / "icon-256.png"

# The first lines give the app its own name and icon in Windows notifications (a per-user registry entry, no admin needed),
# so the notification says "Media MultiTool Desktop" instead of the program that happened to show it. This runs in PowerShell
# rather than in Python because the Microsoft Store build of Python redirects registry writes into a private hive.
_TOAST = r"""
$k = 'HKCU:\Software\Classes\AppUserModelId\' + $env:MD_AUMID
if (-not (Test-Path $k)) { New-Item -Path $k -Force | Out-Null }
Set-ItemProperty -Path $k -Name DisplayName -Value $env:MD_NAME
Set-ItemProperty -Path $k -Name IconUri -Value $env:MD_ICON
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml($env:MD_XML)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:MD_AUMID).Show([Windows.UI.Notifications.ToastNotification]::new($x))
"""


def toast_xml(title, text, open_target=None):
    """The notification's XML. Clicking it opens `open_target` (a file or folder) with its default program."""
    e = lambda s: html.escape(s or "", quote=True)
    launch = f' activationType="protocol" launch="{e(Path(open_target).as_uri())}"' if open_target else ""
    return (f'<toast{launch}><visual><binding template="ToastGeneric"><text>{e(title)[:120]}</text>'
            f'<text>{e(text)[:160]}</text></binding></visual></toast>')


def notify(title, text, open_target=None):
    """A Windows notification from Media MultiTool Desktop. Fire and forget; everything goes through the environment so no text can break the script."""
    if not WIN:
        return
    env = {**os.environ, "MD_AUMID": AUMID, "MD_NAME": APP_NAME, "MD_ICON": str(ICON), "MD_XML": toast_xml(title, text, open_target)}
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", _TOAST], env=env, creationflags=NO_WINDOW)
    except OSError:
        pass
