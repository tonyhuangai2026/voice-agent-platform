"""Voice store: DynamoDB-backed editable voice registry (Part A of the
voice-registry + activity-log proposal).

Mirrors :class:`demo_store.DemoStore` — a sync boto3 resource wrapped in
``asyncio.to_thread`` so it never blocks the event loop, an in-memory
``_cache``, a **lazy** table accessor (built on first use, like DemoStore, so
constructing the singleton at import time never touches AWS), and graceful
degradation when the table is missing. Two additions over DemoStore, both new
here:

  * ``delete(provider, voice_id)`` — removes one item.
  * ``seed_if_empty(constants)`` — batch-writes the three in-code constant
    dicts (MINIMAX_VOICES / POLLY_VOICES / NOVA_SONIC_VOICES, incl. the
    ``DEFAULT_*`` voice ids) ONCE, when the live table is reachable AND empty.

Table shape
-----------
- Table name: env ``VOICES_TABLE`` (default ``genaiic-voicebot-voices``).
- Composite key: ``provider`` (S, HASH) ∈ {minimax, polly, nova-sonic};
  ``voice_id`` (S, RANGE). ``(provider, voice_id)`` is unique.
- Item: ``provider`` + ``voice_id`` + the provider-specific attrs
  (``label``/``gender``/``language``|``locale``/``boost``/``engine``/
  ``polyglot``/``lang_label`` …).

Liveness / fallback
-------------------
``rescan()`` sets ``live=True`` when the scan succeeds and ``live=False`` when
the table is missing. ``bot.voices_for(provider)`` consults ``live`` to choose
between the live registry and the in-code constant dict, so shipping this code
is **zero-impact** until the table exists: with no table, ``live`` stays False
and every resolver reads the same constants as before (byte-identical).

Decimal handling
----------------
Writes reuse ``bot._to_ddb`` (float -> Decimal); reads convert Decimals back to
plain Python numbers via ``demo_store._from_ddb`` so e.g. a MiniMax ``boost``
that was stored numeric comes back as int/float, never a Decimal.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import boto3

from demo_store import _from_ddb

logger = logging.getLogger(__name__)

VOICES_TABLE = (
    os.environ.get("VOICES_TABLE", "genaiic-voicebot-voices").strip()
    or "genaiic-voicebot-voices"
)

# The three providers that share the table. Used to validate the partition key
# and to iterate the constant dicts during seeding.
VOICE_PROVIDERS = ("minimax", "polly", "nova-sonic")


class VoiceStore:
    """DynamoDB-backed voice registry mirroring DemoStore's shape.

    The boto3 Table is built lazily on first use so constructing a
    ``VoiceStore`` never touches AWS (bot.py builds the singleton at import
    time). The cache starts empty and ``live`` starts False; the FastAPI
    lifespan startup hook ``await``s :meth:`rescan` (then :meth:`seed_if_empty`)
    to prewarm it.
    """

    def __init__(self, table_name: str | None = None, region: str | None = None):
        self._table_name = table_name or VOICES_TABLE
        # DynamoDB lives in the deploy region; DDB_REGION falls back to
        # AWS_REGION so single-region deploys are unchanged (matches DemoStore).
        self._region = (
            region
            or os.environ.get("DDB_REGION")
            or os.environ.get("AWS_REGION", "us-east-1")
        )
        self._table = None
        # provider -> {voice_id -> attrs}. attrs DOES NOT include the two key
        # columns (provider/voice_id) — they are stripped on read so the cached
        # dict matches the in-code constant dict shape exactly.
        self._cache: dict[str, dict[str, dict[str, Any]]] = {
            p: {} for p in VOICE_PROVIDERS
        }
        # Drives bot.voices_for(): True once a scan succeeds, False when the
        # table is missing (so callers fall back to the in-code constants).
        self.live: bool = False
        self.last_skipped: list[dict[str, str]] = []

    # ---- lazy table accessor (like DemoStore) -----------------------------

    def _get_table(self):
        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self._table_name)
        return self._table

    # ---- internals: classify "table missing" so reads degrade -------------

    @staticmethod
    def _is_missing_table(exc: Exception) -> bool:
        # Identical to DemoStore._is_missing_table / UserStore._is_missing_table.
        code = (
            getattr(exc, "response", {}).get("Error", {}).get("Code")
            if hasattr(exc, "response")
            else None
        )
        name = type(exc).__name__
        return code == "ResourceNotFoundException" or name == "ResourceNotFoundException"

    # ---- deserialization --------------------------------------------------

    @staticmethod
    def _split_item(item: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any]]:
        """DDB item -> (provider, voice_id, attrs).

        Decimals are converted back to plain numbers first; the two key columns
        are stripped from ``attrs`` so the cached attr dict matches the shape of
        the in-code constant dict (which has NO provider/voice_id keys)."""
        clean = _from_ddb(item)
        provider = clean.pop("provider", None)
        voice_id = clean.pop("voice_id", None)
        return provider, voice_id, clean

    # ---- public API (sync reads — read the in-memory cache) ---------------

    def list(self, provider: str | None = None) -> dict[str, dict[str, Any]]:
        """Return ``{voice_id: attrs}`` for one provider (the shape of the
        in-code constant dict). ``provider=None`` -> the full nested
        ``{provider: {voice_id: attrs}}`` map. Synchronous, reads the cache;
        unknown provider / empty cache -> ``{}`` (never raises)."""
        if provider is None:
            return {p: dict(v) for p, v in self._cache.items()}
        return dict(self._cache.get(provider, {}))

    def get(self, provider: str, voice_id: str) -> dict[str, Any] | None:
        """Return one voice's attr dict or None. Synchronous, reads the cache."""
        if not provider or not voice_id:
            return None
        return self._cache.get(provider, {}).get(voice_id)

    # ---- prewarm / refresh (async) ----------------------------------------

    async def rescan(self) -> int:
        """Paginated ``table.scan()`` -> rebuild the cache. Returns the number
        of voices loaded.

        On success sets ``live=True``. Table-missing -> log a warning, set
        ``live=False``, record ``last_skipped``, KEEP the prior cache, and
        return ``-1`` so callers fall back to the in-code constants (matches
        the tech-design A.3 contract). Any other scan error degrades the same
        way but is recorded as a scan failure. Never raises."""
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
            if self._is_missing_table(e):
                reason = f"table {self._table_name!r} missing"
                # Table absent -> NOT live -> voices_for() falls back to the
                # in-code constants. Return -1 as the explicit not-live signal.
                self.live = False
                logger.warning(
                    f"voice_store: {reason}; falling back to in-code constants"
                )
                self.last_skipped.append({"id": "*", "reason": reason})
                return -1
            reason = f"scan failed: {type(e).__name__}: {e}"
            # A transient scan error keeps the prior cache + prior liveness so a
            # blip doesn't flip a healthy registry to constants.
            logger.warning(
                f"voice_store: {reason}; keeping prior cache "
                f"({sum(len(v) for v in self._cache.values())} voices, live={self.live})"
            )
            self.last_skipped.append({"id": "*", "reason": reason})
            return sum(len(v) for v in self._cache.values())

        new_cache: dict[str, dict[str, dict[str, Any]]] = {p: {} for p in VOICE_PROVIDERS}
        for item in items:
            provider, voice_id, attrs = self._split_item(item)
            if not provider or not voice_id:
                self.last_skipped.append({"id": "?", "reason": "item missing provider/voice_id"})
                continue
            if provider not in new_cache:
                # Unknown provider partition — keep it in the cache anyway so a
                # future provider doesn't silently vanish, but it won't be read
                # by voices_for (which only asks for the three known providers).
                new_cache[provider] = {}
            new_cache[provider][voice_id] = attrs

        self._cache = new_cache
        self.live = True
        total = sum(len(v) for v in new_cache.values())
        logger.info(
            f"voice_store: scanned {self._table_name}, loaded {total} voices "
            f"({ {p: len(v) for p, v in new_cache.items()} })"
        )
        return total

    # ---- writes -----------------------------------------------------------

    async def put(self, provider: str, voice_id: str, attrs: dict[str, Any]) -> None:
        """Persist one voice as a single DDB item.

        ``attrs`` is the validated, provider-specific attr dict (NO provider /
        voice_id keys — they are added here as the composite key). Floats are
        converted to Decimal via ``bot._to_ddb`` (REUSED, not re-implemented) so
        a numeric MiniMax ``boost`` round-trips. Raises ValueError on an empty
        provider / voice_id. Does NOT refresh the cache; the caller (admin
        endpoint / seeding) calls :meth:`rescan` afterwards."""
        if not provider or not voice_id:
            raise ValueError("put requires non-empty provider and voice_id")
        # Lazy import to avoid an import cycle (bot imports voice_store).
        from bot import _to_ddb

        item = {"provider": provider, "voice_id": voice_id}
        # attrs may legitimately carry a "provider"/"voice_id" key only if a
        # caller copied a full row; the explicit key columns win.
        for k, v in (attrs or {}).items():
            if k in ("provider", "voice_id"):
                continue
            item[k] = v
        item = _to_ddb(item)
        table = self._get_table()
        await asyncio.to_thread(lambda: table.put_item(Item=item))

    async def delete(self, provider: str, voice_id: str) -> None:
        """Delete one voice item by composite key. Does NOT refresh the cache;
        the caller calls :meth:`rescan` afterwards."""
        if not provider or not voice_id:
            raise ValueError("delete requires non-empty provider and voice_id")
        table = self._get_table()
        await asyncio.to_thread(
            lambda: table.delete_item(Key={"provider": provider, "voice_id": voice_id})
        )

    # ---- one-time seed ----------------------------------------------------

    async def seed_if_empty(self, constants: dict[str, dict[str, dict[str, Any]]]) -> int:
        """Batch-write the in-code constant dicts ONCE, iff the live table is
        reachable AND empty.

        ``constants`` is ``{provider: {voice_id: attrs}}`` (the three in-code
        dicts). Returns the number of voices written (0 if the table already had
        rows or is missing). Table missing -> no-op (returns 0). Refreshes the
        cache (sets ``live``) via :meth:`rescan` first to decide emptiness, and
        again after writing so the cache reflects the seeded rows.

        Idempotent: a non-empty live table is never re-seeded, so an admin who
        deletes every voice will NOT get the constants re-injected on the next
        boot (deletion is intentional)."""
        # rescan establishes liveness + current contents.
        await self.rescan()
        if not self.live:
            # Table missing -> seeding is a no-op (constants are the fallback).
            return 0
        if any(self._cache.get(p) for p in VOICE_PROVIDERS):
            # Already has rows for at least one provider -> never re-seed.
            return 0

        written = 0
        for provider, voices in (constants or {}).items():
            for voice_id, attrs in (voices or {}).items():
                await self.put(provider, voice_id, attrs)
                written += 1
        if written:
            await self.rescan()
            logger.info(f"voice_store: seeded {written} voices from in-code constants")
        return written
