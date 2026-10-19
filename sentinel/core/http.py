"""HTTP layer: pooled per-thread sessions, per-host rate limits, circuit breaker,
secret-safe error messages, and a throttled yfinance Ticker cache."""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sentinel.config import (
    API_RATE_LIMIT_DEFAULT, API_RATE_LIMITS,
    CIRCUIT_BREAKER_RECOVERY_SECS, CIRCUIT_BREAKER_THRESHOLD,
    HTTP_POOL_CONNECTIONS, HTTP_POOL_MAXSIZE,
    HTTP_RETRY_BACKOFF, HTTP_RETRY_STATUS_FORCELIST, HTTP_RETRY_TOTAL,
    YF_CACHE_MAX_SIZE, YF_CACHE_TTL, YF_MAX_CONCURRENT, YF_MIN_GAP,
)

try:
    from orjson import loads as _json_loads
except ImportError:  # pragma: no cover
    from json import loads as _json_loads

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

logger = logging.getLogger("sentinel.http")


_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

_http_local = threading.local()


def _get_http_session() -> requests.Session:
    """Per-thread Session (requests.Session is not thread-safe)."""
    session = getattr(_http_local, "session", None)
    if session is not None:
        return session
    session = requests.Session()
    retry = Retry(
        total=HTTP_RETRY_TOTAL,
        connect=1,
        read=0,  # a read timeout already cost `timeout` seconds; don't triple it

        backoff_factor=HTTP_RETRY_BACKOFF,
        status_forcelist=HTTP_RETRY_STATUS_FORCELIST,
        # POST is retried only for the read-only Hyperliquid info endpoint,
        # which is idempotent.
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(
        pool_connections=HTTP_POOL_CONNECTIONS,
        pool_maxsize=HTTP_POOL_MAXSIZE,
        max_retries=retry,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": _UA, "Accept": "application/json"})
    _http_local.session = session
    return session


# ── Metrics
_metrics_lock = threading.Lock()
_request_metrics: dict[str, dict] = {}


def _record_metric(api_domain: str, latency_ms: float, is_error: bool = False) -> None:
    with _metrics_lock:
        m = _request_metrics.setdefault(api_domain, {
            "count": 0, "errors": 0, "total_ms": 0.0, "max_ms": 0.0,
        })
        m["count"] += 1
        m["total_ms"] += latency_ms
        m["max_ms"] = max(m["max_ms"], latency_ms)
        if is_error:
            m["errors"] += 1


def get_request_metrics() -> dict[str, dict]:
    with _metrics_lock:
        return {
            d: {
                "count": m["count"],
                "errors": m["errors"],
                "avg_ms": round(m["total_ms"] / m["count"], 1) if m["count"] else 0.0,
                "max_ms": round(m["max_ms"], 1),
            }
            for d, m in _request_metrics.items()
        }


# ── Per-host rate limiting
_rate_lock = threading.Lock()
_next_slot: dict[str, float] = {}


def _enforce_api_rate_limit(domain: str) -> None:
    """Reserve the next request slot for *domain* and sleep until it arrives."""
    min_gap = API_RATE_LIMITS.get(domain, API_RATE_LIMIT_DEFAULT)
    with _rate_lock:
        now = time.monotonic()
        slot = max(now, _next_slot.get(domain, 0.0))
        _next_slot[domain] = slot + min_gap
    wait = slot - time.monotonic()
    if wait > 0:
        time.sleep(wait)


# ── Secret redaction (errors can echo full URLs with query-string keys)
_KEY_PATTERN = re.compile(
    r"\b(api[_-]?key|apikey|access[_-]?key|client[_-]?secret|token|secret|password|authorization|key)"
    r"([=:]\s*)[\"']?([^\s&\"']{6,})[\"']?",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(r"\b(Bearer)\s+[^\s,;]{8,}", re.IGNORECASE)


def _sanitize_error(msg) -> str:
    """Strip API keys / tokens from text before it is logged or displayed."""
    # Bearer first: "Authorization: Bearer <tok>" would otherwise redact only the word "Bearer".
    text = _BEARER_PATTERN.sub(r"\1 ***", str(msg))
    return _KEY_PATTERN.sub(lambda m: m.group(0) if m.group(3) == "Bearer" else f"{m.group(1)}{m.group(2)}***", text)


# ── Circuit breaker
_cb_lock = threading.Lock()
_API_CIRCUIT_BREAKERS: dict[str, dict] = {}


def _breaker_open(host: str) -> bool:
    with _cb_lock:
        cb = _API_CIRCUIT_BREAKERS.get(host)
        return bool(
            cb and cb["failures"] >= CIRCUIT_BREAKER_THRESHOLD
            and (time.monotonic() - cb["last_fail"]) < CIRCUIT_BREAKER_RECOVERY_SECS
        )


def _breaker_result(host: str, ok: bool) -> None:
    with _cb_lock:
        cb = _API_CIRCUIT_BREAKERS.setdefault(host, {"failures": 0, "last_fail": 0.0})
        if ok:
            cb["failures"] = 0
        else:
            cb["failures"] += 1
            cb["last_fail"] = time.monotonic()


def _request_json(method, url, params=None, headers=None, json_body=None, timeout=10):
    host = urlparse(url).netloc
    if _breaker_open(host):
        logger.warning("Circuit breaker open for %s — skipping request", host)
        return None
    session = _get_http_session()
    _enforce_api_rate_limit(host)
    t0 = time.monotonic()
    try:
        r = session.request(method, url, params=params, headers=headers, json=json_body, timeout=timeout)
        _record_metric(host, (time.monotonic() - t0) * 1000, is_error=r.status_code >= 400)
        r.raise_for_status()
        data = _json_loads(r.content)
        _breaker_result(host, True)
        return data
    except Exception as exc:
        _record_metric(host, (time.monotonic() - t0) * 1000, is_error=True)
        _breaker_result(host, False)
        # Never log the exception object directly: requests embeds the full URL.
        logger.error("Request failed for %s: %s", host, _sanitize_error(exc))
        return None


def _fetch_robust_json(url, params=None, headers=None, timeout=10):
    """GET JSON with pooling, rate limiting, circuit breaker. Returns None on failure."""
    return _request_json("GET", url, params=params, headers=headers, timeout=timeout)


def _post_robust_json(url, payload, headers=None, timeout=10):
    """POST a JSON body and decode a JSON response. Returns None on failure."""
    return _request_json("POST", url, headers=headers, json_body=payload, timeout=timeout)


# ── yfinance Ticker cache (Ticker objects keep their own HTTP session)
class _LRUTickerCache:
    def __init__(self, maxsize=200, ttl=120):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key):
        entry = self._cache.get(key)
        if entry is None:
            return None
        obj, ts = entry
        if time.monotonic() - ts >= self._ttl:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return obj

    def put(self, key, obj):
        self._cache[key] = (obj, time.monotonic())
        self._cache.move_to_end(key)
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


_yf_semaphore = threading.BoundedSemaphore(YF_MAX_CONCURRENT)
_yf_lock = threading.Lock()
_yf_last_request = 0.0
_yf_ticker_cache = _LRUTickerCache(maxsize=YF_CACHE_MAX_SIZE, ttl=YF_CACHE_TTL)


def get_yf_ticker(ticker):
    """Cached, throttled ``yf.Ticker`` (None if yfinance is unavailable)."""
    global _yf_last_request
    if yf is None:
        return None
    key = str(ticker or "").strip().upper()
    if not key:
        return None
    with _yf_lock:
        cached = _yf_ticker_cache.get(key)
        if cached is not None:
            return cached
        wait = max(0.0, YF_MIN_GAP - (time.monotonic() - _yf_last_request))
        _yf_last_request = time.monotonic() + wait
    if wait > 0:
        time.sleep(wait)
    tk = yf.Ticker(key)
    with _yf_lock:
        _yf_ticker_cache.put(key, tk)
    return tk
