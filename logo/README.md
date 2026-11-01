# Media MultiTool Desktop — logo kit

**Idea:** the phone logo's download sign (chevron, baseline pill and top slot) on a laptop screen, with the base set apart like the pill. It's a sibling of the phone logo (`../final/`), so the two apps read as one family.

## Files (`final/`)

| Use | File |
|---|---|
| **Windows app icon** | `mmd-app-icon.ico` (16, 24, 32, 48, 64, 128, 256 px; the 16-32 px sizes use the heavier small cut) |
| App icon, rounded tile | `mmd-app-icon-rounded.svg`, `mmd-app-icon-small-rounded.svg`, `png/app-icon-1024.png`, `png/icon-<size>.png` |
| App icon, full-bleed square | `mmd-app-icon.svg` (for stores or masks that round it themselves) |
| Symbol, master | `mmd-symbol.svg` (+ `-black`, `-white`, `-silver`, `-square`, `-favicon`) |
| Symbol, 32 px and below | `mmd-symbol-small.svg`: no webcam slot, heavier strokes |
| Horizontal lockup | `mmd-horizontal.svg` (+ `-black`, `-white`, `-mono-d1d2d6`, `-silver-on-black`) |
| Stacked lockup | `mmd-stacked.svg` (+ `-black`, `-white`, `-mono-d1d2d6`) |
| Wordmark only | `mmd-wordmark.svg` (+ variants) |
| Web | `web/` holds favicon.ico, favicon.svg, PNG icons, webmanifest and `head-snippet.html` |
| PNG lockups | `png/*-1200.png` |

Every file is outlined paths, with no live text, fonts or filters. The lettering is the phone logo's custom monoline wordmark with four extra letters (D, s, k, p), so no font licence is needed. To change anything, edit `build_kit.py` and run `python build_kit.py final` (needs `skia-python`). It reuses the phone kit's glyph code (`../build_kit.py`).

## Colour

Same as the phone logo:

| Name | HEX | Use |
|---|---|---|
| Ink | `#0B0B0C` | Logo on light backgrounds |
| Silver | `#D1D2D6` | One-colour logo on dark backgrounds |
| Silver gradient | `#FFFFFF` → `#B4B5BA` (top to bottom) | The mark on the app icon only |
| Tile | `#2A2B2E` → `#050505` (diagonal) | App icon background |

## Rules

- **Clear space:** keep at least half the lid's height empty on every side.
- **Minimum size:** symbol 24 px (use the small cut at 32 px and below; 16 px still reads as a laptop but the chevron blurs); horizontal lockup 200 px wide; stacked lockup 120 px wide.
- **Backgrounds:** ink on white or light grey; silver or white on black or the app's dark gradient.
- **Don't:** stretch or rotate it, recolour it, add shadows or glows, retype the name in another font, put the chevron back on a stem, or use the phone and laptop marks in the same lockup.

## Notes

- The wordmark and lockups have many anchor points because the round letters are drawn with curves. That's normal for lettering.
- In the stacked lockup, "Desktop" sits under "Media MultiTool" at a smaller size. The two i-dots in the larger line are small, so don't use the stacked lockup below 120 px wide.
- Previews: `presentation.html` (slides in `slides/`) and `preview.html` (size and background tests). The concept sheet comparing the laptop with the monitor option is in `explore/`.
- The Windows app that would use this icon doesn't exist yet. When it does, point the build at `mmd-app-icon.ico`.
