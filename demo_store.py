"""Demo store: DynamoDB-backed demo configs preserving DemoLoader's interface.

Drop-in replacement for :class:`demo_loader.DemoLoader` as the ``DEMO_LOADER``
singleton in bot.py — the public surface is byte-identical so no call site
changes:

    list()  -> [{id, label, lang, kb_chars}]   (sorted by id, sync, non-blocking)
    get(id) -> full demo dict | None            (sync, non-blocking)
    last_skipped : list[{id, reason}]

Two differences from DemoLoader, both additive:

  * ``rescan()`` is **async** (it does a paginated ``table.scan()``), whereas
    DemoLoader.rescan is sync. The only caller of DemoStore.rescan is the
    FastAPI ``lifespan`` startup hook, which awaits it. ``get``/``list`` stay
    synchronous and read the in-memory cache, so every per-call site in bot.py
    (which only ever calls ``get``/``list``) is unchanged.
  * ``put(demo_dict)`` is new (DemoLoader had no writer — it scanned disk). It
    persists one demo as a single DDB item.

DynamoDB usage mirrors :class:`user_store.UserStore` / ``HistoryRecorder``:
a sync boto3 resource wrapped in ``asyncio.to_thread`` so it never blocks the
event loop, and graceful degradation (log + keep prior/empty cache) when the
table is missing. The ``last_skipped`` attribute records the degrade reason
for admin diagnostics, paralleling DemoLoader.

Decimal handling
----------------
Writes reuse ``bot._to_ddb`` (float -> Decimal) — we do NOT define a second
converter. On read, ``_from_ddb`` walks the item and converts every Decimal
back to int (integral) or float (fractional) so consumers see plain Python
numbers — e.g. ``filler.probability`` is a float, not a Decimal, before it
reaches TimeoutFillerObserver.

Table shape
-----------
- Table name: env ``DEMOS_TABLE`` (default ``genaiic-voicebot-demos``).
- Partition key: ``id`` (string).
- Item: the full canonical demo dict (system/greeting/kb_* per-lang maps,
  kb_body str|map, tool_ids list, mcp_servers list, filler map, tags list).
"""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal
from typing import Any

import boto3

from demo_loader import kb_chars_of, normalize_demo_dict

logger = logging.getLogger(__name__)

DEMOS_TABLE = (
    os.environ.get("DEMOS_TABLE", "genaiic-voicebot-demos").strip()
    or "genaiic-voicebot-demos"
)


def _from_ddb(value: Any) -> Any:
    """Recursively convert DynamoDB Decimals back to plain Python numbers.

    Integral Decimals -> int, fractional -> float. Lists / dicts are walked;
    other scalars pass through unchanged. Inverse of ``bot._to_ddb`` for the
    read path (e.g. ``filler.probability`` comes back as a float)."""
    if isinstance(value, Decimal):
        # Integral values (e.g. timeout_ms) -> int; fractional -> float.
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_from_ddb(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_ddb(v) for k, v in value.items()}
    return value


class DemoStore:
    """DynamoDB-backed demo store with the DemoLoader public interface.

    The table object is created lazily on first use so constructing a
    ``DemoStore`` never touches AWS (cheap to import — bot.py builds the
    singleton at import time). The cache starts empty; the FastAPI lifespan
    startup hook ``await``s :meth:`rescan` to prewarm it.
    """

    def __init__(self, table_name: str | None = None, region: str | None = None):
        self._table_name = table_name or DEMOS_TABLE
        # DynamoDB lives in the deploy region; DDB_REGION falls back to
        # AWS_REGION so single-region deploys are unchanged (matches user_store).
        self._region = (
            region
            or os.environ.get("DDB_REGION")
            or os.environ.get("AWS_REGION", "us-east-1")
        )
        self._table = None
        self._cache: dict[str, dict[str, Any]] = {}
        self.last_skipped: list[dict[str, str]] = []

    def _get_table(self):
        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self._table_name)
        return self._table

    # ---- internals: classify "table missing" so reads degrade -------------

    @staticmethod
    def _is_missing_table(exc: Exception) -> bool:
        # Mirrors user_store.UserStore._is_missing_table.
        code = (
            getattr(exc, "response", {}).get("Error", {}).get("Code")
            if hasattr(exc, "response")
            else None
        )
        name = type(exc).__name__
        return code == "ResourceNotFoundException" or name == "ResourceNotFoundException"

    # ---- deserialization --------------------------------------------------

    @staticmethod
    def _deserialize(item: dict[str, Any]) -> dict[str, Any]:
        """DDB item -> canonical demo dict (same key shape as DemoLoader.get).

        Decimal -> float/int first, then through the SHARED normalizer so the
        ``tool_ids`` key (NOT ``tools``) and all other keys are byte-identical
        to the manifest path. ``validate_tools=False``: stored ids were already
        validated when written, and a registry change must not silently drop
        them on read.
        """
        return normalize_demo_dict(_from_ddb(item), validate_tools=False)

    # ---- public API (sync reads — same signatures as DemoLoader) ----------

    def list(self) -> list[dict[str, Any]]:
        """Return demo summaries {id, label, lang, kb_chars}, sorted by id.

        Reads the in-memory cache synchronously (non-blocking). Empty cache
        (before prewarm, or after a degrade) -> []."""
        out = [
            {
                "id": demo["id"],
                "label": demo["label"],
                "lang": demo["lang"],
                "kb_chars": kb_chars_of(demo.get("kb_body")),
            }
            for demo in self._cache.values()
        ]
        out.sort(key=lambda x: x["id"] or "")
        return out

    def get(self, demo_id: str) -> dict[str, Any] | None:
        """Return the full demo dict for ``demo_id`` or None. Synchronous,
        reads the cache. Empty cache / unknown id -> None (never raises)."""
        if not demo_id:
            return None
        return self._cache.get(demo_id)

    # ---- prewarm / refresh (async) ----------------------------------------

    async def rescan(self) -> int:
        """Paginated ``table.scan()`` -> rebuild the in-memory cache. Returns
        the number of demos loaded.

        Table-missing / scan error -> record ``last_skipped`` and DEGRADE: the
        existing cache (prior contents, or empty at startup) is KEPT, and the
        previous count is returned. Never raises, so a DDB outage at startup
        does not block the app (mirrors user_store's degrade philosophy)."""
        self.last_skipped = []
        table = self._get_table()

        def _scan() -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            kwargs: dict[str, Any] = {}
            while True:
                resp = table.scan(**kwargs)
                items.extend(resp.get("Items", []))
                lek = resp.get("LastEvaluatedKey")
                if not lek:
                    break
                kwargs["ExclusiveStartKey"] = lek
            return items

        try:
            items = await asyncio.to_thread(_scan)
        except Exception as e:
            reason = (
                f"table {self._table_name!r} missing"
                if self._is_missing_table(e)
                else f"scan failed: {type(e).__name__}: {e}"
            )
            logger.warning(
                f"demo_store: {reason}; keeping prior cache "
                f"({len(self._cache)} demos)"
            )
            self.last_skipped.append({"id": "*", "reason": reason})
            return len(self._cache)

        new_cache: dict[str, dict[str, Any]] = {}
        for item in items:
            try:
                demo = self._deserialize(item)
            except Exception as e:  # pragma: no cover — defensive
                bad_id = item.get("id", "?")
                reason = f"deserialize failed: {type(e).__name__}: {e}"
                logger.warning(f"demo_store: demo {bad_id!r}: {reason}; skipping")
                self.last_skipped.append({"id": str(bad_id), "reason": reason})
                continue
            demo_id = demo.get("id")
            if not demo_id:
                self.last_skipped.append({"id": "?", "reason": "item missing id"})
                continue
            if demo_id in new_cache:
                reason = f"duplicate id {demo_id}"
                logger.warning(f"demo_store: {reason}; skipping")
                self.last_skipped.append({"id": demo_id, "reason": reason})
                continue
            new_cache[demo_id] = demo

        self._cache = new_cache
        logger.info(
            f"demo_store: scanned {self._table_name}, loaded {len(new_cache)} demos, "
            f"skipped {len(self.last_skipped)}"
        )
        return len(new_cache)

    # ---- write ------------------------------------------------------------

    async def put(self, demo_dict: dict[str, Any]) -> None:
        """Persist one demo as a single DDB item.

        The dict is normalized through the SHARED helper (guaranteeing the
        ``tool_ids`` key shape on disk too) and floats are converted to Decimal
        via ``bot._to_ddb`` — REUSED, not re-implemented. Raises ValueError if
        the demo has no ``id`` (the partition key). Does NOT refresh the cache;
        the caller (PATCH endpoint / migration) calls ``rescan`` afterwards."""
        if not isinstance(demo_dict, dict) or not demo_dict.get("id"):
            raise ValueError("demo_dict must be a dict with a non-empty 'id'")
        # Lazy import to avoid an import cycle (bot imports demo_store).
        from bot import _to_ddb

        canonical = normalize_demo_dict(demo_dict, validate_tools=False)
        item = _to_ddb(canonical)
        table = self._get_table()
        await asyncio.to_thread(lambda: table.put_item(Item=item))
