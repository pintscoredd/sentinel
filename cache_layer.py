#!/usr/bin/env python3
"""SENTINEL — Cache Layer

Replaces @st.cache_data with cachetools.TTLCache for production use.
Provides a unified caching decorator that works in both Streamlit
and non-Streamlit contexts (CLI, tests, multi-worker deployments).

Features:
- TTL-based expiration with configurable per-function TTLs
- Thread-safe via locking
- Cache hit/miss metrics for observability
- Optional cache warming support
- Backward-compatible with @st.cache_data signature
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from typing import Any, Callable

try:
    from cachetools import TTLCache
except ImportError:
    class TTLCache(dict):
        """Minimal TTLCache fallback — no TTL eviction, just an LRU-ish dict."""
        def __init__(self, maxsize=128, ttl=300):
            super().__init__()
            self._maxsize = maxsize
            self._ttl = ttl

        def __setitem__(self, key, value):
            if len(self) >= self._maxsize:
                try:
                    oldest = next(iter(self))
                    del self[oldest]
                except StopIteration:
                    pass
            super().__setitem__(key, (value, time.time()))

        def __getitem__(self, key):
            value, ts = super().__getitem__(key)
            if time.time() - ts > self._ttl:
                del self[key]
                raise KeyError(key)
            return value

        def get(self, key, default=None):
            try:
                return self[key]
            except KeyError:
                return default


logger = logging.getLogger("sentinel.cache")


_metrics_lock = threading.Lock()
_cache_metrics: dict[str, dict[str, int]] = {}


def _record_cache_hit(func_name: str) -> None:
    with _metrics_lock:
        m = _cache_metrics.setdefault(func_name, {"hits": 0, "misses": 0})
        m["hits"] += 1


def _record_cache_miss(func_name: str) -> None:
    with _metrics_lock:
        m = _cache_metrics.setdefault(func_name, {"hits": 0, "misses": 0})
        m["misses"] += 1


def get_cache_metrics() -> dict[str, dict[str, Any]]:
    """Return cache hit/miss statistics for all cached functions."""
    with _metrics_lock:
        result = {}
        for name, m in _cache_metrics.items():
            total = m["hits"] + m["misses"]
            result[name] = {
                "hits": m["hits"],
                "misses": m["misses"],
                "total": total,
                "hit_rate_pct": round(m["hits"] / total * 100, 1) if total > 0 else 0.0,
            }
        return result


def reset_cache_metrics() -> None:
    """Reset all cache metrics."""
    with _metrics_lock:
        _cache_metrics.clear()


_cache_registry: dict[str, TTLCache] = {}
_registry_lock = threading.Lock()


def get_cache_registry() -> dict[str, TTLCache]:
    """Return all registered caches for inspection/warming."""
    with _registry_lock:
        return dict(_cache_registry)


def invalidate_cache(func_name: str) -> bool:
    """Clear a specific function's cache by name."""
    with _registry_lock:
        cache = _cache_registry.get(func_name)
        if cache is not None:
            cache.clear()
            return True
        return False


def invalidate_all_caches() -> int:
    """Clear all registered caches. Returns count cleared."""
    with _registry_lock:
        count = 0
        for cache in _cache_registry.values():
            cache.clear()
            count += 1
        return count


def _is_streamlit_available() -> bool:
    """Check if running inside a Streamlit context."""
    try:
        import streamlit as st
        return hasattr(st, "cache_data") and hasattr(st, "session_state")
    except ImportError:
        return False


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


def cached(ttl: int = 300, maxsize: int = 128):
    def decorator(func: Callable) -> Callable:
        func_name = f"{func.__module__}.{func.__qualname__}"

        if _is_streamlit_available():
            import streamlit as st
            cached_func = st.cache_data(ttl=ttl)(func)

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return cached_func(*args, **kwargs)

            wrapper._cache_clear = getattr(cached_func, "clear", lambda: None)
            return wrapper

        cache = TTLCache(maxsize=maxsize, ttl=ttl)
        lock = threading.Lock()

        with _registry_lock:
            _cache_registry[func_name] = cache

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_cache_key(args, kwargs)

            with lock:
                try:
                    result = cache[key]
                    _record_cache_hit(func_name)
                    return result
                except KeyError:
                    pass

            _record_cache_miss(func_name)
            result = func(*args, **kwargs)

            with lock:
                try:
                    cache[key] = result
                except ValueError:
                    pass

            return result

        wrapper._cache = cache
        wrapper._cache_clear = cache.clear
        return wrapper

    return decorator
