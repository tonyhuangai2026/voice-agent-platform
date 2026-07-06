"""MCP server registry: in-memory cache + atomic JSON persistence.

Global registry of MCP (Model Context Protocol) servers that demos can
mount via the optional ``mcp_servers: [<server-id>, ...]`` manifest field.
Mirrors the :mod:`runtime_config` pattern (thread-safe cache, tempfile +
``os.replace`` atomic writes).

Storage: <project_root>/config/mcp_servers.json  (gitignored — headers may
contain API keys / bearer tokens).
Schema:
    {
      "servers": [
        {
          "id": "weather-api",            // slug, unique
          "label": "Weather API",
          "transport": "streamable_http",  // "sse" | "streamable_http"
          "url": "https://example.com/mcp",
          "headers": {"Authorization": "Bearer ..."},  // optional
          "auth": {"type": "none"},  // optional: none|header|sigv4
          "enabled": true
        }
      ],
      "_meta": {"version": 1, "updated_at": "<iso8601>"}
    }

Validation (raises ``ValueError``):
  - id must match ``^[a-z0-9][a-z0-9-]{1,62}$``
  - transport must be "sse" or "streamable_http" — **stdio is rejected** so
    the admin panel can never become an arbitrary-command-execution surface
    on the EC2 box
  - url must be http(s) with a non-empty host

Secret-preservation sentinel: a header value of ``"***"`` passed to
:meth:`McpConfig.upsert` means "keep the value already stored for this
key" (the admin UI shows masked values and sends them back verbatim when
the admin doesn't retype the secret). Use :func:`mask_headers` to produce
the masked wire shape for GET responses.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SERVER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
ALLOWED_TRANSPORTS = ("sse", "streamable_http")
HEADER_MASK = "***"

# Auth types a server may declare. ``none``/``header`` are the legacy behaviour
# (a missing ``auth`` field is treated as ``none``). ``sigv4`` signs requests
# with AWS SigV4 at connect time using the instance's IAM credentials (no
# secret is ever stored in config) — see mcp_sigv4.py.
ALLOWED_AUTH_TYPES = ("none", "header", "sigv4")
SIGV4_DEFAULT_SERVICE = "bedrock-agentcore"
SIGV4_DEFAULT_REGION = "us-east-1"


def validate_auth(auth: Any) -> dict[str, Any]:
    """Validate + normalize a server ``auth`` object. Returns the canonical
    shape. Raises ``ValueError``.

    Canonical shapes::

        {"type": "none"}
        {"type": "header"}
        {"type": "sigv4", "service": "<str>", "region": "<str>"}

    A missing / ``None`` auth is backward-compatible and normalizes to
    ``{"type": "none"}``. For ``sigv4``, ``service`` defaults to
    ``bedrock-agentcore`` and ``region`` to ``us-east-1`` (both must be
    non-empty strings if supplied); no secret is stored (IAM role is used).
    """
    if auth is None:
        return {"type": "none"}
    if not isinstance(auth, dict):
        raise ValueError("auth must be an object")

    atype = auth.get("type", "none")
    if atype not in ALLOWED_AUTH_TYPES:
        raise ValueError(
            f"invalid auth.type {atype!r}: must be one of {list(ALLOWED_AUTH_TYPES)}"
        )

    if atype == "sigv4":
        service = auth.get("service")
        if service is None:
            service = SIGV4_DEFAULT_SERVICE
        if not isinstance(service, str) or not service:
            raise ValueError("auth.service must be a non-empty string for sigv4")
        region = auth.get("region")
        if region is None:
            region = SIGV4_DEFAULT_REGION
        if not isinstance(region, str) or not region:
            raise ValueError("auth.region must be a non-empty string for sigv4")
        return {"type": "sigv4", "service": service, "region": region}

    # none / header carry no extra fields (header still uses the top-level
    # ``headers`` field, exactly as before).
    return {"type": atype}


def mask_headers(server: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``server`` with every header value replaced by
    ``"***"`` — never echo secrets back over the wire."""
    out = dict(server)
    headers = out.get("headers")
    if isinstance(headers, dict) and headers:
        out["headers"] = {k: HEADER_MASK for k in headers}
    return out


def validate_server(server: dict[str, Any]) -> dict[str, Any]:
    """Validate + normalize a server dict. Returns the canonical shape
    (id/label/transport/url/headers/enabled only). Raises ValueError."""
    if not isinstance(server, dict):
        raise ValueError("server must be an object")

    sid = server.get("id")
    if not isinstance(sid, str) or not SERVER_ID_RE.match(sid):
        raise ValueError(
            f"invalid server id {sid!r}: must match {SERVER_ID_RE.pattern} "
            f"(lowercase slug, 2-63 chars)"
        )

    transport = server.get("transport")
    if transport == "stdio":
        raise ValueError("transport 'stdio' is not supported (security: no command execution)")
    if transport not in ALLOWED_TRANSPORTS:
        raise ValueError(
            f"invalid transport {transport!r}: must be one of {list(ALLOWED_TRANSPORTS)}"
        )

    url = server.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("url is required")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"invalid url {url!r}: must be http(s) with a host")

    label = server.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError("label must be a string")
    label = (label or "").strip() or sid

    headers = server.get("headers")
    if headers is None:
        headers = {}
    if not isinstance(headers, dict):
        raise ValueError("headers must be an object of string -> string")
    for k, v in headers.items():
        if not isinstance(k, str) or not k or not isinstance(v, str):
            raise ValueError(f"invalid header entry {k!r}: keys and values must be strings")

    enabled = server.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")

    # N2: ``auth`` MUST be part of the canonical dict — otherwise upsert()
    # silently strips it and bot.py never sees a sigv4 config. A missing auth
    # normalizes to {"type": "none"} (backward compatible).
    auth = validate_auth(server.get("auth"))

    return {
        "id": sid,
        "label": label,
        "transport": transport,
        "url": url,
        "headers": dict(headers),
        "enabled": enabled,
        "auth": auth,
    }


class McpConfig:
    """Thread-safe MCP server registry with file-backed persistence."""

    _SCHEMA_VERSION = 1

    def __init__(self, path: str):
        """Args:
            path: absolute path to the JSON file. Missing file == empty
                registry (the file is only created on the first write).
        """
        self._path = path
        self._lock = threading.RLock()
        self._cache: dict[str, Any] | None = None

    # ---- public API ----------------------------------------------------

    def list_servers(self) -> list[dict[str, Any]]:
        """Return all servers (deep-ish copies; mutating them is safe)."""
        store = self._ensure_loaded()
        return [dict(s, headers=dict(s.get("headers") or {})) for s in store["servers"]]

    def get(self, server_id: str) -> dict[str, Any] | None:
        """Return one server by id (copy) or None."""
        store = self._ensure_loaded()
        for s in store["servers"]:
            if s.get("id") == server_id:
                return dict(s, headers=dict(s.get("headers") or {}))
        return None

    def upsert(self, server: dict[str, Any]) -> dict[str, Any]:
        """Validate + insert-or-replace a server, persist atomically, and
        return the stored (unmasked) dict.

        Header values equal to ``"***"`` are replaced with the currently
        stored value for the same key (mask round-trip semantics). If
        there is no stored value for that key, the entry is dropped.
        """
        normalized = validate_server(server)
        with self._lock:
            store = self._ensure_loaded()
            existing = next(
                (s for s in store["servers"] if s.get("id") == normalized["id"]), None
            )
            if normalized["headers"]:
                old_headers = (existing or {}).get("headers") or {}
                resolved: dict[str, str] = {}
                for k, v in normalized["headers"].items():
                    if v == HEADER_MASK:
                        if k in old_headers:
                            resolved[k] = old_headers[k]
                        else:
                            logger.warning(
                                f"mcp_config: header {k!r} for {normalized['id']!r} is the "
                                f"mask sentinel but has no stored value; dropping it"
                            )
                    else:
                        resolved[k] = v
                normalized["headers"] = resolved
            if existing is not None:
                idx = store["servers"].index(existing)
                store["servers"][idx] = normalized
            else:
                store["servers"].append(normalized)
            self._persist(store)
            return dict(normalized, headers=dict(normalized["headers"]))

    def delete(self, server_id: str) -> bool:
        """Delete a server by id. Returns True if it existed."""
        with self._lock:
            store = self._ensure_loaded()
            before = len(store["servers"])
            store["servers"] = [s for s in store["servers"] if s.get("id") != server_id]
            if len(store["servers"]) == before:
                return False
            self._persist(store)
            return True

    def reload(self) -> None:
        """Drop the in-memory cache. Next read reloads from disk."""
        with self._lock:
            self._cache = None

    # ---- internals -----------------------------------------------------

    def _ensure_loaded(self) -> dict[str, Any]:
        with self._lock:
            if self._cache is not None:
                return self._cache
            self._cache = self._load()
            return self._cache

    def _load(self) -> dict[str, Any]:
        if not os.path.exists(self._path):
            return {"servers": []}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or not isinstance(data.get("servers"), list):
                raise ValueError("missing 'servers' list")
            data["servers"] = [s for s in data["servers"] if isinstance(s, dict)]
            return data
        except Exception as e:
            logger.warning(
                f"mcp_config: {self._path} unreadable ({type(e).__name__}: {e}); "
                f"treating as empty registry"
            )
            return {"servers": []}

    def _persist(self, store: dict[str, Any]) -> None:
        store["_meta"] = {
            "version": self._SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self._write_atomic(store)
        self._cache = store

    def _write_atomic(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        # NamedTemporaryFile in same dir so os.replace is atomic on POSIX.
        dir_ = os.path.dirname(self._path) or "."
        fd, tmp = tempfile.mkstemp(prefix=".mcp_config.", suffix=".tmp", dir=dir_)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
