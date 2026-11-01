"""Media MultiTool Desktop logo kit: the phone logo's parts in a laptop. Run: python build_kit.py final  (needs skia-python).
Glyph code is shared with ../build_kit.py (same monoline wordmark)."""
import math, os, sys
import skia

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

# ---------- path helpers ----------
def stroke(path, w, join=skia.Paint.kRound_Join):
    p = skia.Paint(Style=skia.Paint.kStroke_Style, StrokeWidth=w,
                   StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=join)
    out = skia.Path(); p.getFillPath(path, out); return out

def union(paths):
    acc = skia.Path()
    for p in paths: acc = skia.Op(acc, p, skia.PathOp.kUnion_PathOp)
    return acc

def diff(a, b): return skia.Op(a, b, skia.PathOp.kDifference_PathOp)

def poly(*pts):
    p = skia.Path(); p.moveTo(*pts[0])
    for q in pts[1:]: p.lineTo(*q)
    return p

def rrect(x, y, w, h, r): p = skia.Path(); p.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), r, r)); return p
def circle(cx, cy, r): return skia.Path.Circle(cx, cy, r)
def arc(cx, cy, r, start, sweep):
    p = skia.Path(); p.addArc(skia.Rect.MakeLTRB(cx - r, cy - r, cx + r, cy + r), start, sweep); return p

def transform(path, sx=1, tx=0, ty=0):
    m = skia.Matrix(); m.setScaleTranslate(sx, sx, tx, ty)
    out = skia.Path(path); out.transform(m); return out

def d_of(path):
    """skia path -> SVG path data; conics are split into quads."""
    f = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")
    d = []; it = skia.Path.Iter(path, False)
    while True:
        verb, pts = it.next()
        if verb == skia.Path.kDone_Verb: break
        if verb == skia.Path.kMove_Verb: d.append(f"M{f(pts[0].fX)} {f(pts[0].fY)}")
        elif verb == skia.Path.kLine_Verb: d.append(f"L{f(pts[1].fX)} {f(pts[1].fY)}")
        elif verb == skia.Path.kQuad_Verb: d.append(f"Q{f(pts[1].fX)} {f(pts[1].fY)} {f(pts[2].fX)} {f(pts[2].fY)}")
        elif verb == skia.Path.kCubic_Verb: d.append(f"C{f(pts[1].fX)} {f(pts[1].fY)} {f(pts[2].fX)} {f(pts[2].fY)} {f(pts[3].fX)} {f(pts[3].fY)}")
        elif verb == skia.Path.kConic_Verb:
            q = skia.Path.ConvertConicToQuads(pts[0], pts[1], pts[2], it.conicWeight(), 2)
            for i in range(1, len(q), 2): d.append(f"Q{f(q[i].fX)} {f(q[i].fY)} {f(q[i+1].fX)} {f(q[i+1].fY)}")
        elif verb == skia.Path.kClose_Verb: d.append("Z")
    return "".join(d)

# ---------- the mark (256 grid): the phone logo's parts (chevron, baseline pill, top slot) in a laptop ----------
def _content(cx, top, s, small):
    """The phone's chevron + baseline pill scaled by s; group top (outer edge) at `top`, centred on cx."""
    sw_c, sw_p = (32 if small else 26) * s, (30 if small else 24) * s
    half = 38 * s                                   # chevron half-width and depth (centre line)
    y0 = top + sw_c / 2
    chev = stroke(poly((cx - half, y0), (cx, y0 + half), (cx + half, y0)), sw_c)
    py = y0 + 80 * s
    return [chev, stroke(poly((cx - 26 * s, py), (cx + 26 * s, py)), sw_p)]

def _centred(path, cy=127):
    b = path.getBounds()
    return transform(path, 1, 128 - (b.left() + b.right()) / 2, cy - (b.top() + b.bottom()) / 2)

def symbol(small=False):
    lid = rrect(36, 52, 184, 136, 28)
    if small:   # <=32 px cut: no webcam slot, heavier strokes, bigger gap to the base
        holes = _content(128, 52 + 38, 0.86, True); gap, base_h = 12, 26
    else:
        holes = _content(128, 52 + 32, 0.8, False) + [rrect(128 - 14.4, 52 + 12, 28.8, 8.8, 4.4)]; gap, base_h = 10, 22
    base = rrect(12, 188 + gap, 232, base_h, base_h / 2)
    return _centred(union([diff(lid, union(holes)), base]))

# ---------- custom monoline wordmark (built from the mark's round-capped strokes) ----------
C, X, S = 110, 80, 17          # cap height, x-height, stroke
RO = (X - S) / 2               # bowl radius (stroke centre)
TOP, BOT = -C + S / 2, -S / 2  # stem ends so round caps land on cap line / baseline
XT = -X + S / 2

def ring(cx, cy): return diff(circle(cx, cy, RO + S / 2), circle(cx, cy, RO - S / 2))

def g_o(x): cx = x + X / 2; return [ring(cx, -X / 2)], X
def g_e(x):
    cx = x + X / 2
    return [stroke(arc(cx, -X / 2, RO, 42, 318), S), stroke(poly((cx - RO, -X / 2), (cx + RO, -X / 2)), S)], X
def g_bowl_stem(x, top):
    cx = x + X / 2
    return [ring(cx, -X / 2), stroke(poly((cx + RO, top), (cx + RO, BOT)), S)], X
def g_d(x): return g_bowl_stem(x, TOP)
def g_a(x): return g_bowl_stem(x, XT)
def g_u(x):
    cx = x + X / 2
    p = poly((cx - RO, XT), (cx - RO, -X / 2)); p.arcTo(skia.Rect.MakeLTRB(cx - RO, -X / 2 - RO, cx + RO, -X / 2 + RO), 180, -180, False)
    return [stroke(p, S), stroke(poly((cx + RO, XT), (cx + RO, BOT)), S)], X
def g_l(x): return [stroke(poly((x + S / 2, TOP), (x + S / 2, BOT)), S)], S
def g_i(x): return [stroke(poly((x + S / 2, XT), (x + S / 2, BOT)), S), circle(x + S / 2, -C + S / 2 + 1, S / 2 * 1.08)], S
def g_t(x):
    w = 50; sx = x + 18
    return [stroke(poly((sx, -C + 14 + S / 2), (sx, BOT)), S), stroke(poly((x + S / 2, XT), (x + w - S / 2, XT)), S)], w
def g_T(x):
    w = 82
    return [stroke(poly((x + S / 2, TOP), (x + w - S / 2, TOP)), S), stroke(poly((x + w / 2, TOP), (x + w / 2, BOT)), S)], w
def g_M(x):
    w = 104; l, r = x + S / 2, x + w - S / 2
    return [stroke(poly((l, BOT), (l, TOP), (x + w / 2, TOP + (w / 2 - S / 2) * math.sqrt(3)), (r, TOP), (r, BOT)), S)], w

GLYPH = dict(o=g_o, e=g_e, d=g_d, a=g_a, u=g_u, l=g_l, i=g_i, t=g_t, T=g_T, M=g_M)
ROUND_L, ROUND_R = set("oeda"), set("oe")
TRACK, SPACE = 19, 50
KERN = {("T", "o"): -16, ("t", "i"): -4, ("l", "t"): -2}

def wordmark(text="Media MultiTool"):
    parts, x, prev = [], 0, None
    for ch in text:
        if ch == " ": x += SPACE; prev = None; continue
        if prev:
            x += TRACK - (3 if ch in ROUND_L else 0) - (3 if prev in ROUND_R else 0) + KERN.get((prev, ch), 0)
        ps, w = GLYPH[ch](x); parts += ps; x += w; prev = ch
    return union(parts), x

# ---------- extra letters for "Desktop" (same monoline stroke S as the phone wordmark) ----------
def _oval(l, t, r, b): return skia.Rect.MakeLTRB(l, t, r, b)
def g_D(x):
    w = 98; R = (C - S) / 2; l = x + S / 2; rc = x + w - S / 2 - R
    p = poly((l, BOT), (l, TOP), (rc, TOP)); p.arcTo(_oval(rc - R, TOP, rc + R, BOT), 270, 180, False); p.lineTo(l, BOT); p.close()
    return [stroke(p, S)], w
def g_s(x):
    w = 60; rx = (w - S) / 2; cx = x + w / 2
    t, b = -X + S / 2, -S / 2; h = b - t; ry1 = h / 2 * 0.47; mid = t + 2 * ry1
    p = skia.Path(); p.arcTo(_oval(cx - rx, t, cx + rx, mid), 335, -245, True)
    p.arcTo(_oval(cx - rx, mid, cx + rx, b), 270, 245, False)
    return [stroke(p, S)], w
def g_k(x):
    w = 64; sx = x + S / 2; r = x + w - S / 2
    return [stroke(poly((sx, TOP), (sx, BOT)), S),
            stroke(poly((sx + 2, -X * 0.36), (r, XT)), S), stroke(poly((sx + 14, -X * 0.45), (r, BOT)), S)], w
def g_p(x):
    cx = x + X / 2
    return [ring(cx, -X / 2), stroke(poly((cx - RO, XT), (cx - RO, 16)), S)], X

GLYPH.update(D=g_D, s=g_s, k=g_k, p=g_p)
ROUND_L |= set("s"); ROUND_R |= set("Dsp")
KERN.update({("D", "e"): -1, ("s", "k"): 0, ("k", "t"): -4, ("t", "o"): -2})

# ---------- SVG writers ----------
INK, SILVER_TOP, SILVER_BOT, SILVER = "#0B0B0C", "#FFFFFF", "#B4B5BA", "#D1D2D6"
BG_TOP, BG_BOT = "#2A2B2E", "#050505"
def write(name, vb, body, title="Media MultiTool Desktop logo"):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}"><title>{title}</title>{body}</svg>\n')
def silver_grad(id_, y0, y1):
    return (f'<defs><linearGradient id="{id_}" x1="0" y1="{y0}" x2="0" y2="{y1}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{SILVER_TOP}"/><stop offset="1" stop-color="{SILVER_BOT}"/></linearGradient></defs>')
def fill(c, d): return f'<path fill="{c}" fill-rule="evenodd" d="{d}"/>'

sym, sym_s = symbol(), symbol(small=True)
D, DS = d_of(sym), d_of(sym_s)
bb = sym.getBounds(); SY0, SY1 = bb.top(), bb.bottom()           # y extent of the mark, for the silver gradient
write("mmd-symbol.svg", "0 0 256 256", fill(INK, D))
write("mmd-symbol-small.svg", "0 0 256 256", fill(INK, DS))
write("mmd-symbol-silver.svg", "0 0 256 256", silver_grad("s", SY0, SY1) + fill("url(#s)", D))

# Lockups
wm, wm_w = wordmark("Media MultiTool Desktop")
k = 0.74
wm_x = 244 + 44                                                  # laptop right edge + gap
WMD = d_of(transform(wm, k, wm_x, 124 + C * k / 2))
hx1 = wm_x + wm_w * k
hv = f"-4 {SY0 - 12:.0f} {hx1 + 20 + 4:.0f} {SY1 - SY0 + 24:.0f}"
write("mmd-horizontal.svg", hv, fill(INK, D) + fill(INK, WMD))
write("mmd-horizontal-silver-on-black.svg", hv,
      f'<rect x="-4" y="{SY0 - 12:.0f}" width="{hx1 + 24:.0f}" height="{SY1 - SY0 + 24:.0f}" fill="#000"/>' + silver_grad("s", SY0, SY1) + fill("url(#s)", D) + fill(SILVER, WMD))

# Stacked: laptop on top, "Media MultiTool" below it, "Desktop" smaller underneath
w1, w1w = wordmark("Media MultiTool"); w2, w2w = wordmark("Desktop")
k1, k2 = 0.62, 0.40
y1 = SY1 + 44 + C * k1; y2 = y1 + 30 + C * k2
p1 = transform(w1, k1, 128 - w1w * k1 / 2, y1); p2 = transform(w2, k2, 128 - w2w * k2 / 2, y2)
sv = f"{128 - w1w * k1 / 2 - 8:.0f} {SY0 - 12:.0f} {w1w * k1 + 16:.0f} {y2 + 8 - SY0 + 12:.0f}"
write("mmd-stacked.svg", sv, fill(INK, D) + fill(INK, d_of(p1)) + fill(INK, d_of(p2)))
write("mmd-wordmark.svg", f"0 0 {wm_w + 16:.0f} {C + 40}", fill(INK, d_of(transform(wm, 1, 8, C + 8))))

# App icon: the phone icon's dark gradient tile + silver mark. Full-bleed square, and a rounded tile for Windows.
def icon(name, mark, scale, rounded):
    b = mark.getBounds(); cy = (b.top() + b.bottom()) / 2; cx = (b.left() + b.right()) / 2
    p = d_of(transform(mark, scale, 128 - cx * scale, 128 - cy * scale))
    y0, y1 = 128 + (b.top() - cy) * scale, 128 + (b.bottom() - cy) * scale
    tile = f'<rect width="256" height="256" rx="{56 if rounded else 0}" fill="url(#bg)"/>'
    write(name, "0 0 256 256",
          f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOT}"/></linearGradient></defs>'
          + silver_grad("s", y0, y1) + tile + fill("url(#s)", p))
icon("mmd-app-icon.svg", sym, 0.84, False)
icon("mmd-app-icon-rounded.svg", sym, 0.84, True)
icon("mmd-app-icon-small-rounded.svg", sym_s, 0.92, True)
print("ok", round(wm_w))
