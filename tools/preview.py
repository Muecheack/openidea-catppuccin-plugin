#!/usr/bin/env python3
"""Render a preview of the four Catppuccin themes from the generated token files.

Draws a small mock of the IDE — frame, tool window, editor tabs, code with
syntax colours, current line, selection, popups and the status bar — reading
every colour from `themes/*.json`. It is a sanity check for the mapping, not
part of the plugin package.

    python tools/preview.py [--out preview.png]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
THEMES = ROOT / "themes"
FLAVOURS = ("latte", "frappe", "macchiato", "mocha")

WIN_W, WIN_H = 560, 392
GAP, PAD, LABEL_H = 18, 20, 26

UI_FONT = r"C:\Windows\Fonts\segoeui.ttf"
UI_FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
MONO_FONT = r"C:\Windows\Fonts\consola.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def load(flavour: str) -> dict[str, str]:
    theme = json.loads((THEMES / f"catppuccin-{flavour}.theme.json").read_text(encoding="utf-8"))
    scheme = json.loads((THEMES / f"catppuccin-{flavour}.scheme.json").read_text(encoding="utf-8"))
    toks = {**theme["tokens"], **scheme["tokens"]}
    toks["__title"] = theme["name"]
    toks["__kind"] = theme["kind"]
    return toks


def solid(value: str, fallback: str = "#ff00ff") -> str:
    """Opaque colours only: the mock has no alpha compositing."""
    return value if value.startswith("#") else fallback


def blend(value: str, under: str) -> str:
    """Flatten an rgba()/transparent value over `under`."""
    v = value.strip().lower()
    if v in ("transparent", "none", "inherit"):
        return under
    if v.startswith("#"):
        return v[:7] if len(v) > 7 else v
    if v.startswith("rgba(") or v.startswith("rgb("):
        nums = v[v.index("(") + 1 : v.rindex(")")].replace("/", ",").split(",")
        try:
            r, g, b = (int(float(n)) for n in nums[:3])
            a = float(nums[3]) if len(nums) > 3 else 1.0
        except ValueError:
            return under
        ur, ug, ub = (int(under[i : i + 2], 16) for i in (1, 3, 5))
        mix = lambda p, q: round(p * a + q * (1 - a))  # noqa: E731
        return f"#{mix(r, ur):02x}{mix(g, ug):02x}{mix(b, ub):02x}"
    return fallback_hint(value, under)


def fallback_hint(value: str, under: str) -> str:
    if "underline wavy" in value:
        return value.rsplit(" ", 1)[-1][:7]
    return under


# (text, token) segments per line; None keeps the default editor colour.
SEGMENTS: list[list[tuple[str, str | None]]] = [
    [("// Catppuccin for OpenIDEA", "--syn-comment")],
    [
        ("fn ", "--syn-keyword"),
        ("main", "--syn-function"),
        ("(", "--syn-punct"),
        (") ", "--syn-punct"),
        ("-> ", "--syn-punct"),
        ("Result", "--syn-type"),
        ("<", "--syn-punct"),
        ("()", "--syn-punct"),
        (", ", "--syn-punct"),
        ("Error", "--syn-type"),
        ("> {", "--syn-punct"),
    ],
    [
        ("    ", None),
        ("let ", "--syn-keyword"),
        ("name", "--syn-variable"),
        (" = ", "--syn-punct"),
        ('"world"', "--syn-string"),
        (";", "--syn-punct"),
    ],
    [
        ("    ", None),
        ("let ", "--syn-keyword"),
        ("n", "--syn-variable"),
        (" = ", "--syn-punct"),
        ("42", "--syn-number"),
        (";", "--syn-punct"),
    ],
    [
        ("    ", None),
        ("println!", "--syn-function-call"),
        ("(", "--syn-punct"),
        ('"hello {name} {n}"', "--syn-string"),
        (");", "--syn-punct"),
    ],
    [("    ", None), ("Ok", "--syn-function"), ("(())", "--syn-punct")],
    [("}", "--syn-punct")],
]


def render(t: dict[str, str]) -> Image.Image:
    img = Image.new("RGB", (WIN_W, WIN_H), solid(t["--bg-frame"]))
    d = ImageDraw.Draw(img)
    f_ui = font(UI_FONT, 12)
    f_bold = font(UI_FONT_BOLD, 12)
    f_mono = font(MONO_FONT, 12)

    frame = solid(t["--bg-frame"])
    island = solid(t["--bg-island"])
    line_bg = blend(t["--bg-current-line"], island)

    # Title bar + tool window stripe
    d.rectangle([0, 0, WIN_W, 26], fill=frame)
    d.text((12, 7), t["__title"], font=f_bold, fill=solid(t["--fg-strong"]))
    for i, ch in enumerate("‹ ›"):  # window controls
        d.text((WIN_W - 60 + i * 14, 7), ch, font=f_ui, fill=solid(t["--fg-subtle"]))
    stripe_x, stripe_w = 8, 40
    d.rounded_rectangle([stripe_x, 34, stripe_x + stripe_w, WIN_H - 34], 6, fill=frame)
    for i, glyph in enumerate(("▤", "⌕", "⑂", "⚙")):
        act = i == 0
        box = [stripe_x + 6, 44 + i * 34, stripe_x + stripe_w - 6, 74 + i * 34]
        if act:
            d.rounded_rectangle(box, 4, fill=blend(t["--bg-toolbar-selected"], frame))
        d.text((box[0] + 8, box[1] + 7), glyph, font=f_ui,
               fill=solid(t["--fg-stripe-selected-active"] if act else t["--fg-stripe-label"]))

    # Tool window
    tw = [stripe_x + stripe_w + 6, 34, stripe_x + stripe_w + 176, WIN_H - 34]
    d.rounded_rectangle(tw, 6, fill=island)
    d.text((tw[0] + 10, tw[1] + 8), "Project", font=f_bold, fill=solid(t["--fg-secondary"]))
    rows = ["▾ catppuccin", "  ▾ themes", "    latte", "    mocha", "  plugin.toml",
            "  tools", "  README.md"]
    for i, row in enumerate(rows):
        y = tw[1] + 30 + i * 21
        sel = i == 3
        if sel:
            d.rectangle([tw[0] + 4, y - 3, tw[2] - 4, y + 16], fill=blend(t["--bg-tree-selected"], island))
        elif i == 5:
            d.rectangle([tw[0] + 4, y - 3, tw[2] - 4, y + 16], fill=blend(t["--bg-tree-hover"], island))
        d.text((tw[0] + 10, y), row, font=f_ui,
               fill=solid(t["--fg"] if sel or i < 2 else t["--fg-secondary"]))

    # Editor
    ed = [tw[2] + 8, 34, WIN_W - 8, WIN_H - 34]
    d.rounded_rectangle(ed, 6, fill=island)

    # Tabs
    tab_h = 28
    tabs = ["catppuccin-mocha.theme.json", "lib.rs"]
    x = ed[0] + 4
    for i, name in enumerate(tabs):
        w = int(d.textlength(name, font=f_ui)) + 26
        box = [x, ed[1] + 4, x + w, ed[1] + 4 + tab_h]
        if i == 0:
            d.rounded_rectangle(box, 5, fill=blend(t["--bg-tab-selected"], island))
            d.line([box[0] + 6, box[3], box[2] - 6, box[3]],
                   fill=solid(t["--border-tab-selected"]), width=2)
        d.text((x + 12, ed[1] + 12), name, font=f_ui,
               fill=solid(t["--fg"] if i == 0 else t["--fg-muted"]))
        x += w + 2
    d.line([ed[0], ed[1] + 4 + tab_h + 2, ed[2], ed[1] + 4 + tab_h + 2],
           fill=solid(t["--border-editor-tabs"]))

    # Code
    top = ed[1] + 4 + tab_h + 10
    lh = 18
    gutter_w = 34
    for i in range(len(SEGMENTS)):
        y = top + i * lh
        if i == 3:  # current line
            d.rectangle([ed[0] + 2, y - 3, ed[2] - 2, y + lh - 4], fill=line_bg)
        d.text((ed[0] + 10, y), str(i + 1), font=f_mono, fill=solid(t["--fg-line-number"]))
    cursor_x = ed[0] + gutter_w + 8
    # Selection on line 5, behind its text.
    sy = top + 4 * lh
    sel = blend(t["--bg-editor-selection"], island)
    d.rectangle([ed[0] + gutter_w + 8, sy - 3, ed[0] + gutter_w + 168, sy + lh - 4], fill=sel)
    for i, segs in enumerate(SEGMENTS):
        y = top + i * lh
        x = ed[0] + gutter_w + 8
        for text, tok in segs:
            colour = solid(t[tok]) if tok else solid(t["--fg-editor"])
            d.text((x, y), text, font=f_mono, fill=colour)
            x += d.textlength(text, font=f_mono)
        if i == 2:
            d.rectangle([x, y - 1, x + 1, y + 13], fill=solid(t["--caret"]))

    # A popup over the editor
    pw, ph = 200, 54
    px, py = ed[2] - pw - 22, WIN_H - 34 - ph - 96
    d.rounded_rectangle([px, py, px + pw, py + ph], 5, fill=blend(t["--bg-popup"], island),
                        outline=solid(t["--border-popup"]))
    d.text((px + 10, py + 8), "Catppuccin: Apply theme", font=f_ui, fill=solid(t["--fg"]))
    d.text((px + 10, py + 26), "Mocha · 224 tokens", font=f_ui, fill=solid(t["--fg-muted"]))
    d.rounded_rectangle([px + 6, py + 6, px + pw - 6, py + 24], 4,
                        fill=blend(t["--bg-hover"], island))

    # Status bar
    d.rectangle([0, WIN_H - 26, WIN_W, WIN_H], fill=frame)
    d.text((14, WIN_H - 19), "main", font=f_ui, fill=solid(t["--fg-stripe-label"]))
    badge_w = 22
    bx = 70
    d.rounded_rectangle([bx, WIN_H - 21, bx + badge_w, WIN_H - 5], 7,
                        fill=solid(t["--bg-counter"]))
    d.text((bx + 8, WIN_H - 19), "0", font=f_ui, fill=solid(t["--fg-counter"]))
    d.text((WIN_W - 120, WIN_H - 19), "UTF-8  Rust", font=f_ui,
           fill=solid(t["--fg-stripe-label"]))
    d.text((WIN_W - 34, WIN_H - 19), "⚡", font=f_ui, fill=solid(t["--warning"]))
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "preview.png"))
    ap.add_argument("--scale", type=float, default=1.0)
    args = ap.parse_args()

    missing = [f for f in FLAVOURS if not (THEMES / f"catppuccin-{f}.theme.json").is_file()]
    if missing:
        print(f"missing themes for {missing}; run tools/gen_themes.py first", file=sys.stderr)
        return 1

    cols, rows = 2, 2
    cell_w, cell_h = WIN_W + GAP, WIN_H + LABEL_H + GAP
    sheet = Image.new("RGB", (PAD * 2 + cols * cell_w - GAP, PAD * 2 + rows * cell_h - GAP), "#0b0b0f")
    for i, flavour in enumerate(FLAVOURS):
        t = load(flavour)
        shot = render(t)
        cx = PAD + (i % cols) * cell_w
        cy = PAD + (i // cols) * cell_h
        ImageDraw.Draw(sheet).text((cx + 2, cy), f"{t['__title']}  ({t['__kind']})",
                                   font=font(UI_FONT_BOLD, 14), fill="#c9d1dc")
        sheet.paste(shot, (cx, cy + LABEL_H - 8))

    if args.scale != 1.0:
        sheet = sheet.resize(
            (int(sheet.width * args.scale), int(sheet.height * args.scale)), Image.LANCZOS
        )
    sheet.save(args.out)
    print(f"wrote {args.out} ({sheet.width}x{sheet.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
