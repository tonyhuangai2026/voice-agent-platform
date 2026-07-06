#!/usr/bin/env python3
"""One-shot migration: lift in-code SCENARIOS / KB_SCENARIOS into disk demos.

Purpose
-------
Phase out the in-code ``bot.SCENARIOS`` (default / sales / it-support /
interviewer / tutor) and ``bot.KB_SCENARIOS`` (acme-security-support) dicts so
that **every demo** is sourced from ``data/<id>/manifest.yaml`` and discovered
by :class:`demo_loader.DemoLoader`. After this script runs successfully, T4
can safely delete the in-code dicts from ``bot.py``.

What it does
~~~~~~~~~~~~
1. ``from bot import SCENARIOS, KB_SCENARIOS`` — read the live in-code
   structures (no source-text parsing).
2. For each of ``default / sales / it-support / interviewer / tutor`` write
   a ``data/<id>/manifest.yaml`` containing:

   - ``id``, ``label``, ``lang``, ``tags`` top-level fields.
   - ``system`` and ``greeting`` as **per-language dicts** (keys
     ``en-US / zh-CN / zh-HK / ja-JP``). Missing langs are filled by the
     fallback chain ``en-US → zh-CN → zh-HK → ja-JP → first non-empty``.
     Each fallback is annotated at the top of the file with a YAML comment
     ``# auto-fallback for ${lang}: from ${src}``.
   - ``tools: []`` — migration intentionally does NOT enable any tools by
     default; that is left to the admin UI.
3. For ``acme-security-support`` (KB_SCENARIOS): if ``data/acme-security-support/``
   already exists on disk it is **skipped** (avoids overwriting hand-edited
   manifest/kb). Otherwise a fresh manifest + kb.md is generated.
4. Archives the legacy Chinese-named ``data/acme-security-support/`` directory by **moving**
   it (not copying) to ``backups/_archive_haikang_<YYYYMMDD>/`` outside the
   data root, so DemoLoader no longer scans it.
5. Post-apply self-check: instantiate :class:`DemoLoader` and call
   :meth:`DemoLoader.rescan`; explicitly verify that the 7 ids
   ``default / sales / it-support / interviewer / tutor / it-helpdesk /
   acme-security-support`` are all present. Prints ``✅ demos: 7`` on success;
   ``exit 1`` if any id is missing.

CLI
~~~
::

    python scripts/migrate_demo_tools.py            # dry-run (default)
    python scripts/migrate_demo_tools.py --apply    # actually write files

Idempotency
-----------
Re-running ``--apply`` is safe. For each target ``manifest.yaml``:

- if it does not exist → write it.
- if it exists with byte-identical content → print ``skip(unchanged)``,
  do NOT touch the file, do NOT create a new ``.bak``.
- if it exists with different content → first copy to
  ``manifest.yaml.bak.YYYYMMDD`` (overwriting any same-day bak from a
  previous run is fine), then write the new content.

The ``data/acme-security-support/`` archival step is also idempotent: once the directory is
moved out of ``data/``, subsequent runs see no source dir to archive and
print ``skip (already archived)``.

YAML round-trip
---------------
Uses ``ruamel.yaml`` (round-trip mode) so we can prepend leading comments
and so future hand edits to the manifest preserve their formatting when
loaded by other tools.

Git note
--------
The script is intentionally idempotent so it can live in-tree and be
re-run after future schema changes (e.g. to back-fill a new field across
all generated demos). It is not invoked at runtime.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import logging
import os
import shutil
import sys
from typing import Any

# Make the project root importable so ``import bot`` and ``import demo_loader``
# resolve regardless of cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ruamel.yaml import YAML  # noqa: E402  (after sys.path tweak)
from ruamel.yaml.comments import CommentedMap  # noqa: E402

logger = logging.getLogger("migrate_demo_tools")


# --- constants --------------------------------------------------------------

DATA_ROOT = os.path.join(_PROJECT_ROOT, "data")
BACKUPS_ROOT = os.path.join(_PROJECT_ROOT, "backups")
LANGS = ("en-US", "zh-CN", "zh-HK", "ja-JP")
# Fallback order used when a language is missing from a SCENARIOS / KB_SCENARIOS
# entry. en-US first (broadest reach), then the two Chinese variants, then
# Japanese, then "first non-empty whatever is left" as a last resort.
FALLBACK_ORDER = ("en-US", "zh-CN", "zh-HK", "ja-JP")
EXPECTED_DEMO_IDS = (
    "default",
    "sales",
    "it-support",
    "interviewer",
    "tutor",
    "it-helpdesk",
    "acme-security-support",
)

# Per-id label + tags. Labels are user-facing in the admin UI; tags are
# free-form taxonomy used for filtering.
DEMO_META: dict[str, dict[str, Any]] = {
    "default": {
        "label": "Default (friendly assistant)",
        "lang": "en-US",
        "tags": ["default", "generic"],
    },
    "sales": {
        "label": "Sales / Customer Service",
        "lang": "en-US",
        "tags": ["sales", "customer-service"],
    },
    "it-support": {
        "label": "IT Support / Helpdesk",
        "lang": "en-US",
        "tags": ["it-support", "helpdesk"],
    },
    "interviewer": {
        "label": "Interviewer (mock interview)",
        "lang": "en-US",
        "tags": ["interview", "hiring"],
    },
    "tutor": {
        "label": "Language Tutor",
        "lang": "en-US",
        "tags": ["tutor", "language-learning"],
    },
    "acme-security-support": {
        "label": "ACME Security Tech Support",
        "lang": "zh-HK",
        "tags": ["tech-support", "kb"],
    },
}


# --- helpers ----------------------------------------------------------------


def _yaml() -> YAML:
    """Return a ruamel.yaml instance configured for human-friendly round-trip."""
    y = YAML()
    y.preserve_quotes = True
    y.width = 100
    y.indent(mapping=2, sequence=4, offset=2)
    y.allow_unicode = True
    return y


def _today_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d")


def _resolve_language_default(lang: str) -> tuple[str, str]:
    """Return ``(system, greeting)`` from ``bot.LANGUAGES[lang]``.

    The in-code ``default`` scenario stores an empty ``prompts`` dict and
    relies on per-language defaults from ``bot.LANGUAGES``. We mirror that
    fallback explicitly so the on-disk manifest still has a non-empty value
    for every lang.
    """
    import bot  # noqa: WPS433  (deferred import: heavy)

    entry = bot.LANGUAGES.get(lang) or {}
    return (entry.get("prompt", "") or "", entry.get("greeting", "") or "")


def _scenario_to_lang_pairs(prompts: dict[str, dict]) -> dict[str, dict[str, str]]:
    """Convert ``SCENARIOS[id]['prompts']`` to ``{lang: {system, greeting}}``.

    Empty / missing langs are *not* filled here; that's what the fallback
    pass does. We just keep what the source actually declared.
    """
    out: dict[str, dict[str, str]] = {}
    for lang, kv in (prompts or {}).items():
        if not isinstance(kv, dict):
            continue
        sys_v = (kv.get("system") or "").strip()
        greet_v = (kv.get("greeting") or "").strip()
        if not sys_v and not greet_v:
            continue
        out[lang] = {"system": sys_v, "greeting": greet_v}
    return out


def _fill_with_fallback(
    pairs: dict[str, dict[str, str]],
    *,
    lang_defaults: dict[str, tuple[str, str]] | None = None,
) -> tuple[dict[str, str], dict[str, str], list[tuple[str, str]]]:
    """Return ``(system_map, greeting_map, fallback_notes)``.

    Every key in :data:`LANGS` will be present in both returned maps.
    ``fallback_notes`` is a list of ``(lang, src_lang)`` for langs that were
    not present in the source and had to be filled.

    ``lang_defaults`` lets callers (only ``default`` scenario today) provide
    a per-language baseline (from ``bot.LANGUAGES``) BEFORE the cross-lang
    fallback chain kicks in. That prevents the final ``default`` manifest
    from having all 4 langs collapsed to one English string.
    """
    system_map: dict[str, str] = {}
    greeting_map: dict[str, str] = {}
    notes: list[tuple[str, str]] = []

    # Layer 0: per-language defaults from bot.LANGUAGES (only for the
    # ``default`` demo). These are NOT marked as fallbacks because they are
    # the legitimate per-lang values for that demo.
    if lang_defaults:
        for lang, (sys_v, greet_v) in lang_defaults.items():
            if sys_v or greet_v:
                system_map[lang] = sys_v
                greeting_map[lang] = greet_v

    # Layer 1: explicit values from the source pairs override layer 0.
    for lang, kv in pairs.items():
        if kv.get("system"):
            system_map[lang] = kv["system"]
        if kv.get("greeting"):
            greeting_map[lang] = kv["greeting"]

    # Layer 2: cross-lang fallback for any LANG still missing system OR
    # greeting. The fallback chain (en-US → zh-CN → zh-HK → ja-JP → first
    # non-empty) consults **original** non-empty values only — not values
    # already filled in by an earlier fallback step. This guarantees the
    # `from <src>` annotation credits the ultimate human-authored source
    # (e.g. zh-HK only ⇒ ja-JP gets ``from zh-HK``, not ``from en-US``).
    original_sys = dict(system_map)
    original_greet = dict(greeting_map)

    def _pick(target_lang: str, source_map: dict[str, str]) -> tuple[str, str] | None:
        # Walk the explicit fallback order first.
        for src in FALLBACK_ORDER:
            if src == target_lang:
                continue
            if source_map.get(src):
                return source_map[src], src
        # Then any non-empty entry as last resort.
        for src, val in source_map.items():
            if src == target_lang:
                continue
            if val:
                return val, src
        return None

    for lang in LANGS:
        sys_missing = not system_map.get(lang)
        greet_missing = not greeting_map.get(lang)
        if not sys_missing and not greet_missing:
            continue
        # Pick a single source lang to credit for this fallback (use the
        # one that supplies the system text; if only greeting is missing,
        # use the greeting source). We record one note per missing lang.
        src_lang: str | None = None
        if sys_missing:
            picked = _pick(lang, original_sys)
            if picked is None:
                # No source has a non-empty system at all — leave blank.
                continue
            system_map[lang], src_lang = picked
        if greet_missing:
            picked = _pick(lang, original_greet)
            if picked is not None:
                greeting_map[lang], src_pg = picked
                src_lang = src_lang or src_pg
        if src_lang and src_lang != lang:
            notes.append((lang, src_lang))

    return system_map, greeting_map, notes


def _build_manifest_yaml(
    *,
    demo_id: str,
    label: str,
    lang: str,
    tags: list[str],
    system_map: dict[str, str],
    greeting_map: dict[str, str],
    fallback_notes: list[tuple[str, str]],
    kb_path: str | dict[str, str] | None = None,
    kb_intro_map: dict[str, str] | None = None,
    kb_ack_map: dict[str, str] | None = None,
) -> bytes:
    """Render a manifest.yaml file as bytes (UTF-8).

    Header is a multi-line comment block (purpose + auto-fallback notes,
    if any). Body is the round-tripped YAML mapping.
    """
    y = _yaml()
    doc = CommentedMap()
    doc["id"] = demo_id
    doc["label"] = label
    doc["lang"] = lang
    doc["tags"] = list(tags)
    doc["tools"] = []  # T3: never enable tools by default; admin UI does it.
    if kb_path is not None:
        doc["kb_path"] = kb_path
    sys_cm = CommentedMap()
    for lk in LANGS:
        sys_cm[lk] = _scalar_block(system_map.get(lk, ""))
    doc["system"] = sys_cm
    greet_cm = CommentedMap()
    for lk in LANGS:
        greet_cm[lk] = _scalar_block(greeting_map.get(lk, ""))
    doc["greeting"] = greet_cm
    if kb_intro_map:
        intro_cm = CommentedMap()
        for lk in LANGS:
            v = kb_intro_map.get(lk, "")
            if v:
                intro_cm[lk] = _scalar_block(v)
        if intro_cm:
            doc["kb_intro"] = intro_cm
    if kb_ack_map:
        ack_cm = CommentedMap()
        for lk in LANGS:
            v = kb_ack_map.get(lk, "")
            if v:
                ack_cm[lk] = v
        if ack_cm:
            doc["kb_ack"] = ack_cm

    buf = io.StringIO()
    # Manual header comment block (ruamel's start_comment APIs are awkward
    # for multi-line headers across different versions — emitting it as
    # raw text before the dump is reliable).
    header_lines = [
        f"# Auto-generated by scripts/migrate_demo_tools.py",
        f"# Demo id: {demo_id}",
        f"# tools: [] — empty by default; flip via admin UI Demos > Tools tab.",
    ]
    for lang_, src in fallback_notes:
        header_lines.append(f"# auto-fallback for {lang_}: from {src}")
    buf.write("\n".join(header_lines))
    buf.write("\n")
    y.dump(doc, buf)
    return buf.getvalue().encode("utf-8")


def _scalar_block(text: str):
    """Return a YAML literal-block scalar when ``text`` has newlines, else plain.

    Long multi-line system prompts read better as ``|`` blocks; short
    one-liners (greetings) stay inline. ruamel.yaml's PreservedScalarString
    forces the literal-block style.
    """
    from ruamel.yaml.scalarstring import (  # noqa: WPS433  (per-call import is fine)
        LiteralScalarString,
        PlainScalarString,
    )

    if not text:
        return ""
    if "\n" in text:
        # Force trailing newline so ``|`` block round-trips cleanly.
        if not text.endswith("\n"):
            text = text + "\n"
        return LiteralScalarString(text)
    return PlainScalarString(text)


# --- per-id manifest assembly ----------------------------------------------


def _assemble_scenario_manifest(demo_id: str, scenario: dict) -> bytes:
    """Build one of the 5 SCENARIOS-derived manifests."""
    meta = DEMO_META[demo_id]
    pairs = _scenario_to_lang_pairs(scenario.get("prompts", {}))

    # Special-case: ``default`` scenario has empty prompts and relies on
    # bot.LANGUAGES per-lang defaults. Pre-seed those so each lang gets
    # its real default rather than an English fallback.
    lang_defaults = None
    if demo_id == "default":
        lang_defaults = {lang: _resolve_language_default(lang) for lang in LANGS}

    sys_map, greet_map, notes = _fill_with_fallback(pairs, lang_defaults=lang_defaults)
    return _build_manifest_yaml(
        demo_id=demo_id,
        label=scenario.get("label") or meta["label"],
        lang=meta["lang"],
        tags=meta["tags"],
        system_map=sys_map,
        greeting_map=greet_map,
        fallback_notes=notes,
        kb_path=None,  # SCENARIOS-derived demos have no KB.
    )


def _assemble_kb_manifest(demo_id: str, kb_scenario: dict) -> tuple[bytes, str]:
    """Build acme-security-support manifest + return ``(yaml_bytes, kb_body)``."""
    meta = DEMO_META[demo_id]
    sys_dict = kb_scenario.get("system") or {}
    greet_dict = kb_scenario.get("greeting") or {}
    intro_dict = kb_scenario.get("kb_intro") or {}
    ack_dict = kb_scenario.get("kb_ack") or {}

    pairs: dict[str, dict[str, str]] = {}
    for lang in LANGS:
        s = (sys_dict.get(lang) or "").strip()
        g = (greet_dict.get(lang) or "").strip()
        if s or g:
            pairs[lang] = {"system": s, "greeting": g}

    sys_map, greet_map, notes = _fill_with_fallback(pairs)

    # KB body: read from data/acme-security-support/kb.md before archival, fall back
    # to whatever path the in-code KB_SCENARIOS specified.
    kb_body = ""
    kb_path_in_code = kb_scenario.get("kb_path")
    if kb_path_in_code:
        full = os.path.join(_PROJECT_ROOT, kb_path_in_code)
        if os.path.isfile(full):
            with open(full, "r", encoding="utf-8") as f:
                kb_body = f.read()

    yaml_bytes = _build_manifest_yaml(
        demo_id=demo_id,
        label=kb_scenario.get("label") or meta["label"],
        lang=meta["lang"],
        tags=meta["tags"],
        system_map=sys_map,
        greeting_map=greet_map,
        fallback_notes=notes,
        kb_path="kb.md",
        kb_intro_map=intro_dict,
        kb_ack_map=ack_dict,
    )
    return yaml_bytes, kb_body


# --- write / archive primitives --------------------------------------------


def _write_manifest(target_dir: str, content: bytes, *, apply: bool) -> str:
    """Write manifest.yaml at ``target_dir``. Returns one of:
    ``written`` / ``skip(unchanged)`` / ``would-write`` / ``would-skip``.
    Backs up an existing differing file to ``.bak.YYYYMMDD`` (apply mode)."""
    manifest_path = os.path.join(target_dir, "manifest.yaml")
    existing: bytes | None = None
    if os.path.isfile(manifest_path):
        with open(manifest_path, "rb") as f:
            existing = f.read()
    if existing == content:
        return "skip(unchanged)" if apply else "would-skip(unchanged)"
    if not apply:
        return "would-write"

    os.makedirs(target_dir, exist_ok=True)
    if existing is not None:
        bak = f"{manifest_path}.bak.{_today_stamp()}"
        # Only create the bak if it doesn't already exist — otherwise we'd
        # clobber an earlier same-day backup with the now-current file (which
        # is exactly what we *don't* want during repeated migrations).
        if not os.path.isfile(bak):
            shutil.copy2(manifest_path, bak)
    with open(manifest_path, "wb") as f:
        f.write(content)
    return "written"


def _write_kb(target_dir: str, kb_body: str, *, apply: bool) -> str:
    kb_path = os.path.join(target_dir, "kb.md")
    new_bytes = (kb_body or "").encode("utf-8")
    existing: bytes | None = None
    if os.path.isfile(kb_path):
        with open(kb_path, "rb") as f:
            existing = f.read()
    if existing == new_bytes:
        return "skip(unchanged)" if apply else "would-skip(unchanged)"
    if not apply:
        return "would-write-kb"
    os.makedirs(target_dir, exist_ok=True)
    if existing is not None:
        bak = f"{kb_path}.bak.{_today_stamp()}"
        if not os.path.isfile(bak):
            shutil.copy2(kb_path, bak)
    with open(kb_path, "wb") as f:
        f.write(new_bytes)
    return "written"


def _archive_haikang(*, apply: bool) -> str:
    """Move ``data/acme-security-support/`` to ``backups/_archive_haikang_<ts>/``.

    Returns the destination path (or a ``skip`` marker). Idempotent: once
    moved, subsequent runs see no source dir and short-circuit.
    """
    src = os.path.join(DATA_ROOT, "ACME 安防")
    if not os.path.isdir(src):
        return "skip (already archived or never existed)"
    dst_dir = os.path.join(BACKUPS_ROOT, f"_archive_haikang_{_today_stamp()}")
    if not apply:
        return f"would-archive -> {dst_dir}"
    os.makedirs(BACKUPS_ROOT, exist_ok=True)
    # If a prior same-day archive already exists, append a counter so we
    # never overwrite real data.
    final_dst = dst_dir
    counter = 1
    while os.path.exists(final_dst):
        final_dst = f"{dst_dir}_{counter}"
        counter += 1
    shutil.move(src, final_dst)
    return final_dst


# --- main flow --------------------------------------------------------------


def _run(apply: bool) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[migrate_demo_tools] mode={mode}")
    print(f"[migrate_demo_tools] data root: {DATA_ROOT}")

    # ---- 1. import live in-code dicts -------------------------------------
    from bot import SCENARIOS, KB_SCENARIOS  # noqa: WPS433

    # ---- 2. write 5 SCENARIOS-derived demos -------------------------------
    written: list[str] = []
    skipped: list[str] = []
    target_ids = ("default", "sales", "it-support", "interviewer", "tutor")
    for demo_id in target_ids:
        scenario = SCENARIOS.get(demo_id)
        if scenario is None:
            print(f"  ! SCENARIOS missing id={demo_id}; refusing to fabricate")
            return 2
        target_dir = os.path.join(DATA_ROOT, demo_id)
        manifest_bytes = _assemble_scenario_manifest(demo_id, scenario)
        result = _write_manifest(target_dir, manifest_bytes, apply=apply)
        rel = os.path.relpath(os.path.join(target_dir, "manifest.yaml"), _PROJECT_ROOT)
        print(f"  [{result:>22}] {rel}")
        if "written" in result:
            written.append(rel)
        elif "skip" in result:
            skipped.append(rel)

    # ---- 3. acme-security-support: only generate if dir absent ----------------
    hikv_dir = os.path.join(DATA_ROOT, "acme-security-support")
    if os.path.isdir(hikv_dir):
        print(f"  [{'skip(dir-exists)':>22}] data/acme-security-support/  "
              "— preserving existing manifest + kb")
    else:
        kb_scenario = KB_SCENARIOS.get("acme-security-support")
        if kb_scenario is None:
            print("  ! KB_SCENARIOS missing acme-security-support; cannot generate")
            return 2
        manifest_bytes, kb_body = _assemble_kb_manifest("acme-security-support", kb_scenario)
        m_result = _write_manifest(hikv_dir, manifest_bytes, apply=apply)
        kb_result = _write_kb(hikv_dir, kb_body, apply=apply)
        print(f"  [{m_result:>22}] data/acme-security-support/manifest.yaml")
        print(f"  [{kb_result:>22}] data/acme-security-support/kb.md")
        if "written" in m_result:
            written.append("data/acme-security-support/manifest.yaml")

    # ---- 4. archive data/acme-security-support/ --------------------------------------------
    archive_result = _archive_haikang(apply=apply)
    print(f"  archive data/acme-security-support/: {archive_result}")

    # ---- 5. summary -------------------------------------------------------
    print(
        f"[migrate_demo_tools] summary: {len(written)} written, "
        f"{len(skipped)} unchanged"
    )
    if not apply:
        print("[migrate_demo_tools] dry-run only — re-run with --apply to commit.")
        return 0

    # ---- 6. post-apply self-check via DemoLoader.rescan() -----------------
    from demo_loader import DemoLoader  # noqa: WPS433

    loader = DemoLoader(DATA_ROOT)
    found_ids = {d["id"] for d in loader.list()}
    missing = [d for d in EXPECTED_DEMO_IDS if d not in found_ids]

    print(f"[migrate_demo_tools] DemoLoader.rescan() found {len(found_ids)} demos")
    for did in EXPECTED_DEMO_IDS:
        ok = did in found_ids
        print(f"  {'✅' if ok else '❌'} {did}")
    if loader.last_skipped:
        print("[migrate_demo_tools] WARNING: loader skipped some demos:")
        for s in loader.last_skipped:
            print(f"    - {s.get('id')}: {s.get('reason')}")

    if missing:
        print(f"[migrate_demo_tools] FAIL: missing demos: {missing}")
        return 1

    print(f"✅ demos: {len(EXPECTED_DEMO_IDS)}")
    if isinstance(archive_result, str) and archive_result.startswith(BACKUPS_ROOT):
        print(f"[migrate_demo_tools] archive path: {archive_result}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-shot migration: generate disk demos for default/sales/"
            "it-support/interviewer/tutor (+ acme-security-support if absent), "
            "archive legacy data/acme-security-support/, then verify via DemoLoader.rescan()."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write files. Default is dry-run (prints what would change).",
    )
    args = parser.parse_args(argv)
    try:
        return _run(apply=args.apply)
    except Exception as e:  # pragma: no cover — surfaces traceback to operator
        logger.exception("migrate_demo_tools failed")
        print(f"[migrate_demo_tools] ERROR: {type(e).__name__}: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
