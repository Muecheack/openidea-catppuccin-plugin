#!/usr/bin/env python3
"""Check `plugin.toml` against OpenIDEA's manifest format 0.1.

`openidea-plugin check` ships with a newer release and happily accepts 1.x-only
keys like `categories` and `engines.openidea`, but an installed OpenIDEA 0.1.x
rejects the whole package with "unknown field". This script encodes the 0.1
schema — `PluginManifest` in `crates/ide-plugin/src/manifest.rs` at v0.1.32 —
so that keys a 0.1.x IDE does not know are caught before installing.

    python tools/check_manifest.py

OpenIDEA 0.1.32 is the version this plugin targets. A 1.x IDE reads the same
manifest as legacy, so passing here is the narrower of the two requirements.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_VERSION = "0.1"

# `PluginManifest`, `#[serde(deny_unknown_fields)]`, kebab-case.
ALLOWED = {
    "id", "name", "version", "description", "authors", "homepage",
    "change-notes", "openidea-api", "wasm", "permissions", "contributes",
}
# Fields without `#[serde(default)]`.
REQUIRED = {"id", "name", "version", "openidea-api"}
# `Contribution` struct.
ALLOWED_CONTRIBUTES = {"commands", "languages", "themes"}
# `[[contributes.themes]]` (`ThemeDecl`).
ALLOWED_THEME_FIELDS = {"path", "editor-scheme"}
# `Permission` enum.
PERMISSIONS = {"project-read", "editor-read", "editor-write"}


def is_version(v: str) -> bool:
    core = re.split(r"[-+]", v)[0]
    parts = core.split(".")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def api_compatible(v: str) -> bool:
    return v == API_VERSION or v.startswith(API_VERSION + ".")


def main() -> int:
    problems: list[str] = []
    raw = tomllib.loads((ROOT / "plugin.toml").read_text(encoding="utf-8"))

    for key in raw:
        if key not in ALLOWED:
            problems.append(
                f"unknown field {key!r}: OpenIDEA 0.1.x rejects the install. "
                f"Allowed: {', '.join(sorted(ALLOWED))}"
            )
    for key in REQUIRED:
        if key not in raw:
            problems.append(f"missing required field {key!r}")

    if "id" in raw and not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", raw["id"]):
        problems.append(f"invalid plugin id {raw['id']!r}: use a-z, 0-9, '-', '_'")
    if "version" in raw and not is_version(raw["version"]):
        problems.append(f"version {raw['version']!r} must look like 1.2.3")
    if "openidea-api" in raw and not api_compatible(str(raw["openidea-api"])):
        problems.append(f"openidea-api {raw['openidea-api']!r} is not {API_VERSION}.x")

    for perm in raw.get("permissions", []):
        if perm not in PERMISSIONS:
            problems.append(f"unknown permission {perm!r}; use {', '.join(sorted(PERMISSIONS))}")

    contributes = raw.get("contributes", {})
    for point in contributes:
        if point not in ALLOWED_CONTRIBUTES:
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
            target = ROOT / rel
            if Path(rel).is_absolute() or ".." in Path(rel).parts:
                problems.append(f"contributes.themes[{i}].{field}: {rel!r} must be relative to the package")
            elif not target.is_file():
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
    print(f"ok: plugin.toml is manifest format {API_VERSION}, {len(themes)} themes, all files present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
