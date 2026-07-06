"""Demo loader: scan data/<demo>/ and expose them as scenario configs.

A demo is a directory containing:
  - manifest.yaml — id, label, lang, system / greeting / kb_intro / kb_ack as
    per-language dicts (key = language code: zh-HK / zh-CN / en-US / ja-JP).
    Optional `tools: [...]` field listing tool ids from
    :mod:`tools.registry`.
    Optional `mcp_servers: [...]` field listing MCP server ids from
    config/mcp_servers.json (see :mod:`mcp_config`). Ids are NOT
    validated against the registry at load time — servers can be
    created after the demo, so unknown ids are skipped (with a
    WARNING) at pipeline-build time instead.
  - kb.md — the knowledge base body, injected as a synthetic first user
    message into the LLM context. Optional now: a demo with no readable
    KB file is still loaded with ``kb_body = ""`` (or per-language empty
    strings) so that pure tool-only demos work.

Adding a new demo at runtime: drop a folder under data/, then call rescan().
The Admin UI exposes this via POST /api/admin/demos/rescan.

Skipped demos (validation failures) are recorded on
``DemoLoader.last_skipped`` as ``[{id, reason}, ...]`` for admin REST
diagnostics. The list is reset at the start of every :meth:`rescan`.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

logger = logging.getLogger(__name__)


REQUIRED_FIELDS = ("id", "label", "lang")
LOCALIZED_REQUIRED = ("system", "greeting")  # must be per-language dicts
LOCALIZED_OPTIONAL = ("kb_intro", "kb_ack")  # also per-language if present


def _normalize_tool_ids(raw_tools: Any, *, validate: bool, where: str = "") -> list[str]:
    """Coerce a raw ``tools``/``tool_ids`` value into a clean ``list[str]``.

    ``validate=True`` drops ids not present in ``tools.registry.REGISTRY``
    (manifest-load semantics). ``validate=False`` keeps every non-empty string
    (DDB-deserialize semantics — the ids were already validated when written,
    and a server-side registry change should not silently mutate stored data).
    Non-list inputs degrade to ``[]`` (never raise), matching DemoLoader's
    lenient handling.
    """
    if raw_tools is None:
        return []
    if not isinstance(raw_tools, list):
        logger.warning(
            f"demo: {where}'tools' must be a list of strings "
            f"(got {type(raw_tools).__name__}); using empty list"
        )
        return []

    registry = None
    if validate:
        try:
            from tools.registry import REGISTRY as registry  # noqa: WPS433
        except Exception as e:  # pragma: no cover — defensive
            logger.warning(
                f"demo: cannot import tools.registry ({type(e).__name__}: {e}); "
                f"accepting tool ids unvalidated"
            )
            registry = None

    out: list[str] = []
    for t in raw_tools:
        if not isinstance(t, str) or not t:
            logger.warning(f"demo: {where}ignoring non-string tool entry {t!r}")
            continue
        if registry is not None and t not in registry:
            logger.warning(
                f"demo: {where}dropping unknown tool id {t!r} "
                f"(not in tools.registry.REGISTRY)"
            )
            continue
        out.append(t)
    return out


def _normalize_mcp_servers(raw_mcp: Any, where: str = "") -> list[str]:
    """Coerce a raw ``mcp_servers`` value into a clean ``list[str]`` (ids are
    NOT validated against the registry — servers may be created after the demo).
    Non-list inputs degrade to ``[]``."""
    if raw_mcp is None:
        return []
    if not isinstance(raw_mcp, list):
        logger.warning(
            f"demo: {where}'mcp_servers' must be a list of strings "
            f"(got {type(raw_mcp).__name__}); using empty list"
        )
        return []
    out: list[str] = []
    for m in raw_mcp:
        if not isinstance(m, str) or not m:
            logger.warning(f"demo: {where}ignoring non-string mcp_servers entry {m!r}")
            continue
        out.append(m)
    return out


def kb_chars_of(kb_body: Any) -> int:
    """Total KB character count: sum across per-language variants if a dict,
    else len of the single string. Single source for list()/summary kb_chars."""
    if isinstance(kb_body, dict):
        return sum(len(v or "") for v in kb_body.values())
    return len(kb_body or "")


def normalize_demo_dict(raw: dict[str, Any], *, validate_tools: bool) -> dict[str, Any]:
    """SINGLE source of the canonical demo-dict key shape.

    Takes a raw dict (a parsed manifest with ``kb_body`` already resolved, OR a
    DynamoDB item already in demo shape) and returns the canonical demo dict
    that bot.py consumes. The tool-list key is ALWAYS ``tool_ids`` (never
    ``tools``) — bot.py reads ``demo["tool_ids"]`` at pipeline-build time. Both
    DemoLoader (manifest path) and DemoStore (DDB path) build their cache
    entries through here so the key shape can never drift between them.

    ``validate_tools`` is forwarded to tool-id normalization: True on the
    manifest path (drop ids unknown to the registry), False on the DDB path
    (trust already-validated stored ids).

    Accepts either ``tool_ids`` (preferred / already-normalized) or the raw
    manifest ``tools`` key as the tool source.
    """
    where = f"{raw.get('id', '?')}: "
    raw_tools = raw.get("tool_ids", raw.get("tools"))
    filler = raw.get("filler")
    filler_cfg = filler if isinstance(filler, dict) else None
    asr_filter = raw.get("asr_filter")
    asr_filter_cfg = asr_filter if isinstance(asr_filter, dict) else None
    tags = raw.get("tags")
    out: dict[str, Any] = {
        "id": raw.get("id"),
        "label": raw.get("label"),
        "lang": raw.get("lang"),
        # Optional per-demo engine/voice/provider/model overrides (parity with
        # ``lang``: trusted stored/migrated data, no validation here — that
        # lives at the PATCH boundary in bot._validate_engine_voice_patch).
        # Absent → None → byte-identical downstream (launch omits null values;
        # /ws falls back exactly as today). ``model`` is the per-demo LLM
        # override — MUST be kept here or it is dropped on every DDB read/write.
        "engine": raw.get("engine"),
        "provider": raw.get("provider"),
        "voice": raw.get("voice"),
        "model": raw.get("model"),
        "system": raw.get("system"),
        "greeting": raw.get("greeting"),
        "kb_intro": raw.get("kb_intro"),
        "kb_ack": raw.get("kb_ack"),
        "kb_body": raw.get("kb_body", ""),
        "tool_ids": _normalize_tool_ids(raw_tools, validate=validate_tools, where=where),
        "mcp_servers": _normalize_mcp_servers(raw.get("mcp_servers"), where=where),
        "filler": filler_cfg,
        "asr_filter": asr_filter_cfg,
        "tags": tags if isinstance(tags, list) else [],
    }
    return out


class DemoLoader:
    """Scans `data_root` for demos. Each subdirectory with a valid
    manifest.yaml becomes a usable demo. Invalid manifests are logged
    and skipped (with a reason recorded on ``last_skipped``); they don't
    crash the loader."""

    def __init__(self, data_root: str):
        self._data_root = data_root
        self._cache: dict[str, dict[str, Any]] = {}
        self.last_skipped: list[dict[str, str]] = []
        self.rescan()

    # ---- public API ----------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """Return demo summaries (id, label, lang, kb_chars).

        For per-language KBs, kb_chars reports the total across all variants.
        """
        out = []
        for demo in self._cache.values():
            out.append({
                "id": demo["id"],
                "label": demo["label"],
                "lang": demo["lang"],
                "kb_chars": kb_chars_of(demo.get("kb_body")),
            })
        out.sort(key=lambda x: x["id"])
        return out

    def get(self, demo_id: str) -> dict[str, Any] | None:
        """Return the full demo dict (with system/greeting/kb_body) or None."""
        return self._cache.get(demo_id)

    def rescan(self) -> int:
        """Re-scan data_root, rebuild the cache. Returns count of demos found.

        Resets ``self.last_skipped`` to an empty list at the start, then
        appends ``{id, reason}`` entries for each demo that is rejected
        during this scan.
        """
        new_cache: dict[str, dict[str, Any]] = {}
        self.last_skipped = []
        if not os.path.isdir(self._data_root):
            logger.info(f"demo_loader: data root {self._data_root} missing, no demos")
            self._cache = new_cache
            return 0
        for entry in sorted(os.listdir(self._data_root)):
            sub = os.path.join(self._data_root, entry)
            if not os.path.isdir(sub):
                continue
            demo = self._load_one(sub)
            if demo is None:
                continue
            if demo["id"] in new_cache:
                reason = f"duplicate id {demo['id']} (in {sub})"
                logger.warning(f"demo_loader: {reason}; skipping")
                self.last_skipped.append({"id": demo["id"], "reason": reason})
                continue
            new_cache[demo["id"]] = demo
        self._cache = new_cache
        logger.info(
            f"demo_loader: scanned {self._data_root}, found {len(new_cache)} demos, "
            f"skipped {len(self.last_skipped)}"
        )
        return len(new_cache)

    # ---- internals -----------------------------------------------------

    def _record_skip(self, demo_id: str, reason: str) -> None:
        """Append a skip entry. ``demo_id`` may be the manifest id or a
        directory-derived placeholder when the id couldn't be parsed."""
        self.last_skipped.append({"id": demo_id, "reason": reason})

    def _load_one(self, dir_path: str) -> dict[str, Any] | None:
        manifest_path = os.path.join(dir_path, "manifest.yaml")
        # Use the directory basename as a fallback id for skip records when
        # we can't even parse the manifest. The real manifest id (if any)
        # overrides this once we have it.
        fallback_id = os.path.basename(dir_path.rstrip(os.sep)) or dir_path

        if not os.path.isfile(manifest_path):
            logger.info(f"demo_loader: no manifest.yaml in {dir_path}, skipping")
            # Not recorded in last_skipped: a directory with no manifest is
            # not a demo at all (might just be a stray folder), so it would
            # be noise in the admin "why was this skipped?" view.
            return None

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)
        except Exception as e:
            reason = f"failed to parse manifest.yaml: {type(e).__name__}: {e}"
            logger.warning(f"demo_loader: {manifest_path}: {reason}")
            self._record_skip(fallback_id, reason)
            return None

        if not isinstance(manifest, dict):
            reason = "manifest.yaml is not a YAML mapping"
            logger.warning(f"demo_loader: {manifest_path}: {reason}; skipping")
            self._record_skip(fallback_id, reason)
            return None

        # Use the manifest id for skip records once available.
        skip_id = manifest.get("id") or fallback_id

        for f in REQUIRED_FIELDS:
            if not manifest.get(f):
                reason = f"missing required field '{f}'"
                logger.warning(f"demo_loader: {manifest_path}: {reason}; skipping")
                self._record_skip(skip_id, reason)
                return None

        for f in LOCALIZED_REQUIRED:
            v = manifest.get(f)
            if not isinstance(v, dict) or not v:
                reason = (
                    f"field '{f}' must be a non-empty per-language dict "
                    f"(got {type(v).__name__})"
                )
                logger.warning(f"demo_loader: {manifest_path}: {reason}; skipping")
                self._record_skip(skip_id, reason)
                return None

        for f in LOCALIZED_OPTIONAL:
            v = manifest.get(f)
            if v is not None and not isinstance(v, dict):
                reason = f"field '{f}' if present must be a dict (got {type(v).__name__})"
                logger.warning(f"demo_loader: {manifest_path}: {reason}; skipping")
                self._record_skip(skip_id, reason)
                return None

        # ---- kb_path -----------------------------------------------------
        # `kb_path` accepts either:
        #   "kb.md"                                    — single file (legacy)
        #   {"en-US": "kb.en.md", "zh-HK": "kb.zh.md"} — per-language (preferred)
        # Missing / unreadable KB files are NOT a hard error any more —
        # they downgrade kb_body for that lang (or the whole demo) to "",
        # so a pure tool-only demo with no kb_path still loads.
        kb_path = manifest.get("kb_path")
        kb_body: Any
        if kb_path is None:
            # Manifest didn't declare a kb_path at all -> empty body.
            kb_body = ""
        elif isinstance(kb_path, dict):
            kb_body = {}
            for lang, rel in kb_path.items():
                if not isinstance(rel, str) or not rel:
                    logger.warning(
                        f"demo_loader: {manifest_path}: kb_path[{lang!r}] is "
                        f"not a non-empty string; using empty body for that lang"
                    )
                    kb_body[lang] = ""
                    continue
                full = os.path.join(dir_path, rel)
                if not os.path.isfile(full):
                    logger.warning(
                        f"demo_loader: kb file {full} not found for "
                        f"{manifest['id']}/{lang}; using empty kb_body for that lang"
                    )
                    kb_body[lang] = ""
                    continue
                try:
                    with open(full, "r", encoding="utf-8") as f:
                        kb_body[lang] = f.read()
                except Exception as e:
                    logger.warning(
                        f"demo_loader: failed to read {full}: {e}; "
                        f"using empty kb_body for {manifest['id']}/{lang}"
                    )
                    kb_body[lang] = ""
        else:
            kb_full = os.path.join(dir_path, str(kb_path))
            if not os.path.isfile(kb_full):
                logger.warning(
                    f"demo_loader: kb file {kb_full} not found for "
                    f"{manifest['id']}; using empty kb_body"
                )
                kb_body = ""
            else:
                try:
                    with open(kb_full, "r", encoding="utf-8") as f:
                        kb_body = f.read()
                except Exception as e:
                    logger.warning(
                        f"demo_loader: failed to read {kb_full}: {e}; "
                        f"using empty kb_body for {manifest['id']}"
                    )
                    kb_body = ""

        # ---- filler field -------------------------------------------------
        # Optional per-demo override of the global FILLER_* env defaults
        # (enabled / timeout_ms / probability). Only a dict is accepted;
        # anything else is ignored (env fallback) rather than crashing the
        # loader. The actual coercion lives in normalize_demo_dict; we only
        # WARN here so the manifest author gets a pointer to the bad field.
        raw_filler = manifest.get("filler")
        if raw_filler is not None and not isinstance(raw_filler, dict):
            logger.warning(
                f"demo_loader: {manifest_path}: 'filler' must be a mapping "
                f"(got {type(raw_filler).__name__}); ignoring (env fallback)"
            )

        # ---- asr_filter field --------------------------------------------
        # Optional per-demo override of the global ASR_FILTER_* env defaults
        # (enabled / min_confidence / max_chars / max_words). Only a dict is
        # accepted; anything else is ignored (env fallback) rather than crashing
        # the loader. Coercion lives in normalize_demo_dict; WARN here only.
        raw_asr = manifest.get("asr_filter")
        if raw_asr is not None and not isinstance(raw_asr, dict):
            logger.warning(
                f"demo_loader: {manifest_path}: 'asr_filter' must be a mapping "
                f"(got {type(raw_asr).__name__}); ignoring (env fallback)"
            )

        # Build the canonical demo dict through the SHARED normalizer so the
        # key shape (esp. the `tool_ids` key) is identical to DemoStore's
        # DDB-deserialization path. ``kb_body`` was just resolved from disk.
        raw = dict(manifest)
        raw["kb_body"] = kb_body  # str OR dict[lang -> str]
        demo = normalize_demo_dict(raw, validate_tools=True)
        demo["_dir"] = dir_path  # filesystem origin — DemoLoader only
        return demo
