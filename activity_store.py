"""Activity audit store: DynamoDB-backed operations audit log (Part B).

An *operations* audit trail — who did what, when — distinct from the
conversation transcripts kept by ``HistoryRecorder``. Records admin/auth
actions (login/logout, demo edits, mcp/voice/user/config mutations) plus
call start/stop events.

Design (tech_design Part B.2/B.3):

- **Write-path semantics mirror ``HistoryRecorder``**: a sync boto3 resource
  invoked via ``asyncio.to_thread`` (moto patches sync botocore cleanly), TTL
  on every row, best-effort writes that NEVER raise into the caller.
- **Lazy ``_table`` accessor** (like ``DemoStore``, NOT eager like
  ``HistoryRecorder.__init__``) — N3 in the tech design. Constructing an
  ``ActivityStore`` when the table is absent / creds aren't ready must never
  touch AWS, so the bot.py singleton can be built at import time and the
  endpoints/lifespan stay zero-impact until the table exists.
- **Graceful degrade**: table missing → ``log`` is a silent no-op, ``query``
  returns empty. Shipping the code is zero-impact on prod until the table
  exists + env is set.

Table shape (PK ``day`` = UTC ``YYYY-MM-DD``, SK ``ts_id`` =
``<epoch_ms>#<uuid>``) so a time-range query touches a small set of day
partitions, time-sorted within a day.

Redaction — DEFAULT-DENY (the round-1 reviewer BLOCKER fix)
-----------------------------------------------------------
The old "redact keys matching ``password|token|...``" substring approach was
unsafe: a credential-bearing field whose JSON key doesn't match (an mcp
``url``/``headers``/``auth`` block, a ``verification_code``, a bearer value)
would persist a raw secret. The model here is **default-deny**:

1. Callers pass a CURATED, already-safe ``detail`` (changed field NAMES for
   mutating endpoints, never raw bodies) — enforced at the call site.
2. ``ACTIVITY_DETAIL_VALUE_ALLOWLIST`` names, per activity type, the ONLY
   fields whose *values* may be stored. ``_sanitize_detail`` is the store-side
   backstop: any field NOT in the allowlist is masked to its NAME ONLY (value
   → ``"***changed***"``). An UNKNOWN type masks all values.
3. A residual substring scrub runs LAST as belt-and-suspenders only —
   correctness rests on the default-deny allowlist, not the substring list.

Net: a credential-bearing field can only ever appear as its field NAME,
never its value — regardless of how the field is named.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)

ACTIVITY_TABLE = (
    os.environ.get("ACTIVITY_TABLE", "genaiic-voicebot-activity").strip()
    or "genaiic-voicebot-activity"
)


def _ttl_days_default() -> int:
    raw = (os.environ.get("ACTIVITY_LOG_TTL_DAYS") or "").strip()
    try:
        v = int(raw)
        return v if v > 0 else 90
    except (TypeError, ValueError):
        return 90


# --- Redaction (DEFAULT-DENY) --------------------------------------------

# Per-type value allowlist: the ONLY fields whose *values* may be stored for a
# given activity type. Anything else → field-name only ("***changed***").
# NEVER list password/password_hash (user-*), url/headers/auth (mcp-*).
ACTIVITY_DETAIL_VALUE_ALLOWLIST: dict[str, set[str]] = {
    "config-web": {"engine", "lang", "scenario", "provider", "voice", "minimax_model", "model", "asr_filter"},
    "config-phone": {"engine", "lang", "scenario", "provider", "voice", "minimax_model", "model", "asr_filter"},
    "voice-create": {"provider", "voice_id", "label", "gender", "language", "locale", "polyglot", "engine", "boost"},
    "voice-update": {"provider", "voice_id", "label", "gender", "language", "locale", "polyglot", "engine", "boost"},
    "voice-delete": {"provider", "voice_id", "label", "gender", "language", "locale", "polyglot", "engine", "boost"},
    "user-create": {"role", "disabled"},
    "user-update": {"role", "disabled"},
    "user-delete": {"role", "disabled"},
    "mcp-upsert": {"id", "label", "transport", "enabled"},
    "mcp-delete": {"id", "label", "transport", "enabled"},
    # demo-edit stores changed FIELD NAMES only (the caller passes
    # {"changed": [..names..]}); no per-value fields are allowlisted, so any
    # stray value-bearing key is masked.
    "demo-edit": {"changed"},
    "login": {"username"},
    "logout": {"username"},
    # Guest experience links — the token is NEVER passed to detail (and would be
    # masked by default-deny regardless); only the link parameters are recorded.
    "guest-link-create": {"ttl_minutes", "scenario", "lang", "engine", "voice", "provider"},
    "guest-login": {"scenario"},
    # call-start / call-end carry only non-secret runtime descriptors.
    "call-start": {"engine", "lang", "scenario", "voice"},
    "call-end": {"engine", "lang", "scenario", "voice"},
}

_MASK = "***changed***"

# Belt-and-suspenders ONLY (runs last). Correctness rests on the default-deny
# allowlist above, not this substring list.
_SECRET_SUBSTR = re.compile(
    r"password|token|api[_-]?key|secret|authorization|key|credential|bearer",
    re.IGNORECASE,
)


def _scrub_residual(value: Any) -> Any:
    """Belt-and-suspenders: recursively mask any dict key matching a known
    secret substring. Runs LAST, after the allowlist has already masked
    non-allowlisted fields — it is NOT the primary defence."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _SECRET_SUBSTR.search(k):
                out[k] = _MASK
            else:
                out[k] = _scrub_residual(v)
        return out
    if isinstance(value, list):
        return [_scrub_residual(v) for v in value]
    return value


def _sanitize_detail(activity_type: str, detail: dict[str, Any] | None) -> dict[str, Any]:
    """DEFAULT-DENY store-side backstop.

    Any key not in this type's ``ACTIVITY_DETAIL_VALUE_ALLOWLIST`` is masked to
    its NAME ONLY (value → ``"***changed***"``). An UNKNOWN type masks ALL
    values. A residual secret-substring scrub runs LAST as belt-and-suspenders.
    Even a careless caller that passes a raw credential value under an
    innocuous key (e.g. mcp ``url``/``headers``/``auth``) cannot leak it.
    """
    if not detail:
        return {}
    if not isinstance(detail, dict):
        # Non-dict detail can't be field-allowlisted; mask entirely.
        return {"detail": _MASK}
    allow = ACTIVITY_DETAIL_VALUE_ALLOWLIST.get(activity_type)
    out: dict[str, Any] = {}
    for k, v in detail.items():
        if allow is not None and k in allow:
            out[k] = v
        else:
            # Not allowlisted (or unknown type) → keep the field NAME, drop the
            # value. The audit trail still records THAT the field changed.
            out[k] = _MASK
    # Residual belt-and-suspenders scrub on the surviving (allowlisted) values.
    return _scrub_residual(out)


class ActivityStore:
    """DynamoDB-backed operations audit store (best-effort write, lazy table).

    Constructing this never touches AWS — the boto3 Table is built lazily on
    first use (N3). ``log`` swallows ALL failures (incl. table-missing) so it
    can never break the operation it audits; ``query`` returns empty when the
    table is absent.
    """

    def __init__(
        self,
        table_name: str | None = None,
        region: str | None = None,
        ttl_days: int | None = None,
    ):
        # Read the env at construction (not just the import-time module
        # constant) so a test/process that sets ACTIVITY_TABLE after import is
        # honoured — the singleton in bot.py is built at import time in prod, so
        # this is also correct there.
        self._table_name = table_name or (
            os.environ.get("ACTIVITY_TABLE", "").strip() or ACTIVITY_TABLE
        )
        # DynamoDB lives in the deploy region; DDB_REGION falls back to
        # AWS_REGION so single-region deploys are unchanged (matches DemoStore).
        self._region = (
            region
            or os.environ.get("DDB_REGION")
            or os.environ.get("AWS_REGION", "us-east-1")
        )
        self._ttl_days = ttl_days if ttl_days is not None else _ttl_days_default()
        self._table = None  # built lazily — never eager (N3)

    # ---- lazy table (built on first use, like DemoStore) ------------------

    def _get_table(self):
        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self._table_name)
        return self._table

    @staticmethod
    def _is_missing_table(exc: Exception) -> bool:
        # Mirrors DemoStore / user_store classification.
        code = (
            getattr(exc, "response", {}).get("Error", {}).get("Code")
            if hasattr(exc, "response")
            else None
        )
        name = type(exc).__name__
        return code == "ResourceNotFoundException" or name == "ResourceNotFoundException"

    # ---- write (best-effort, never raises) --------------------------------

    async def log(
        self,
        actor: str,
        actor_role: str | None = None,
        type: str = "",
        target: str | None = None,
        detail: dict[str, Any] | None = None,
        status: str = "success",
        error: str | None = None,
    ) -> None:
        """Persist one audit row. BEST-EFFORT: any failure — including a
        missing table or unavailable credentials — is swallowed with a debug
        log and NEVER raised into the caller.

        Row: ``day`` (UTC YYYY-MM-DD) / ``ts_id`` (``<epoch_ms>#<uuid>``) /
        ``ttl`` (now + ttl_days*86400). ``detail`` is passed through
        ``_sanitize_detail`` (default-deny) so the store can't persist a raw
        secret even if a caller is careless.
        """
        try:
            now = time.time()
            now_ms = int(now * 1000)
            dt = datetime.now(timezone.utc)
            row: dict[str, Any] = {
                "day": dt.strftime("%Y-%m-%d"),
                "ts_id": f"{now_ms}#{uuid.uuid4().hex}",
                "ts": now_ms,
                "actor": actor or "anon",
                "actor_role": actor_role or "",
                "type": type or "",
                "status": status or "success",
                "detail": _sanitize_detail(type or "", detail),
                "ttl": int(now) + self._ttl_days * 86400,
            }
            if target is not None:
                row["target"] = target
            if error:
                row["error"] = str(error)[:500]

            # Reuse bot._to_ddb (float → Decimal) like HistoryRecorder; lazy
            # import avoids an import cycle (bot imports activity_store).
            from bot import _to_ddb

            table = self._get_table()
            await asyncio.to_thread(lambda: table.put_item(Item=_to_ddb(row)))
        except Exception as e:  # noqa: BLE001 — best-effort, must never raise
            # NB: the `type` PARAMETER shadows the builtin in this scope, so use
            # the class attribute directly rather than type(e).
            logger.debug(
                f"activity_store: log dropped (type={type!r} actor={actor!r}): "
                f"{e.__class__.__name__}: {e}"
            )

    # ---- read (paginated, newest-first) -----------------------------------

    async def query(
        self,
        day_from: str | None = None,
        day_to: str | None = None,
        actor: str | None = None,
        type: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Query the day partitions in ``[day_from, day_to]`` (UTC dates),
        optionally filter by ``actor`` / ``type``, return newest-first and
        paginated.

        Returns ``{"items": [...], "cursor": <opaque str|None>}``. ``cursor`` is
        a ``"<day>|<ts_id>"`` marker identifying the last row returned; pass it
        back to fetch the next (older) page. Table missing / any error →
        ``{"items": [], "cursor": None}``.
        """
        try:
            limit = max(1, min(int(limit or 100), 1000))
        except (TypeError, ValueError):
            limit = 100

        # Default window: today back 90 days (TTL horizon) when unset.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d_to = (day_to or today)
        d_from = day_from or _days_ago(d_to, 90)
        if d_from > d_to:
            d_from, d_to = d_to, d_from

        days = _day_range_desc(d_from, d_to)  # newest day first

        # Parse cursor: only start emitting once we pass it (newest-first).
        cur_day, cur_ts_id = None, None
        if cursor and "|" in cursor:
            cur_day, cur_ts_id = cursor.split("|", 1)

        try:
            from boto3.dynamodb.conditions import Key

            table = self._get_table()
            collected: list[dict[str, Any]] = []
            next_cursor: str | None = None

            for day in days:
                # Skip day-partitions newer than the cursor's day (already sent).
                if cur_day is not None and day > cur_day:
                    continue

                def _query_day(d=day) -> list[dict[str, Any]]:
                    items: list[dict[str, Any]] = []
                    kwargs: dict[str, Any] = {
                        "KeyConditionExpression": Key("day").eq(d),
                        "ScanIndexForward": False,  # newest ts_id first within a day
                    }
                    while True:
                        resp = table.query(**kwargs)
                        items.extend(resp.get("Items", []))
                        lek = resp.get("LastEvaluatedKey")
                        if not lek:
                            break
                        kwargs["ExclusiveStartKey"] = lek
                    return items

                rows = await asyncio.to_thread(_query_day)

                for r in rows:
                    ts_id = r.get("ts_id", "")
                    # Cursor: on the cursor's own day, skip rows >= the cursor
                    # ts_id (already returned). ScanIndexForward=False yields
                    # descending ts_id, so "older" == smaller ts_id.
                    if cur_day is not None and day == cur_day and cur_ts_id is not None:
                        if ts_id >= cur_ts_id:
                            continue
                    if actor and r.get("actor") != actor:
                        continue
                    if type and r.get("type") != type:
                        continue
                    collected.append(_from_ddb_row(r))
                    if len(collected) >= limit:
                        next_cursor = f"{day}|{ts_id}"
                        return {"items": collected, "cursor": next_cursor}

                # Once we've consumed the cursor's day, the cursor no longer
                # constrains older days.
                if cur_day is not None and day == cur_day:
                    cur_day, cur_ts_id = None, None

            return {"items": collected, "cursor": None}
        except Exception as e:  # noqa: BLE001 — degrade to empty
            if self._is_missing_table(e):
                logger.debug(f"activity_store: query table {self._table_name!r} missing → empty")
            else:
                # `type` param shadows the builtin — use the class attribute.
                logger.warning(f"activity_store: query failed: {e.__class__.__name__}: {e}")
            return {"items": [], "cursor": None}


# --- helpers --------------------------------------------------------------

def _days_ago(day: str, n: int) -> str:
    from datetime import date, timedelta

    y, m, d = (int(x) for x in day.split("-"))
    return (date(y, m, d) - timedelta(days=n)).strftime("%Y-%m-%d")


def _day_range_desc(d_from: str, d_to: str) -> list[str]:
    """Inclusive list of UTC YYYY-MM-DD strings from d_to back to d_from
    (newest first). Capped at 366 partitions defensively."""
    from datetime import date, timedelta

    y1, m1, d1 = (int(x) for x in d_from.split("-"))
    y2, m2, d2 = (int(x) for x in d_to.split("-"))
    start = date(y1, m1, d1)
    cur = date(y2, m2, d2)
    out: list[str] = []
    guard = 0
    while cur >= start and guard < 366:
        out.append(cur.strftime("%Y-%m-%d"))
        cur = cur - timedelta(days=1)
        guard += 1
    return out


def _from_ddb_row(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a DDB activity item's Decimals back to plain Python numbers so
    the JSON response carries ints, not Decimal. Reuses demo_store._from_ddb."""
    from demo_store import _from_ddb

    return _from_ddb(item)
