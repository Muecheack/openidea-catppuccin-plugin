#!/usr/bin/env python3
"""Check `plugin.toml` the way the OpenIDEA community registry parses it.

The IDE is lenient in places the registry is not, so "it installs" is not enough
for a package that will be listed. This encodes `plugin.toml` in manifest format
0.2 (`plugins/README.md` in the OpenIDEA repository, `RawManifest` in
`crates/ide-extension/src/manifest.rs`) plus the registry's own rules
(`scripts/registry.py` of `l0ng-ai/openidea-plugins`):

* only 0.2 keys — a 0.1 manifest still *installs*, but `openidea-plugin index`,
  which the registry runs, refuses it outright;
* the plugin id must be `<publisher>.<name>` so the publisher may sign it, and be
  dot-separated segments of `a-z0-9_-`;
* `categories` from the marketplace vocabulary, at most three.

    python tools/check_manifest.py
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# `RawManifest`, `#[serde(deny_unknown_fields)]`, kebab-case. 0.2 only.
ALLOWED = {
    "id", "name", "version", "description", "authors", "homepage", "license",
    "change-notes", "categories", "engines", "wasm", "activation",
    "capabilities", "contributes",
}
# Fields without `#[serde(default)]`.
REQUIRED = {"id", "name", "version", "engines"}
# `Contribution` points; a theme plugin uses `themes`.
KNOWN_POINTS = {
    "commands", "menus", "keymaps", "statusBar", "settings", "views",
    "customEditors", "themes", "fileIcons", "fileTemplates", "languages",
    "providers", "secrets", "runDetectors", "iconThemes",
}
# Marketplace categories (`plugins/README.md`), at most three.
CATEGORIES = {
    "languages", "themes", "icon-themes", "linters", "vcs", "ai",
    "frameworks", "tools", "other",
}
MAX_CATEGORIES = 3
ALLOWED_THEME_FIELDS = {"path", "editor-scheme"}

_ID_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
_ID_FIRST = set("abcdefghijklmnopqrstuvwxyz0123456789")


def _segment_ok(s: str) -> bool:
    return bool(s) and s[0] in _ID_FIRST and all(c in _ID_CHARS for c in s)


def plugin_id_ok(pid: str) -> bool:
    """`validate_plugin_id`: `acme.tools`, each part `[a-z0-9][a-z0-9_-]*`."""
    return 0 < len(pid) <= 64 and all(_segment_ok(seg) for seg in pid.split("."))


def is_version(v: str) -> bool:
    core = re.split(r"[-+]", v)[0]
    parts = core.split(".")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def engine_ok(req: str) -> bool:
    """The plugin API this package needs must accept the 1.x API."""
    return bool(re.match(r"^\s*(\^|>=|~)?\s*1(\.|$)", req))


def main() -> int:
    problems: list[str] = []
    raw = tomllib.loads((ROOT / "plugin.toml").read_text(encoding="utf-8"))

    for key in raw:
        if key not in ALLOWED:
            problems.append(
                f"unknown field {key!r}: not a 0.2 manifest key. "
                f"Allowed: {', '.join(sorted(ALLOWED))}"
            )
    for key in REQUIRED:
        if key not in raw:
            problems.append(f"missing required field {key!r}")
    if "openidea-api" in raw:
        problems.append(
            "`openidea-api` is the 0.1 format; `openidea-plugin index` refuses it. "
            "Use `engines.openidea`."
        )

    if "id" in raw and not plugin_id_ok(raw["id"]):
        problems.append(
            f"invalid plugin id {raw['id']!r}: use a-z, 0-9, '-', '_' in "
            f"'.'-separated parts (e.g. acme.tools), max 64"
        )
    if "version" in raw and not is_version(raw["version"]):
        problems.append(f"version {raw['version']!r} must look like 1.2.3")

    engines = raw.get("engines")
    if engines is not None:
        if not isinstance(engines, dict):
            problems.append("`engines` is a table")
        elif "openidea" not in engines:
            problems.append("`engines.openidea` is required, e.g. \"^1.0\"")
        elif not engine_ok(str(engines["openidea"])):
            problems.append(f"engines.openidea {engines['openidea']!r} does not accept API 1.x")

    cats = raw.get("categories", [])
    if not isinstance(cats, list) or not all(isinstance(c, str) for c in cats):
        problems.append("`categories` is a list of strings")
    else:
        unknown = [c for c in cats if c not in CATEGORIES]
        if unknown:
            problems.append(f"unknown categories {unknown}; use {', '.join(sorted(CATEGORIES))}")
        if len(cats) > MAX_CATEGORIES:
            problems.append(f"at most {MAX_CATEGORIES} categories, got {len(cats)}")

    contributes = raw.get("contributes", {})
    for point in contributes:
        if point not in KNOWN_POINTS:
            problems.append(f"unknown contribution point {point!r}")

    seen: set[str] = set()
    themes = contributes.get("themes", [])
    if not themes:
        problems.append("contributes no themes")

    for i, theme in enumerate(themes):
        for field in theme:
            if field not in ALLOWED_THEME_FIELDS:
                problems.append(f"contributes.themes[{i}]: unknown field {field!r}")
        for field in ("path", "editor-scheme"):
            rel = theme.get(field)
            if rel is None:
                continue
            if Path(rel).is_absolute() or ".." in Path(rel).parts:
                problems.append(f"contributes.themes[{i}].{field}: {rel!r} must stay inside the package")
            elif not (ROOT / rel).is_file():
                problems.append(f"contributes.themes[{i}].{field}: {rel!r} does not exist")
        path = theme.get("path")
        if path and (ROOT / path).is_file():
            try:
                doc = json.loads((ROOT / path).read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                problems.append(f"{path}: invalid JSON ({e})")
                continue
            tid = doc.get("id", "")
            if tid in seen:
                problems.append(f"{path}: duplicate theme id {tid!r}")
            seen.add(tid)
            if doc.get("kind") not in ("dark", "light"):
                problems.append(f"{path}: kind must be 'dark' or 'light', got {doc.get('kind')!r}")
            if not doc.get("tokens"):
                problems.append(f"{path}: empty tokens")

    for p in problems:
        print(f"FAIL {p}", file=sys.stderr)
    if problems:
        return 1
    print(f"ok: manifest 0.2, id {raw.get('id')!r}, {len(themes)} themes, all files present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
