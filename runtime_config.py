"""Runtime config: in-memory cache + atomic JSON persistence for web/phone defaults.

Replaces the static module-level constants (DEFAULT_LANG, PHONE_ENGINE, ...) with a
mutable runtime layer so the Admin UI can change Web and Phone defaults without
restarting the service. Per-call hot-reload: a new /ws or /phone/ws connection
reads the current snapshot at endpoint entry; in-flight calls keep the values
they captured at start.

Storage: <project_root>/config/runtime.json
Schema:
    {
      "web":   { lang, engine, scenario, model, provider, voice, minimax_model },
      "phone": { engine, lang, scenario, voice, provider, model, minimax_model },
      "_meta": { "version": 1, "updated_at": "<iso8601>" }
    }

If the file is missing or any field is absent, the fallback dict (passed by the
caller — typically built from the existing module constants + PHONE_* env at
import time) fills the gap. Corrupt JSON is treated as "missing" and reseeded.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class RuntimeConfig:
    """Thread-safe runtime config with file-backed persistence."""

    _SCHEMA_VERSION = 1

    def __init__(self, path: str, fallback: dict[str, dict[str, Any]]):
        """Args:
            path: absolute path to the JSON file (created if missing).
            fallback: dict with at least "web" and "phone" sub-dicts. Used both
                as the source for the initial seed file and for filling missing
                fields on subsequent reads.
        """
        if "web" not in fallback or "phone" not in fallback:
            raise ValueError("fallback must contain 'web' and 'phone' keys")
        self._path = path
        self._fallback = {
            "web": dict(fallback["web"]),
            "phone": dict(fallback["phone"]),
        }
        self._lock = threading.RLock()
        self._cache: dict[str, dict[str, Any]] | None = None

    # ---- public API ----------------------------------------------------

    def get_web_defaults(self) -> dict[str, Any]:
        """Return current Web defaults, falling back per-field if absent."""
        return self._merge_segment("web")

    def get_phone_defaults(self) -> dict[str, Any]:
        """Return current Phone defaults, falling back per-field if absent."""
        return self._merge_segment("phone")

    def update_web(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge `updates` into the web segment, persist, and return the new
        merged web dict."""
        return self._update_segment("web", updates)

    def update_phone(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Same as update_web but for the phone segment."""
        return self._update_segment("phone", updates)

    def reload(self) -> None:
        """Drop the in-memory cache. Next read reloads from disk."""
        with self._lock:
            self._cache = None

    # ---- internals -----------------------------------------------------

    def _merge_segment(self, segment: str) -> dict[str, Any]:
        store = self._ensure_loaded()
        merged = dict(self._fallback[segment])
        merged.update(store.get(segment, {}))
        return merged

    def _update_segment(self, segment: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            store = self._ensure_loaded()
            current = dict(store.get(segment, {}))
            current.update(updates)
            store[segment] = current
            store["_meta"] = {
                "version": self._SCHEMA_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            self._write_atomic(store)
            self._cache = store
            merged = dict(self._fallback[segment])
            merged.update(current)
            return merged

    def _ensure_loaded(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if self._cache is not None:
                return self._cache
            self._cache = self._load_or_seed()
            return self._cache

    def _load_or_seed(self) -> dict[str, dict[str, Any]]:
        if not os.path.exists(self._path):
            seed = self._build_seed()
            self._write_atomic(seed)
            logger.info(f"runtime_config: seeded new {self._path}")
            return seed
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "web" not in data or "phone" not in data:
                raise ValueError("missing web/phone keys")
            data.setdefault("web", {})
            data.setdefault("phone", {})
            return data
        except Exception as e:
            logger.warning(
                f"runtime_config: {self._path} unreadable ({type(e).__name__}: {e}); reseeding"
            )
            seed = self._build_seed()
            self._write_atomic(seed)
            return seed

    def _build_seed(self) -> dict[str, dict[str, Any]]:
        return {
            "web": dict(self._fallback["web"]),
            "phone": dict(self._fallback["phone"]),
            "_meta": {
                "version": self._SCHEMA_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        }

    def _write_atomic(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        # NamedTemporaryFile in same dir so os.replace is atomic on POSIX.
        dir_ = os.path.dirname(self._path) or "."
        fd, tmp = tempfile.mkstemp(prefix=".runtime_config.", suffix=".tmp", dir=dir_)
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
