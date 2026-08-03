#!/usr/bin/env python3
"""SENTINEL — HTTP Client Layer

Centralized HTTP infrastructure: connection pooling, rate limiting,
circuit breaker, request metrics, and async execution.

Extracted from data_fetchers.py to create a reusable, testable HTTP layer.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    HTTP_POOL_CONNECTIONS, HTTP_POOL_MAXSIZE,
    HTTP_RETRY_TOTAL, HTTP_RETRY_BACKOFF, HTTP_RETRY_STATUS_FORCELIST,
    CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_RECOVERY_SECS,
    API_RATE_LIMITS, API_RATE_LIMIT_DEFAULT,
    YF_MAX_CONCURRENT, YF_MIN_GAP, YF_CACHE_TTL, YF_CACHE_MAX_SIZE,
)

try:
    from orjson import loads as _json_loads
except ImportError:
    from json import loads as _json_loads

try:
    import yfinance as yf
except ImportError:
    yf = None


logger = logging.getLogger("sentinel.http")


_http_local = threading.local()


def _get_http_session() -> requests.Session:
    """Return a per-thread requests.Session with connection pooling and auto-retry.
    
    requests.Session is NOT thread-safe. Using threading.local() ensures each
    thread gets its own session, preventing connection pool corruption under
    concurrent load (ThreadPoolExecutor, @st.fragment, etc.).
    """
    if hasattr(_http_local, "session"):
        return _http_local.session
    session = requests.Session()
    retry_strategy = Retry(
        total=HTTP_RETRY_TOTAL,
        backoff_factor=HTTP_RETRY_BACKOFF,
        status_forcelist=HTTP_RETRY_STATUS_FORCELIST,
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(
        pool_connections=HTTP_POOL_CONNECTIONS,
        pool_maxsize=HTTP_POOL_MAXSIZE,
        max_retries=retry_strategy,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/122.0.0.0 Safari/537.36",
    })
    _http_local.session = session
    return _http_local.session


_metrics_lock = threading.Lock()
_request_metrics: dict[str, dict] = {}


def _record_metric(api_domain: str, latency_ms: float, is_error: bool = False) -> None:
    """Record a single request metric (thread-safe)."""
    with _metrics_lock:
        m = _request_metrics.setdefault(api_domain, {
            "count": 0, "errors": 0,
            "total_ms": 0.0, "min_ms": float("inf"), "max_ms": 0.0,
        })
        m["count"] += 1
        m["total_ms"] += latency_ms
        if latency_ms < m["min_ms"]:
            m["min_ms"] = latency_ms
        if latency_ms > m["max_ms"]:
            m["max_ms"] = latency_ms
        if is_error:
            m["errors"] += 1


def get_request_metrics() -> dict[str, dict]:
    """Return per-API request metrics snapshot."""
    with _metrics_lock:
        snapshot = {}
        for domain, m in _request_metrics.items():
            avg = m["total_ms"] / m["count"] if m["count"] > 0 else 0.0
            err_rate = (m["errors"] / m["count"] * 100) if m["count"] > 0 else 0.0
            snapshot[domain] = {
                "count": m["count"],
                "errors": m["errors"],
                "avg_ms": round(avg, 1),
                "min_ms": round(m["min_ms"], 1) if m["min_ms"] != float("inf") else 0.0,
                "max_ms": round(m["max_ms"], 1),
                "error_rate_pct": round(err_rate, 1),
            }
        return snapshot


def reset_request_metrics() -> None:
    """Reset all request metrics."""
    with _metrics_lock:
        _request_metrics.clear()


_api_rate_limits_lock = threading.Lock()
_api_rate_limits: dict[str, float] = {}
_api_domain_locks: dict[str, threading.Lock] = {}


def _get_domain_lock(domain: str) -> threading.Lock:
    with _api_rate_limits_lock:
        lock = _api_domain_locks.get(domain)
        if lock is None:
            lock = threading.Lock()
            _api_domain_locks[domain] = lock
        return lock


def _enforce_api_rate_limit(domain: str) -> None:
    min_gap = API_RATE_LIMITS.get(domain, API_RATE_LIMIT_DEFAULT)
    lock = _get_domain_lock(domain)
    with lock:
        last = _api_rate_limits.get(domain, 0.0)
        elapsed = time.time() - last
        need_sleep = max(0.0, min_gap - elapsed)
        _api_rate_limits[domain] = time.time() + need_sleep

    if need_sleep > 0:
        time.sleep(need_sleep)


_KEY_PATTERN = re.compile(
    r"(api[_-]?key|apikey|token|secret|password|authorization)"
    r"[=:]\s*[\"']?([A-Za-z0-9_\-]{8,})[\"']?",
    re.IGNORECASE,
)


def _sanitize_error(msg: str) -> str:
    """Strip potential API keys from error messages before logging/display."""
    return _KEY_PATTERN.sub(r"\1=***REDACTED***", msg)


_cb_lock = threading.Lock()
_API_CIRCUIT_BREAKERS: dict[str, dict] = {}


def get_circuit_breaker_states() -> dict[str, dict]:
    """Return current circuit breaker states for monitoring."""
    with _cb_lock:
        return {
            domain: {
                "failures": cb["failures"],
                "last_fail": datetime.fromtimestamp(cb["last_fail"]).isoformat()
                if cb["last_fail"] > 0 else "never",
                "open": cb["failures"] >= CIRCUIT_BREAKER_THRESHOLD
                and (time.time() - cb["last_fail"]) < CIRCUIT_BREAKER_RECOVERY_SECS,
            }
            for domain, cb in _API_CIRCUIT_BREAKERS.items()
        }


def _do_fetch_robust_json(url, params=None, headers=None, timeout=10):
    """Low-level JSON fetch with pooling, metrics, rate limiting, and sanitized errors."""
    session = _get_http_session()
    req_headers = dict(session.headers)
    if headers:
        req_headers.update(headers)
    if "User-Agent" not in req_headers or "SENTINEL" in req_headers.get("User-Agent", ""):
        req_headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )

    api_domain = urlparse(url).netloc
    t0 = time.time()

    _enforce_api_rate_limit(api_domain)

    try:
        r = session.get(url, params=params, headers=req_headers, timeout=timeout)
        latency_ms = (time.time() - t0) * 1000
        _record_metric(api_domain, latency_ms, is_error=(r.status_code >= 400))
        r.raise_for_status()
        return _json_loads(r.content)
    except Exception as exc:
        latency_ms = (time.time() - t0) * 1000
        _record_metric(api_domain, latency_ms, is_error=True)
        _sanitized_msg = _sanitize_error(str(exc))
        raise RuntimeError(f"API request failed ({api_domain}): {_sanitized_msg}") from None


def _fetch_robust_json(url, params=None, headers=None, timeout=10):
    """Centralized JSON fetcher with circuit breaker, pooling, and metrics."""
    api_name = urlparse(url).netloc

    with _cb_lock:
        cb = _API_CIRCUIT_BREAKERS.setdefault(api_name, {"failures": 0, "last_fail": 0})
        if cb["failures"] >= CIRCUIT_BREAKER_THRESHOLD and (time.time() - cb["last_fail"]) < CIRCUIT_BREAKER_RECOVERY_SECS:
            logger.warning(f"Circuit breaker open for {api_name} - skipping request")
            return None

    try:
        res = _do_fetch_robust_json(url, params=params, headers=headers, timeout=timeout)
        with _cb_lock:
            cb = _API_CIRCUIT_BREAKERS.setdefault(api_name, {"failures": 0, "last_fail": 0})
            cb["failures"] = 0
        return res
    except Exception as e:
        with _cb_lock:
            cb = _API_CIRCUIT_BREAKERS.setdefault(api_name, {"failures": 0, "last_fail": 0})
            cb["failures"] = cb["failures"] + 1
            cb["last_fail"] = time.time()
        logger.error(f"Request failed for {api_name}: {e}")
        return None


_async_loop = None
_async_thread = None
_async_loop_lock = threading.Lock()


def _get_persistent_loop():
    """Return a persistent event loop running on a dedicated background thread.
    
    Thread-safe: uses a lock to prevent duplicate loops on Streamlit
    hot-reload. The loop is also stashed as an attribute on its own thread
    object. If a module reload wipes the module-level `_async_loop`
    reference while the thread is still alive, we recover the loop from
    the thread itself and stop it cleanly — otherwise we'd skip stopping
    it entirely and leak a zombie thread running an orphaned loop forever.
    """
    global _async_loop, _async_thread
    with _async_loop_lock:
        if _async_loop is not None and _async_loop.is_running():
            return _async_loop

        if _async_thread is not None and _async_thread.is_alive():
            stale_loop = _async_loop if _async_loop is not None else getattr(
                _async_thread, "_sentinel_loop", None
            )
            if stale_loop is not None:
                try:
                    stale_loop.call_soon_threadsafe(stale_loop.stop)
                    _async_thread.join(timeout=2)
                except Exception:
                    pass

        _async_loop = asyncio.new_event_loop()
        _async_thread = threading.Thread(
            target=_async_loop.run_forever,
            daemon=True,
            name="sentinel-async-loop",
        )
        _async_thread._sentinel_loop = _async_loop
        _async_thread.start()
        return _async_loop


def run_async(coro):
    """Run an async coroutine on the persistent event loop."""
    loop = _get_persistent_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=60)


class _LRUTickerCache:
    """Thread-safe LRU cache for yfinance Ticker objects with TTL eviction."""
    __slots__ = ("_cache", "_maxsize", "_ttl", "_hits", "_misses")

    def __init__(self, maxsize=200, ttl=120):
        self._cache = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def get(self, key):
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        obj, ts = entry
        if (time.time() - ts) >= self._ttl:
            del self._cache[key]
            self._misses += 1
            return None
        self._cache.move_to_end(key)
        self._hits += 1
        return obj

    def put(self, key, obj):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (obj, time.time())
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    @property
    def stats(self):
        total = self._hits + self._misses
        rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "maxsize": self._maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(rate, 1),
        }

    def __len__(self):
        return len(self._cache)


_yf_semaphore = threading.BoundedSemaphore(YF_MAX_CONCURRENT)
_yf_lock = threading.Lock()
_yf_last_request = 0.0
_yf_ticker_cache = _LRUTickerCache(maxsize=YF_CACHE_MAX_SIZE, ttl=YF_CACHE_TTL)


def get_yf_ticker(ticker):
    if yf is None:
        return None
    global _yf_last_request

    key = str(ticker).strip().upper() if ticker else ""
    if not key:
        return None

    with _yf_lock:
        cached = _yf_ticker_cache.get(key)
        if cached is not None:
            return cached

    _yf_semaphore.acquire()
    try:
        with _yf_lock:
            cached = _yf_ticker_cache.get(key)
            if cached is not None:
                return cached
            elapsed = time.time() - _yf_last_request
            need_sleep = max(0.0, YF_MIN_GAP - elapsed)
            _yf_last_request = time.time() + need_sleep

        if need_sleep > 0:
            time.sleep(need_sleep)

        tk = yf.Ticker(key)

        with _yf_lock:
            _yf_ticker_cache.put(key, tk)
        return tk
    finally:
        _yf_semaphore.release()


def get_ticker_cache_stats() -> dict:
    """Return LRU ticker cache statistics for monitoring."""
    with _yf_lock:
        return _yf_ticker_cache.stats


def _safe_float(v, default=0):
    """Convert to float, returning default for invalid/missing values."""
    if v is None:
        return default
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError, OverflowError):
        return default


def _safe_int(v, default: int = 0) -> int:
    try:
        f = float(v) if v is not None else float(default)
        return default if (math.isnan(f) or math.isinf(f)) else int(f)
    except (ValueError, TypeError, OverflowError):
        return default


def _esc(t) -> str:
    """HTML-escape a string."""
    return (
        str(t)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        if t
        else ""
    )


# Index / rate tickers: no currency prefix (Bloomberg-style bare quotes)
_INDEX_LIKE = frozenset({
    "^GSPC", "^DJI", "^IXIC", "^RUT", "^VIX", "^TNX", "^TYX", "^FVX", "^IRX",
    "^GSPTSE", "^BVSP", "^FTSE", "^GDAXI", "^FCHI", "^STOXX50E", "^N225",
    "^HSI", "^KS11", "^AXJO", "^BSESN", "^AEX", "^TA125.TA", "000001.SS",
    "DX-Y.NYB", "DX=F",
})


def _is_index_ticker(ticker=None):
    if not ticker:
        return False
    t = str(ticker).upper().strip()
    if t in _INDEX_LIKE or t.startswith("^"):
        return True
    # Yields quoted as percent levels
    if t in {"^TNX", "^TYX", "^FVX", "^IRX"}:
        return True
    return False


def fmt_p(p, ticker=None):
    """Format price. Indices/yields omit '$'; micro-prices get more decimals."""
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "—"
    if math.isinf(p):
        return "—"
    if _is_index_ticker(ticker):
        if abs(p) >= 1000:
            return f"{p:,.2f}"
        if abs(p) >= 10:
            return f"{p:,.2f}"
        return f"{p:.3f}"
    if abs(p) < 0.01 and p != 0:
        return f"${p:.6f}"
    if abs(p) < 1:
        return f"${p:.4f}"
    return f"${p:,.2f}"


def fmt_num(p, decimals: int = 2) -> str:
    """Bare number with thousands separators (levels, counts, yields)."""
    if p is None or (isinstance(p, float) and (math.isnan(p) or math.isinf(p))):
        return "—"
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "—"
    return f"{p:,.{decimals}f}"


def fmt_vol(v) -> str:
    """Compact volume: 1.2B / 45.3M / 120.5K."""
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(v) or v < 0:
        return "—"
    if v >= 1e9:
        return f"{v / 1e9:.2f}B"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{v / 1e3:.1f}K"
    return f"{int(v)}"


def fmt_pct(p) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    s = "+" if p >= 0 else ""
    return f"{s}{p:.2f}%"


def pct_color(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "#888888"
    if v > 0:
        return "#00CC44"
    if v < 0:
        return "#FF4444"
    return "#888888"


def _is_english(text: str) -> bool:
    """Heuristic: reject text where >15% of characters are non-ASCII."""
    if not text:
        return False
    return sum(1 for c in text if ord(c) < 128) / max(len(text), 1) > 0.85
