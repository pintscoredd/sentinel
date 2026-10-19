"""Sidebar: data-source status, API-key overrides, user context, threshold alerts."""
from __future__ import annotations

import logging
import time

import requests
import streamlit as st

from sentinel.core.formatting import _esc
from sentinel.core.http import _sanitize_error
from sentinel.core.secrets import SecretStr, get_secret
from sentinel.data.market import get_vix_full, multi_quotes
from sentinel.data.zero_dte import compute_cboe_pcr, fetch_cboe_gex
from sentinel.state import has_alpaca, key, now_pst
from sentinel.ui.palette import FLAT, UP

alert_log = logging.getLogger("sentinel.alerts")
_COOLDOWN_S = 300


def _status_rows():
    return [
        ("Yahoo Finance", True, ""), ("Hyperliquid", True, ""), ("Polymarket", True, ""),
        ("GDELT / USGS / NASA", True, ""), ("CFTC COT", True, ""),
        ("FRED", bool(key("fred_key")), "FRED_API_KEY"),
        ("Finnhub", bool(key("finnhub_key")), "FINNHUB_API_KEY"),
        ("NewsAPI", bool(key("newsapi_key")), "NEWSAPI_KEY"),
        ("Gemini", bool(key("gemini_key")), "GEMINI_API_KEY"),
        ("Alpaca (0DTE)", has_alpaca(), "ALPACA_API_KEY"),
        ("Marinesia AIS", bool(get_secret("MARINESIA_API_KEY")), "MARINESIA_API_KEY"),
    ]


def _send_webhook(msg: str) -> None:
    url = (st.session_state.get("alert_webhook_url") or "").strip()
    if not url:
        return
    if not url.startswith("https://"):
        st.toast("Webhook ignored: URL must start with https://")
        return
    try:
        requests.post(url, json={"text": msg, "source": "Sentinel"}, timeout=5)
    except Exception as e:
        alert_log.warning("Webhook failed: %s", _sanitize_error(e))


def _fire(kind: str, msg: str) -> None:
    cd = st.session_state.alert_cooldowns
    now = time.monotonic()
    if now - cd.get(kind, 0) < _COOLDOWN_S:
        return
    cd[kind] = now
    st.toast(msg)
    _send_webhook(msg)
    alert_log.info("[%s] %s", kind, msg)


@st.fragment(run_every="30s")
def _alert_monitor():
    ss = st.session_state
    vix = get_vix_full()[0]
    if vix and vix > ss.alert_vix_threshold:
        _fire("vix", f"VIX {vix:.2f} above {ss.alert_vix_threshold:.1f}")
    _, opts = fetch_cboe_gex("SPX")
    pcr = compute_cboe_pcr(opts)
    if pcr and pcr > ss.alert_pcr_threshold:
        _fire("pcr", f"SPX put/call (OI) {pcr:.2f} above {ss.alert_pcr_threshold:.2f}")
    tickers = [t.strip().upper() for t in ss.alert_tickers.split(",") if t.strip()]
    levels = [p.strip() for p in ss.alert_ticker_prices.split(",")]
    if tickers:
        quotes = {q["ticker"]: q for q in multi_quotes(tuple(tickers))}
        for i, t in enumerate(tickers):
            try:
                lvl = float(levels[i])
            except (IndexError, ValueError):
                continue
            q = quotes.get(t)
            if q and q["price"] > lvl:
                _fire(f"px_{t}", f"{t} {q['price']:,.2f} above {lvl:,.2f}")
    st.markdown(f'<div style="font-size:11px;color:{UP}">Monitoring · checked {time.strftime("%H:%M:%S")}</div>',
                unsafe_allow_html=True)


def render():
    ss = st.session_state
    with st.sidebar:
        st.markdown(
            f'<div style="padding:4px 0 12px"><div class="s-brand">SENTINEL</div>'
            f'<div class="dim" style="font-size:11px;margin-top:2px">{now_pst()}</div></div>',
            unsafe_allow_html=True)

        with st.expander("Data sources", expanded=False):
            rows = "".join(
                f'<div style="display:flex;justify-content:space-between;padding:2px 0">'
                f'<span style="color:{"#EDEDED" if ok else FLAT}">{_esc(name)}</span>'
                f'<span style="color:{UP if ok else FLAT};font-size:11px">{"on" if ok else _esc(hint)}</span></div>'
                for name, ok, hint in _status_rows())
            st.markdown(rows, unsafe_allow_html=True)

        with st.expander("API keys (this session only)", expanded=False):
            st.caption("Overrides apply to your browser session only and are never written to disk.")
            with st.form("api_key_overrides", clear_on_submit=True, border=False):
                vals = {
                    "fred_key": st.text_input("FRED", type="password"),
                    "finnhub_key": st.text_input("Finnhub", type="password"),
                    "newsapi_key": st.text_input("NewsAPI", type="password"),
                    "gemini_key": st.text_input("Gemini", type="password"),
                }
                if st.form_submit_button("Apply", width="stretch"):
                    for slot, v in vals.items():
                        if v.strip():
                            ss[slot] = SecretStr(v.strip())
                    st.rerun()

        with st.expander("My context (for Sentinel AI)", expanded=False):
            ss.macro_theses = st.text_area("Macro theses", value=ss.macro_theses, height=70,
                                           placeholder="e.g. Fed cuts twice by June")
            ss.geo_watch = st.text_area("Geo watch", value=ss.geo_watch, height=60,
                                        placeholder="e.g. Red Sea, Taiwan")

        with st.expander("Threshold alerts", expanded=False):
            ss.alerts_enabled = st.toggle("Enable alerts", value=ss.alerts_enabled)
            a, b = st.columns(2)
            ss.alert_vix_threshold = a.number_input("VIX above", 5.0, 100.0, float(ss.alert_vix_threshold), 1.0)
            ss.alert_pcr_threshold = b.number_input("SPX P/C above", 0.1, 5.0, float(ss.alert_pcr_threshold), 0.1)
            ss.alert_tickers = st.text_input("Tickers", value=ss.alert_tickers, placeholder="AAPL, NVDA")
            ss.alert_ticker_prices = st.text_input("Alert above (same order)", value=ss.alert_ticker_prices,
                                                   placeholder="250, 180")
            ss.alert_webhook_url = st.text_input("Webhook (https, optional)", value=ss.alert_webhook_url,
                                                 type="password")
            st.caption("Toast + optional webhook; 5-minute cooldown per alert.")
            if ss.alerts_enabled:
                _alert_monitor()

        st.caption("Research tool · not financial advice · public feeds may be delayed.")
