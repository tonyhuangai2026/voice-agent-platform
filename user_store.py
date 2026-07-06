"""User store: DynamoDB-backed account table with bcrypt password hashing.

Backs the JWT-session auth model that replaced the old shared SITE_PASSWORD /
ADMIN_PASSWORD Basic Auth (see bot.py). Mirrors the DDB usage pattern of
:class:`HistoryRecorder` (bot.py) — a sync boto3 resource wrapped in
``asyncio.to_thread`` so it never blocks the event loop, and graceful
degradation (log + treat as empty) when the table does not exist.

Table shape
-----------
- Table name: env ``USERS_TABLE`` (default ``genaiic-voicebot-users``).
- Partition key: ``username`` (string).
- Item fields:
    username       str
    password_hash  str   (bcrypt, cost 12)
    role           str   ("admin" | "user")
    created_at     int   (unix seconds)
    disabled       bool

Security
--------
Passwords are NEVER stored in plaintext and the ``password_hash`` is NEVER
returned by :meth:`UserStore.get` / :meth:`UserStore.list` — those return a
"safe" view (username/role/created_at/disabled only). :meth:`UserStore.verify`
is the only path that reads the hash, and it returns the same safe view.

``bcrypt`` is imported lazily so that a missing dependency degrades only the
auth path — it must never break ``import user_store`` or, by extension,
``import bot`` (which would take down the unauthenticated PSTN ``/phone/ws``
bridge). When bcrypt is unavailable, hashing/verification raise
:class:`AuthUnavailable` at call time and the caller maps that to a 503.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

USERS_TABLE = os.environ.get("USERS_TABLE", "genaiic-voicebot-users").strip() or "genaiic-voicebot-users"

VALID_ROLES = ("admin", "user")
BCRYPT_COST = 12


class AuthUnavailable(RuntimeError):
    """Raised when bcrypt is not importable so password ops cannot run.

    Kept distinct from ValueError so callers can map it to HTTP 503 (server
    mis-config) rather than 400/401 (bad input)."""


def _bcrypt():
    """Lazy import of bcrypt. Raises AuthUnavailable if unavailable so a
    missing dependency degrades only the auth path, never module import."""
    try:
        import bcrypt  # type: ignore
    except Exception as e:  # pragma: no cover - exercised only without bcrypt
        raise AuthUnavailable(f"bcrypt not installed: {e}") from e
    return bcrypt


def hash_password(password: str) -> str:
    """Return a bcrypt hash (cost 12) of ``password`` as a UTF-8 str."""
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    bcrypt = _bcrypt()
    # bcrypt truncates at 72 bytes; encode then hash.
    salt = bcrypt.gensalt(rounds=BCRYPT_COST)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    """Constant-time bcrypt comparison. False on any error / malformed hash."""
    if not password or not password_hash:
        return False
    bcrypt = _bcrypt()
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def _safe_view(item: dict[str, Any]) -> dict[str, Any]:
    """Public projection of a user row — never includes ``password_hash``."""
    created = item.get("created_at")
    try:
        created = int(created) if created is not None else None
    except (TypeError, ValueError):
        created = None
    return {
        "username": item.get("username"),
        "role": item.get("role") or "user",
        "created_at": created,
        "disabled": bool(item.get("disabled")),
    }


class UserStore:
    """DynamoDB-backed user account store.

    All public methods are async and run the blocking boto3 calls via
    ``asyncio.to_thread``. The table object is created lazily on first use so
    constructing a ``UserStore`` never touches AWS (cheap to import).
    """

    def __init__(self, table_name: str | None = None, region: str | None = None):
        self._table_name = (table_name or USERS_TABLE)
        # DynamoDB lives in the deploy region; DDB_REGION falls back to
        # AWS_REGION so single-region deploys are unchanged.
        self._region = region or os.environ.get("DDB_REGION") or os.environ.get("AWS_REGION", "us-east-1")
        self._table = None

    def _get_table(self):
        if self._table is None:
            self._table = boto3.resource("dynamodb", region_name=self._region).Table(self._table_name)
        return self._table

    # ---- internals: classify "table missing" so reads degrade to empty ----

    @staticmethod
    def _is_missing_table(exc: Exception) -> bool:
        # botocore ClientError carries response['Error']['Code'].
        code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
        name = type(exc).__name__
        return code in ("ResourceNotFoundException",) or name == "ResourceNotFoundException"

    # ---- reads -----------------------------------------------------------

    async def get(self, username: str) -> dict[str, Any] | None:
        """Return the safe view of one user (no password_hash) or None."""
        if not username:
            return None
        item = await self._get_raw(username)
        return _safe_view(item) if item else None

    async def _get_raw(self, username: str) -> dict[str, Any] | None:
        """Internal: return the full row INCLUDING password_hash, or None.
        Table-missing degrades to None (treated as empty)."""
        table = self._get_table()

        def _call():
            return table.get_item(Key={"username": username})

        try:
            resp = await asyncio.to_thread(_call)
        except Exception as e:
            if self._is_missing_table(e):
                logger.warning(
                    f"user_store: table {self._table_name!r} missing; treating user "
                    f"{username!r} as absent"
                )
                return None
            logger.warning(f"user_store: get_item failed for {username!r}: {e}")
            return None
        return resp.get("Item")

    async def list(self) -> list[dict[str, Any]]:
        """Return safe views of all users. Table-missing degrades to []."""
        table = self._get_table()

        def _call():
            items: list[dict] = []
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
            items = await asyncio.to_thread(_call)
        except Exception as e:
            if self._is_missing_table(e):
                logger.warning(
                    f"user_store: table {self._table_name!r} missing; list() -> []"
                )
                return []
            # Any OTHER error (e.g. AccessDenied, throttling) must NOT be
            # swallowed as "empty": that would make _needs_setup() wrongly
            # report needs_setup=true and send an initialized deployment to the
            # /setup wizard. Re-raise so the caller surfaces a real error.
            logger.error(f"user_store: scan failed (re-raising): {e}")
            raise
        users = [_safe_view(it) for it in items]
        users.sort(key=lambda u: (u.get("username") or ""))
        return users

    # ---- writes ----------------------------------------------------------

    async def create(
        self, username: str, password: str, role: str = "user"
    ) -> dict[str, Any]:
        """Create a user. Raises ValueError if it already exists, the role is
        invalid, or username/password are empty. Returns the safe view."""
        if not isinstance(username, str) or not username.strip():
            raise ValueError("username must be a non-empty string")
        username = username.strip()
        if role not in VALID_ROLES:
            raise ValueError(f"invalid role {role!r}: must be one of {list(VALID_ROLES)}")
        if not password:
            raise ValueError("password must be a non-empty string")

        existing = await self._get_raw(username)
        if existing is not None:
            raise ValueError(f"user {username!r} already exists")

        item = {
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "created_at": int(time.time()),
            "disabled": False,
        }
        table = self._get_table()
        # Conditional put guards against a race where two creates land at once.
        # On a concurrent collision DynamoDB raises ClientError
        # (ConditionalCheckFailedException), NOT the ValueError that the
        # _get_raw pre-check above raises. Normalize it to the SAME
        # ValueError("already exists") so every caller sees uniform semantics
        # whether the dup was caught by the pre-check or lost the write race.
        try:
            await asyncio.to_thread(
                lambda: table.put_item(
                    Item=item, ConditionExpression="attribute_not_exists(username)"
                )
            )
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ValueError(f"user {username!r} already exists") from e
            raise
        return _safe_view(item)

    async def set_password(self, username: str, password: str) -> bool:
        """Reset a user's password. Returns False if the user does not exist."""
        if not password:
            raise ValueError("password must be a non-empty string")
        if await self._get_raw(username) is None:
            return False
        new_hash = hash_password(password)
        table = self._get_table()
        await asyncio.to_thread(
            lambda: table.update_item(
                Key={"username": username},
                UpdateExpression="SET password_hash = :h",
                ExpressionAttributeValues={":h": new_hash},
            )
        )
        return True

    async def set_role(self, username: str, role: str) -> bool:
        """Change a user's role. Returns False if the user does not exist."""
        if role not in VALID_ROLES:
            raise ValueError(f"invalid role {role!r}: must be one of {list(VALID_ROLES)}")
        if await self._get_raw(username) is None:
            return False
        table = self._get_table()
        await asyncio.to_thread(
            lambda: table.update_item(
                Key={"username": username},
                UpdateExpression="SET #r = :r",
                ExpressionAttributeNames={"#r": "role"},
                ExpressionAttributeValues={":r": role},
            )
        )
        return True

    async def set_disabled(self, username: str, disabled: bool) -> bool:
        """Enable/disable a user. Returns False if the user does not exist."""
        if await self._get_raw(username) is None:
            return False
        table = self._get_table()
        await asyncio.to_thread(
            lambda: table.update_item(
                Key={"username": username},
                UpdateExpression="SET disabled = :d",
                ExpressionAttributeValues={":d": bool(disabled)},
            )
        )
        return True

    async def delete(self, username: str) -> bool:
        """Delete a user. Returns True if a row was removed."""
        table = self._get_table()

        def _call():
            return table.delete_item(
                Key={"username": username}, ReturnValues="ALL_OLD"
            )

        try:
            resp = await asyncio.to_thread(_call)
        except Exception as e:
            if self._is_missing_table(e):
                return False
            raise
        return bool(resp.get("Attributes"))

    async def verify(self, username: str, password: str) -> dict[str, Any] | None:
        """Return the safe view of the user iff the password matches AND the
        account is not disabled; otherwise None.

        Constant-ish: a missing user still runs a dummy bcrypt check is overkill
        here (the table lookup already leaks timing), so we return early on miss.
        """
        item = await self._get_raw(username)
        if not item:
            return None
        if bool(item.get("disabled")):
            return None
        if not check_password(password, item.get("password_hash") or ""):
            return None
        return _safe_view(item)
