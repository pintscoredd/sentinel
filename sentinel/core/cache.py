"""Live-source snapshot cache with in-flight dedup and stale fallback."""
from __future__ import annotations

import functools
import threading
import time
from collections import OrderedDict
from typing import Any, Callable


def _make_cache_key(args: tuple, kwargs: dict) -> tuple:
    key_parts = []
    for arg in args:
        try:
            hash(arg)
            key_parts.append(arg)
        except TypeError:
            key_parts.append(repr(arg))

    for k, v in sorted(kwargs.items()):
        try:
            hash(v)
            key_parts.append((k, v))
        except TypeError:
            key_parts.append((k, repr(v)))

    return tuple(key_parts)


def _source_result_has_data(value: Any) -> bool:
    """Return whether a source result is safe to replace the last good value."""
    if value is None:
        return False
    empty = getattr(value, "empty", None)
    if isinstance(empty, bool):
        return not empty
    if isinstance(value, tuple):
        return any(_source_result_has_data(part) for part in value)
    if isinstance(value, (list, dict, set, str, bytes)):
        return len(value) > 0
    return True


def stale_cached_source(
    ttl: int = 300,
    retry_ttl: int = 60,
    maxsize: int = 32,
    is_valid: Callable[[Any], bool] = _source_result_has_data,
):
    """Cache live-source snapshots with in-flight dedup and stale fallback.

    Adapted from OSIRIS ``src/lib/sourceCache.ts`` (MIT). Concurrent misses
    share one fetch. An empty/failed refresh keeps the last good snapshot and
    retries sooner, preventing a transient provider outage from blanking a
    globe layer.
    """
    def decorator(func: Callable) -> Callable:
        entries: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
        condition = threading.Condition(threading.RLock())

        def _evict() -> None:
            while len(entries) > maxsize:
                victim = next(
                    (key for key, item in entries.items() if not item["inflight"]),
                    None,
                )
                if victim is None:
                    break
                entries.pop(victim, None)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_cache_key(args, kwargs)
            with condition:
                while True:
                    now = time.monotonic()
                    entry = entries.get(key)
                    if entry and now < entry["expires_at"] and is_valid(entry["data"]):
                        entries.move_to_end(key)
                        return entry["data"]
                    if not entry or not entry["inflight"]:
                        stale = entry["data"] if entry else None
                        entries[key] = {
                            "data": stale,
                            "expires_at": entry["expires_at"] if entry else 0.0,
                            "inflight": True,
                        }
                        entries.move_to_end(key)
                        _evict()
                        break
                    condition.wait()

            try:
                fresh = func(*args, **kwargs)
            except Exception:
                with condition:
                    entry = entries.get(key)
                    if entry is None:
                        entry = {"data": None, "expires_at": 0.0, "inflight": True}
                        entries[key] = entry
                    entry["inflight"] = False
                    entry["expires_at"] = time.monotonic() + retry_ttl
                    condition.notify_all()
                    if is_valid(entry["data"]):
                        return entry["data"]
                raise

            with condition:
                entry = entries.get(key)
                if entry is None:
                    entry = {"data": None, "expires_at": 0.0, "inflight": True}
                    entries[key] = entry
                if is_valid(fresh):
                    entry["data"] = fresh
                    entry["expires_at"] = time.monotonic() + ttl
                else:
                    # Empty refreshes commonly mean rate-limit/outage, not that
                    # every aircraft, vessel, or satellite disappeared.
                    if not is_valid(entry["data"]):
                        entry["data"] = fresh
                    entry["expires_at"] = time.monotonic() + retry_ttl
                entry["inflight"] = False
                condition.notify_all()
                return entry["data"]

        def clear() -> None:
            with condition:
                entries.clear()
                condition.notify_all()

        wrapper.clear = clear
        wrapper._cache_clear = clear
        return wrapper

    return decorator
