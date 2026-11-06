#!/usr/bin/env python3
"""Check `plugin.toml` the way the installed OpenIDEA parses it.

`openidea-plugin check` is stricter than the IDE in no way, and it is *looser* in
one: it accepts 1.x-only keys (`categories`, `engines.openidea`) that a 0.1.x IDE
rejects outright with "unknown field". This script closes that gap — it encodes
the manifest rules from the IDE's own source, so a package that would fail to
install is caught here first.

Two rule sets are mixed on purpose, because this manifest is deliberately a 0.1
one installed on a 1.x IDE:

* top-level fields — the 0.1 set (`crates/ide-plugin/src/manifest.rs` at
  v0.1.32), so no 1.x-only key sneaks in. 1.x reads it as a legacy manifest.
* plugin id — the 1.x rule (`crates/ide-extension/src/manifest.rs` at v0.1.37):
  dot-separated segments, e.g. `acme.tools`. A dot is required to sign the
  package at all, since `pack --key` only signs `<publisher>.*`.

    python tools/check_manifest.py
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


_ID_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
_ID_FIRST = set("abcdefghijklmnopqrstuvwxyz0123456789")


def _segment_ok(s: str) -> bool:
    """Mirrors `segment_ok` in the 1.x manifest: starts alphanumeric, then -/_."""
    return bool(s) and s[0] in _ID_FIRST and all(c in _ID_CHARS for c in s)


def plugin_id_ok(pid: str) -> bool:
    """Mirrors `validate_plugin_id` in the 1.x manifest: `acme.tools` is valid."""
    return 0 < len(pid) <= 64 and bool(pid) and all(_segment_ok(seg) for seg in pid.split("."))


def main() -> int:
    problems: list[str] = []
    raw = tomllib.loads((ROOT / "plugin.toml").read_text(encoding="utf-8"))

    for key in raw:
        if key not in ALLOWED:
            problems.append(
                f"unknown field {key!r}: not in the 0.1 manifest the IDE reads. "
                f"Allowed: {', '.join(sorted(ALLOWED))}"
            )
    for key in REQUIRED:
        if key not in raw:
            problems.append(f"missing required field {key!r}")

    if "id" in raw and not plugin_id_ok(raw["id"]):
        problems.append(
            f"invalid plugin id {raw['id']!r}: use a-z, 0-9, '-', '_' in "
            f"'.'-separated parts (e.g. acme.tools), max 64"
        )
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
