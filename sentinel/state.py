"""Per-session state, API-key resolution, and watchlist persistence."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from sentinel.config import DATA_DIR, DEFAULT_WATCHLIST, PERSIST_ENV, TZ_PACIFIC
from sentinel.core.secrets import SecretStr, get_secret

logger = logging.getLogger("sentinel.state")


PST = TZ_PACIFIC

# Session keys holding user-overridable API keys → secret name.
KEY_SLOTS = {
    "gemini_key": "GEMINI_API_KEY",
    "fred_key": "FRED_API_KEY",
    "finnhub_key": "FINNHUB_API_KEY",
    "newsapi_key": "NEWSAPI_KEY",
    "cftc_key": "CFTC_API_KEY",
}

_WATCHLIST_FILE = Path(DATA_DIR) / "watchlist.json"
_LEGACY_WATCHLIST_FILE = Path(__file__).resolve().parents[1] / ".sentinel_watchlist.json"
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "0.0.0.0")


def now_pst() -> str:
    return datetime.now(PST).strftime("%Y-%m-%d %H:%M PST")


def persistence_enabled() -> bool:
    """Write watchlist / AI memory to disk only for a local single-user run.

    On a shared deployment those files would leak one visitor's data to every
    other visitor, so it is off unless SENTINEL_PERSIST=1.
    """
    if PERSIST_ENV in ("1", "true", "yes", "on"):
        return True
    if PERSIST_ENV in ("0", "false", "no", "off"):
        return False
    try:
        host = (st.context.headers.get("Host") or "").split(":")[0].lower()
    except Exception:
        return False
    return host in _LOCAL_HOSTS or host.endswith(".localhost")


def _clean_ticker_list(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = []
    for t in raw:
        t = str(t).strip().upper()[:16]
        if t and t not in out:
            out.append(t)
    return out[:40]


def _load_watchlist() -> list[str]:
    if persistence_enabled():
        for path in (_WATCHLIST_FILE, _LEGACY_WATCHLIST_FILE):
            try:
                if path.exists():
                    wl = _clean_ticker_list(json.loads(path.read_text(encoding="utf-8")))
                    if wl:
                        return wl
            except Exception as exc:
                logger.warning("Watchlist load failed (%s): %s", path.name, exc)
    return list(DEFAULT_WATCHLIST)


def save_watchlist(wl: list[str]) -> None:
    """Atomic write so concurrent reruns cannot corrupt the file."""
    if not persistence_enabled():
        return
    try:
        _WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(_WATCHLIST_FILE.parent), prefix=".wl_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(_clean_ticker_list(wl), f)
            os.replace(tmp, _WATCHLIST_FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.error("Watchlist save failed: %s", exc)
        st.toast("Watchlist could not be saved to disk.")


def init_session() -> None:
    ss = st.session_state
    for slot, secret_name in KEY_SLOTS.items():
        if slot not in ss:
            ss[slot] = get_secret(secret_name)
    defaults = {
        "chat_history": [],
        "macro_theses": "",
        "geo_watch": "",
        "master_ticker": "",
        "trade_log_0dte": [],
        "alert_cooldowns": {},
        "alerts_enabled": False,
        "alert_vix_threshold": 25.0,
        "alert_pcr_threshold": 1.2,
        "alert_tickers": "",
        "alert_ticker_prices": "",
        "alert_webhook_url": "",
    }
    for k, v in defaults.items():
        if k not in ss:
            ss[k] = v
    if "watchlist" not in ss:
        ss.watchlist = _load_watchlist()
    # Per-run memo for expensive shared lookups (reset every script run).
    ss._run_memo = {}


def key(slot: str) -> str:
    """Raw API key for *slot* (session override or secret), '' if unset."""
    val = st.session_state.get(slot)
    if isinstance(val, SecretStr):
        return val.get_secret_value()
    return str(val or "").strip()


def has_alpaca() -> bool:
    return bool(get_secret("ALPACA_API_KEY")) and bool(get_secret("ALPACA_SECRET_KEY"))


def memo(name: str, fn, *args):
    """Compute *fn(*args)* at most once per script run."""
    store = st.session_state.setdefault("_run_memo", {})
    k = (name,) + tuple(args)
    if k not in store:
        store[k] = fn(*args)
    return store[k]
