#!/usr/bin/env python3
"""Generate the Catppuccin themes for OpenIDEA.

Reads `tools/palette.json` (the official Catppuccin palette, flavour by flavour)
and writes, for each of the four flavours:

    themes/catppuccin-<flavour>.theme.json    UI colours
    themes/catppuccin-<flavour>.scheme.json   syntax / editor / ANSI colours

The split mirrors IntelliJ's `.theme.json` + `.icls` pair: OpenIDEA merges the
scheme over the theme. Together the two files set all 224 themeable tokens.

    python tools/gen_themes.py            # regenerate the themes
    python tools/gen_themes.py --check    # verify, write nothing

Mapping rules come from Catppuccin's own style guide
(<https://github.com/catppuccin/catppuccin/blob/main/docs/style-guide.md>):
keywords are mauve, strings green, types yellow, numbers peach, comments
overlay 2, links blue, errors red, warnings yellow, cursor rosewater, and a
selection is overlay 2 at 20-30% opacity. Where OpenIDEA needs a shade the
palette does not have, the token is an `rgba()` blend of a palette colour so
that it still follows the flavour.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PALETTE = Path(__file__).resolve().parent / "palette.json"
THEMES = ROOT / "themes"

# The 117 UI tokens and 107 scheme tokens of docs/plugins/themes.md.
UI_COUNT = 117
SCHEME_COUNT = 107

# `is_safe_value` in crates/ide-host/src/plugins/theme.rs.
FORBIDDEN = ("url(", "image(", "@import", "expression(", ";", "{", "}", "<", ">", "\\")
MAX_VALUE_LEN = 256


class Pal:
    """One flavour of the palette, plus value helpers."""

    def __init__(self, flavour: str, data: dict) -> None:
        self.flavour = flavour
        self.dark: bool = data["dark"]
        self.name: str = data["name"]
        self._colors: dict[str, str] = data["colors"]
        self._ansi: dict[str, dict[str, str]] = data["ansi"]

    def c(self, name: str) -> str:
        """A palette colour as hex."""
        return self._colors[name]

    def rgb(self, name: str) -> str:
        """A palette colour as `r, g, b`."""
        h = self._colors[name].lstrip("#")
        return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"

    def rgba(self, name: str, alpha: float) -> str:
        """A palette colour at `alpha` opacity, for shades the palette lacks."""
        return f"rgba({self.rgb(name)}, {alpha:g})"

    def ansi(self, name: str, weight: str) -> str:
        return self._ansi[name][weight]


def ui_tokens(p: Pal) -> dict[str, str]:
    """The 117 UI tokens: surfaces, lines, text, accent, status, VCS, islands."""
    d = p.dark
    t: dict[str, str] = {}

    # Surfaces. The editor island sits on the frame, so `base` is the island and
    # the darker `mantle`/`crust` are the chrome around it, in both kinds.
    t["--bg-app"] = p.c("mantle")
    t["--bg-elev"] = p.c("surface0") if d else p.c("mantle")
    t["--bg-popup"] = p.c("surface0") if d else p.c("base")
    t["--bg-floating-toolbar"] = p.c("surface0") if d else p.c("base")
    t["--bg-hover"] = p.c("surface0")
    t["--bg-selected"] = p.c("surface1")
    t["--bg-selected-strong"] = p.c("surface2")
    t["--bg-current-line"] = p.rgba("text", 0.10)  # style guide: text at 10%
    t["--bg-debug-line"] = p.rgba("blue", 0.22)
    t["--bg-backdrop"] = p.c("mantle")
    t["--bg-input"] = p.c("base")

    # Lines
    t["--border"] = p.c("surface0")
    t["--border-popup"] = p.c("surface1")
    t["--border-strong"] = p.c("surface2")
    t["--border-window"] = p.c("surface1")
    t["--control-off"] = p.c("overlay0")

    # Text
    t["--fg-strong"] = p.c("text")
    t["--fg-emphasis"] = p.c("text")
    t["--fg"] = p.c("text")
    t["--fg-secondary"] = p.c("subtext1")
    t["--fg-muted"] = p.c("subtext0")
    t["--fg-subtle"] = p.c("overlay1")
    t["--fg-faint"] = p.c("overlay0")
    t["--fg-gutter"] = p.c("overlay0")
    t["--fg-icon"] = p.c("subtext1")

    # Accent
    t["--accent"] = p.c("mauve")
    t["--link"] = p.c("blue")
    t["--link-hover"] = p.c("lavender") if d else p.c("sapphire")

    # Charts
    t["--chart-series"] = p.c("peach")

    # Status
    t["--danger"] = p.c("red")
    t["--warning"] = p.c("yellow")
    t["--success"] = p.c("green")
    t["--db-connected"] = p.c("green")
    t["--db-connected-ring"] = p.rgba("green", 0.45)
    t["--info"] = p.c("blue")

    # Vcs
    t["--vcs-modified"] = p.c("blue")
    t["--vcs-added"] = p.c("green")
    t["--vcs-deleted"] = p.c("red")
    t["--vcs-untracked"] = p.c("teal")
    t["--vcs-ignored"] = p.c("overlay1")
    t["--vcs-conflict"] = p.c("maroon")
    t["--gutter-modified"] = p.c("sapphire")
    t["--gutter-added"] = p.c("green")
    t["--gutter-deleted"] = p.c("red")
    t["--diff-modified"] = p.rgba("blue", 0.18)
    t["--diff-inserted"] = p.rgba("green", 0.18)
    t["--diff-deleted"] = p.rgba("red", 0.18)

    # Shadows and window controls
    if d:
        t["--shadow-popup"] = "0 6px 20px rgba(0, 0, 0, 0.45)"
        t["--shadow-dialog"] = (
            "0 0 0 0.5px rgba(0, 0, 0, 0.6), 0 10px 24px rgba(0, 0, 0, 0.35), "
            "0 24px 72px rgba(0, 0, 0, 0.45)"
        )
        t["--shadow-tooltip"] = "0 4px 12px rgba(0, 0, 0, 0.4)"
        t["--shadow-balloon"] = "0 8px 24px rgba(0, 0, 0, 0.45)"
    else:
        t["--shadow-popup"] = "0 6px 20px rgba(0, 0, 0, 0.12)"
        t["--shadow-dialog"] = (
            "0 0 0 0.5px rgba(0, 0, 0, 0.1), 0 10px 24px rgba(0, 0, 0, 0.1), "
            "0 24px 72px rgba(0, 0, 0, 0.2)"
        )
        t["--shadow-tooltip"] = "0 4px 12px rgba(0, 0, 0, 0.12)"
        t["--shadow-balloon"] = "0 8px 24px rgba(0, 0, 0, 0.14)"
    t["--traffic-close"] = p.c("red")
    t["--traffic-close-border"] = p.c("maroon")
    t["--traffic-close-pressed"] = p.c("maroon")
    t["--traffic-glyph"] = p.c("crust")
    t["--traffic-off"] = p.c("surface1")
    t["--traffic-off-border"] = p.c("surface2")

    # Additive
    t["--bg-tooltip"] = p.c("surface0") if d else p.c("base")
    t["--fg-tooltip"] = p.c("text")
    t["--border-tooltip"] = p.c("surface1")
    t["--bg-control"] = p.c("surface0")
    t["--bg-control-hover"] = p.c("surface1")
    t["--bg-active"] = p.c("surface2")
    t["--bg-scrim"] = p.rgba("crust", 0.6) if d else p.rgba("crust", 0.35)
    t["--fg-on-accent"] = p.c("base")  # style guide: on accent is base

    # Islands contract
    t["--bg-frame"] = p.c("crust")
    t["--bg-island"] = p.c("base")
    t["--bg-stripe-hover"] = p.rgba("text", 0.09) if d else p.rgba("text", 0.07)
    t["--bg-stripe-selected"] = p.rgba("text", 0.16) if d else p.rgba("text", 0.12)
    t["--fg-stripe-selected-active"] = p.c("text") if d else p.c("base")
    t["--fg-stripe-label"] = p.c("subtext1")
    t["--bg-tab-selected"] = p.c("surface0") if d else p.c("base")
    t["--border-tab-selected"] = p.c("mauve")
    t["--bg-tab-selected-inactive"] = p.c("mantle")
    t["--border-tab-selected-inactive"] = p.c("surface1")
    t["--bg-tab-hover"] = p.rgba("text", 0.07) if d else p.rgba("text", 0.05)
    t["--border-editor-tabs"] = p.c("crust")
    t["--bg-tree-selected"] = p.c("surface1")
    t["--bg-tree-selected-inactive"] = p.c("surface0")
    t["--bg-tree-hover"] = p.rgba("text", 0.06)
    t["--bg-toolbar-hover"] = p.rgba("text", 0.09) if d else p.rgba("text", 0.07)
    t["--bg-toolbar-pressed"] = p.rgba("text", 0.16) if d else p.rgba("text", 0.12)
    t["--bg-toolbar-selected"] = p.rgba("mauve", 0.28) if d else p.rgba("mauve", 0.20)
    t["--bg-toolbar-selected-hover"] = p.rgba("mauve", 0.38) if d else p.rgba("mauve", 0.28)
    t["--bg-button-primary-hover"] = p.c("lavender")
    t["--fg-button-primary"] = p.c("base")
    t["--bg-button"] = "transparent"
    t["--border-button"] = p.c("surface1")
    t["--bg-field"] = p.c("base")
    t["--bg-checkbox"] = p.c("base")
    t["--border-checkbox"] = p.c("overlay0")
    t["--bg-toggle-on"] = p.c("green")
    t["--fg-toggle-on"] = p.c("base")
    t["--bg-toggle-off"] = p.c("mantle") if d else p.c("surface0")
    t["--fg-toggle-off"] = p.c("overlay0")
    t["--border-toggle"] = p.c("overlay0")
    t["--bg-toggle-knob"] = p.c("overlay0")
    t["--focus-ring-soft"] = p.rgba("mauve", 0.55)
    t["--scrollbar-thumb"] = p.rgba("text", 0.20)
    t["--scrollbar-thumb-hover"] = p.rgba("text", 0.35)
    # A dark flavour needs a solid highlight with dark text; a light one a tint.
    t["--bg-search-match"] = p.c("yellow") if d else p.rgba("yellow", 0.45)
    t["--bg-search-match-current"] = p.c("peach") if d else p.rgba("peach", 0.70)
    t["--fg-search-match"] = p.c("crust") if d else p.c("text")
    t["--bg-dialog"] = p.c("base")
    t["--bg-popup-inline"] = p.c("surface0") if d else p.c("mantle")
    t["--bg-popup-advertiser"] = p.c("surface0") if d else p.c("mantle")
    t["--bg-feedback-info"] = p.rgba("blue", 0.16)
    t["--border-feedback-info"] = p.rgba("blue", 0.45)
    t["--bg-feedback-error"] = p.rgba("red", 0.14)
    t["--border-feedback-error"] = p.rgba("red", 0.45)
    t["--bg-feedback-warning"] = p.rgba("yellow", 0.14)
    t["--border-feedback-warning"] = p.rgba("yellow", 0.45)
    t["--bg-feedback-success"] = p.rgba("green", 0.14)
    t["--border-feedback-success"] = p.rgba("green", 0.45)
    # A filled badge: `subtext 1` under `base` clears AA on all four flavours
    # (~5.2:1 on Latte, ~8.8:1 on Mocha), where `surface 2` under `text` did not.
    t["--bg-counter"] = p.c("subtext1")
    t["--fg-counter"] = p.c("base")
    t["--bg-progress-track"] = p.c("surface1") if d else p.c("surface0")

    return t


def scheme_tokens(p: Pal) -> dict[str, str]:
    """The 107 scheme tokens: syntax, editor surfaces and the ANSI palettes."""
    d = p.dark
    t: dict[str, str] = {}

    # Syntax, following the style guide's "Code Editors" table.
    t["--syn-keyword"] = p.c("mauve")
    t["--syn-string"] = p.c("green")
    t["--syn-type"] = p.c("yellow")
    t["--syn-function"] = p.c("blue")
    t["--syn-function-call"] = p.c("blue")
    t["--syn-comment"] = p.c("overlay2")
    t["--syn-comment-style"] = "italic"
    t["--syn-doc-comment"] = p.c("overlay1")
    t["--syn-docstring"] = p.c("green")
    t["--syn-annotation"] = p.c("yellow")
    t["--syn-decorator"] = p.c("yellow")
    t["--syn-number"] = p.c("peach")
    t["--syn-punct"] = p.c("overlay2")
    t["--syn-variable"] = p.c("text")
    t["--syn-global"] = p.c("text")
    t["--syn-param"] = p.c("maroon")
    t["--syn-property"] = p.c("blue")
    t["--syn-constant"] = p.c("peach")
    t["--syn-builtin"] = p.c("red")
    t["--syn-self"] = p.c("flamingo")
    t["--syn-keyword-arg"] = p.c("maroon")
    t["--syn-predefined"] = p.c("red")
    t["--syn-escape"] = p.c("pink")
    t["--syn-regexp"] = p.c("pink")
    t["--syn-tag"] = p.c("mauve")
    t["--syn-attribute"] = p.c("yellow")
    t["--syn-todo"] = p.c("peach")
    t["--syn-link"] = p.c("blue")
    t["--syn-markup-heading"] = p.c("mauve")
    t["--syn-markup-code"] = p.c("green")
    t["--syn-invalid"] = p.c("red")
    t["--syn-inline-value"] = p.c("overlay1")
    t["--syn-rainbow-1"] = p.c("teal")
    t["--syn-rainbow-2"] = p.c("peach")
    t["--syn-rainbow-3"] = p.c("yellow")
    t["--syn-rainbow-4"] = p.c("green")
    t["--syn-rainbow-5"] = p.c("pink")
    t["--syn-bracket-1"] = p.c("red")
    t["--syn-bracket-2"] = p.c("yellow")
    t["--syn-bracket-3"] = p.c("blue")

    # Editor
    t["--fg-editor"] = p.c("text")
    t["--caret"] = p.c("rosewater")  # style guide: cursor is rosewater
    t["--fg-line-number"] = p.c("overlay0")
    t["--fg-line-number-current"] = p.c("overlay1")
    t["--border-gutter"] = p.c("mantle")
    t["--border-indent-guide"] = p.c("surface0")
    t["--border-indent-guide-active"] = p.c("surface2")
    t["--border-right-margin"] = p.c("surface0")
    t["--bg-editor-selection"] = p.rgba("overlay2", 0.30) if d else p.rgba("overlay2", 0.25)
    t["--bg-editor-selection-inactive"] = p.rgba("overlay2", 0.16)
    t["--bg-text-search-result"] = p.rgba("yellow", 0.35)
    t["--bg-text-search-result-current"] = p.rgba("peach", 0.55)
    t["--bg-matched-brace"] = p.c("surface1")
    t["--matched-brace-weight"] = "700"
    t["--bg-matched-tag"] = p.c("surface0")
    t["--bg-fold-placeholder"] = p.c("surface0")
    t["--fg-fold-placeholder"] = p.c("overlay1")
    t["--fg-fold-marker"] = p.c("overlay0")
    t["--fg-whitespace"] = p.c("overlay0")
    t["--fg-unused"] = p.c("overlay0")
    t["--bg-identifier-under-caret"] = p.rgba("text", 0.08)
    t["--bg-identifier-under-caret-write"] = p.rgba("peach", 0.16)
    t["--fg-inlay"] = p.c("overlay1")
    t["--bg-inlay"] = p.c("surface0")
    t["--wave-error"] = p.c("red")
    t["--wave-warning"] = p.c("yellow")
    t["--editor-error-decoration"] = f"underline wavy {p.c('red')}"
    t["--editor-warning-decoration"] = f"underline wavy {p.c('yellow')}"
    t["--editor-warning-background"] = "transparent"
    t["--bg-breakpoint-line"] = p.rgba("red", 0.16)
    t["--fg-completion-match"] = p.c("mauve")
    t["--bg-editor-inline"] = p.c("surface0")
    t["--bg-editor-banner"] = p.rgba("blue", 0.16)
    t["--fg-weak-warning"] = p.c("overlay0")
    t["--fg-bulb"] = p.c("yellow")

    # ANSI palettes: terminal colours are the flavour's own ANSI set.
    for name in ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"):
        t[f"--ansi-{name}"] = p.ansi(name, "normal")
        t[f"--ansi-bright-{name}"] = p.ansi(name, "bright")
        t[f"--terminal-ansi-{name}"] = p.ansi(name, "normal")
        t[f"--terminal-ansi-bright-{name}"] = p.ansi(name, "bright")

    return t


TITLES = {
    "latte": "Catppuccin Latte",
    "frappe": "Catppuccin Frappé",
    "macchiato": "Catppuccin Macchiato",
    "mocha": "Catppuccin Mocha",
}


def build(flavour: str, data: dict) -> tuple[dict, dict]:
    p = Pal(flavour, data)
    tid = f"catppuccin-{flavour}"
    theme = {
        "id": tid,
        "name": TITLES[flavour],
        "kind": "dark" if p.dark else "light",
        "tokens": ui_tokens(p),
    }
    scheme = {"name": TITLES[flavour], "tokens": scheme_tokens(p)}
    return theme, scheme


def known_tokens() -> set[str] | None:
    """Token names OpenIDEA defines, as `pnpm gen:theme-docs` reads them.

    Returns None when the IDE checkout is not available, so the script still
    runs outside the repository.
    """
    candidates = [
        Path(__file__).resolve().parent / "tokens.txt",
        ROOT.parent / "openidea" / "src" / "styles" / "tokens.css",
    ]
    for path in candidates:
        if path.suffix == ".txt" and path.is_file():
            return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}
        if path.suffix == ".css" and path.is_file():
            return set(re.findall(r"(?m)^\s*(--[a-z0-9-]+)\s*:", path.read_text(encoding="utf-8")))
    return None


def problems(theme: dict, scheme: dict, known: set[str] | None) -> list[str]:
    out: list[str] = []

    for label, toks in (("theme", theme["tokens"]), ("scheme", scheme["tokens"])):
        for name, value in toks.items():
            if not re.fullmatch(r"--[a-z0-9][a-z0-9-]*", name) or len(name) > 64:
                out.append(f"{label}: bad token name {name!r}")
            low = value.lower()
            bad = [f for f in FORBIDDEN if f in low]
            if bad:
                out.append(f"{label}: {name} has a forbidden sequence {bad[0]!r}")
            if len(value) > MAX_VALUE_LEN or not value.strip():
                out.append(f"{label}: {name} has an unusable value {value!r}")
            if re.fullmatch(r"#[0-9a-fA-F]{3,8}", value) and value.lower() != value:
                out.append(f"{label}: {name} should be lower-case hex ({value})")
        if known:
            for name in toks:
                if name not in known:
                    out.append(f"{label}: {name} is not a token in tokens.css")

    expected = {"theme": UI_COUNT, "scheme": SCHEME_COUNT}
    for label, toks in (("theme", theme["tokens"]), ("scheme", scheme["tokens"])):
        if len(toks) != expected[label]:
            out.append(f"{label}: {len(toks)} tokens, expected {expected[label]}")

    overlap = set(theme["tokens"]) & set(scheme["tokens"])
    if overlap:
        out.append(f"tokens set in both theme and scheme: {sorted(overlap)}")

    return out


# --- Contrast ------------------------------------------------------------------
# The built-in themes keep text at WCAG AA (4.5:1); checked pairs the same way.

def _lum(hex_or_rgba: str) -> float | None:
    """Relative luminance of an opaque colour, or None for rgba/transparent."""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_or_rgba):
        return None
    h = hex_or_rgba.lstrip("#")
    vals = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        vals.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = vals
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float | None:
    a, b = _lum(fg), _lum(bg)
    if a is None or b is None:
        return None
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# Body text must clear WCAG AA. Failing one of these is a bug in the mapping.
STRICT_PAIRS = [
    ("--fg", "--bg-island"),
    ("--fg-emphasis", "--bg-island"),
    ("--fg-strong", "--bg-island"),
    ("--fg-secondary", "--bg-island"),
    ("--fg", "--bg-popup"),
    ("--fg-editor", "--bg-island"),
    ("--fg-tooltip", "--bg-tooltip"),
    ("--fg-button-primary", "--accent"),
    ("--fg-on-accent", "--accent"),
    ("--fg-search-match", "--bg-search-match"),
    ("--fg-counter", "--bg-counter"),
    ("--fg-stripe-label", "--bg-frame"),
    ("--fg", "--bg-frame"),
]

# De-emphasised text and the palette's own accent hues. Catppuccin Latte is
# inherently below 4.5:1 here (its yellow is 2.3:1 on its base), and a port
# that "fixed" it would no longer be Latte, so these are reported, not enforced.
DIM_PAIRS = [
    ("--fg-muted", "--bg-island"),
    ("--fg-subtle", "--bg-island"),
    ("--fg-faint", "--bg-island"),
    ("--link", "--bg-island"),
    ("--danger", "--bg-island"),
    ("--warning", "--bg-island"),
    ("--success", "--bg-island"),
    ("--syn-comment", "--bg-island"),
    ("--syn-keyword", "--bg-island"),
    ("--syn-string", "--bg-island"),
    ("--syn-number", "--bg-island"),
    ("--syn-function", "--bg-island"),
    ("--syn-type", "--bg-island"),
    ("--syn-variable", "--bg-island"),
    ("--syn-param", "--bg-island"),
    ("--syn-constant", "--bg-island"),
]


def contrast_report(theme: dict, scheme: dict) -> tuple[list[str], list[str]]:
    """(violations of AA for body text, informational sub-AA readings)."""
    toks = {**theme["tokens"], **scheme["tokens"]}
    strict, dim = [], []
    for pairs, out in ((STRICT_PAIRS, strict), (DIM_PAIRS, dim)):
        for fg, bg in pairs:
            ratio = contrast(toks.get(fg, ""), toks.get(bg, ""))
            if ratio is not None and ratio < 4.5:
                out.append(f"{theme['id']}: {fg} on {bg} is {ratio:.2f}:1")
    return strict, dim


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify only, write nothing")
    args = ap.parse_args()

    data = json.loads(PALETTE.read_text(encoding="utf-8"))
    known = known_tokens()
    if known is None:
        print("note: tokens.css not found, skipping the token-name check", file=sys.stderr)

    THEMES.mkdir(exist_ok=True)
    failures: list[str] = []
    notes: list[str] = []

    for flavour in ("latte", "frappe", "macchiato", "mocha"):
        theme, scheme = build(flavour, data[flavour])
        failures += problems(theme, scheme, known)
        strict, dim = contrast_report(theme, scheme)
        failures += [f"contrast: {s} (body text below AA)" for s in strict]
        notes += dim

        stem = f"catppuccin-{flavour}"
        for name, doc in ((f"{stem}.theme.json", theme), (f"{stem}.scheme.json", scheme)):
            path = THEMES / name
            text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
            if args.check:
                if not path.is_file() or path.read_text(encoding="utf-8") != text:
                    failures.append(f"{path.name} is out of date; run without --check")
            else:
                path.write_text(text, encoding="utf-8")
                print(f"wrote {path.relative_to(ROOT)} ({len(doc['tokens'])} tokens)")

    for n in notes:
        print(f"note: {n} — de-emphasised or palette hue, kept for fidelity", file=sys.stderr)
    if failures:
        for f in failures:
            print(f"FAIL {f}", file=sys.stderr)
        return 1
    print("ok: 4 flavours x 224 tokens, all tokens exist in tokens.css" if known
          else "ok: 4 flavours x 224 tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
