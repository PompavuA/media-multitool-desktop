"""Builds ui/index.html from the approved design/mockup.html: same markup and CSS, no demo bar, no fake title bar,
and a script tag instead of the mockup's fake data. Re-run it only if the mockup's markup/CSS is changed on purpose."""
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
s = (root / "design" / "mockup.html").read_text(encoding="utf-8")


def cut(pattern, repl="", flags=re.S):
    global s
    new, n = re.subn(pattern, repl, s, count=1, flags=flags)
    assert n == 1, pattern
    s = new


cut(r"<title>.*?</title>", '<title>Media MultiTool Desktop</title>\n<link rel="icon" type="image/svg+xml" href="img/app-icon.svg">')
# the real logo replaces the mockup's placeholder: the lockup (silver or ink by theme) when open, the app icon when folded
cut(r'<div class="brand">.*?<b class="appname"></b></div>',
    '<div class="brand"><img class="full dk" src="img/logo-horizontal-dark.svg" alt="Media MultiTool Desktop">'
    '<img class="full lt" src="img/logo-horizontal-light.svg" alt="Media MultiTool Desktop">'
    '<img class="tile" src="img/app-icon.svg" alt="" aria-hidden="true"></div>')
cut(r"/\* ============ demo bar.*?(?=/\* ============ window)")                      # demo bar CSS
cut(r'<div class="demo">.*?</div>\s*(?=<div class="stage">)')                         # demo bar markup
cut(r'<div class="titlebar">.*?</div>\s*</div>\s*(?=<div class="body">)')             # fake title bar (the real window has its own)
cut(r'<div class="foot">.*?</div>', '<div class="foot" id="foot"></div>')
cut(r'<span class="badge" id="qbadge">\d+</span>', '<span class="badge" id="qbadge" style="display:none"></span>')
cut(r"<script>.*</script>", '<script src="model.js"></script>\n<script src="app.js"></script>')
extra = """
/* ---- the real app (not the mockup): fills the window ---- */
body { padding: 0; overflow: hidden; }
.stage { display: block; }
.window { width: 100vw; height: 100vh; border-radius: 0; box-shadow: none; }
.thumb img, .job .th img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; z-index: 0; }
.thumb b { z-index: 2; }
.thumb::after { z-index: 1; }
.job .th { background-size: cover; }
.job .th.sp { display: grid; place-items: center; }
.spin.sm { width: 18px; height: 18px; border-width: 2px; }
.drop .linkbar { border-color: var(--text); box-shadow: 0 0 0 4px var(--ring); }
.setup { padding: 22px; display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
.setup h2 { font-size: 18px; margin: 0; }
.setup p { color: var(--muted); font-size: 13.5px; line-height: 1.55; max-width: 560px; }
.setup .prog { width: 100%; max-width: 420px; margin-top: 0; }

/* ---- window size: the content keeps a normal size and stays centred; only the sticky link bar runs the full width ---- */
:root { --gut: clamp(16px, 2.4vw, 26px); }
.view { padding-left: var(--gut); padding-right: var(--gut); }
#v-download { max-width: 980px; }
.topbar { margin: 0 calc(-1 * var(--gut)); padding-left: var(--gut); padding-right: var(--gut); background: none; backdrop-filter: none; -webkit-backdrop-filter: none; }
.topbar::before { content: ""; position: absolute; z-index: -1; top: 0; bottom: 0; left: calc(50% - 50cqw); width: 100cqw; background: var(--topbar);
  backdrop-filter: blur(24px) saturate(160%); -webkit-backdrop-filter: blur(24px) saturate(160%);
  -webkit-mask-image: linear-gradient(#000 calc(100% - 14px), transparent); mask-image: linear-gradient(#000 calc(100% - 14px), transparent); }
.resizing .topbar { background: none; }
/* the logo kit: lockup at 200 px or wider, as its rules ask, so the sidebar is a little wider than the mockup's */
.sidebar { width: 224px; }
.brand { position: relative; display: block; height: 44px; padding: 0; margin-bottom: 10px; }
.brand img { position: absolute; top: 50%; transform: translateY(-50%); transition: opacity .3s var(--ease); }
.brand .full { left: 0; width: 100%; height: auto; }
.brand .tile { left: 3px; width: 38px; height: 38px; opacity: 0; }
[data-theme="dark"] .brand .lt, [data-theme="light"] .brand .dk { display: none; }
.sb-collapsed .brand .full { opacity: 0; } .sb-collapsed .brand .tile { opacity: 1; }
/* the Download button: fill glides between the 0.6 s updates, text swaps softly, the check mark is drawn once */
.go .fill { transition: width .65s linear; }
.go b { font-variant-numeric: tabular-nums; }
.go .chk.still path { animation: none; stroke-dashoffset: 0; }
.go .swap { animation: gswap .32s var(--ease); }
@keyframes gswap { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.prog i { transition: width .65s linear; }
/* the (i) next to technical options */
.tip { display: inline-grid; place-items: center; vertical-align: -3px; margin-left: 7px; width: 15px; height: 15px; color: var(--faint); border-radius: 50%; cursor: help; transition: color .15s; }
.tip svg { width: 15px; height: 15px; stroke-width: 1.8; }
.tip:hover, .tip:focus-visible { color: var(--text); }
.tip:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
#tipbox { position: fixed; z-index: 120; max-width: 300px; padding: 9px 12px; border-radius: 10px; font-size: 12.5px; line-height: 1.45; color: var(--text); background: var(--menu-bg);
  backdrop-filter: blur(30px) saturate(180%); -webkit-backdrop-filter: blur(30px) saturate(180%); border: 1px solid var(--line2); box-shadow: 0 12px 34px rgba(0,0,0,.4);
  pointer-events: none; opacity: 0; transform: translateY(3px); transition: opacity .15s, transform .2s var(--ease); }
#tipbox.show { opacity: 1; transform: none; }
.resizing .topbar::before { backdrop-filter: none; -webkit-backdrop-filter: none; background: var(--topbar-solid); }
@container (min-width: 691px) { .dl-grid { grid-template-columns: minmax(0, 1fr) clamp(272px, 30%, 300px); } }
"""
cut(r"</style>", extra + "</style>")
(root / "ui" / "index.html").write_text(s, encoding="utf-8")
print("ui/index.html written", len(s), "bytes")
