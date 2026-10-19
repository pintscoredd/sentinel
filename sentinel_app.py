"""SENTINEL — market & global-intelligence terminal.

Run:  streamlit run sentinel_app.py
"""
import importlib
import logging

import streamlit as st

st.set_page_config(page_title="Sentinel", page_icon="◼", layout="wide", initial_sidebar_state="collapsed")

from sentinel.data.market import is_market_open  # noqa: E402
from sentinel.pages import sidebar  # noqa: E402
from sentinel.state import init_session, now_pst  # noqa: E402
from sentinel.ui.theme import inject_theme  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# yfinance logs expected misses (e.g. no fundamentals for ETFs) at ERROR level.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

# Label → module in sentinel.pages (imported lazily: only the active page runs).
PAGES = {
    "Brief": "brief",
    "Markets": "markets",
    "Options": "options",
    "Macro": "macro",
    "Crypto": "crypto",
    "Perps": "perps",
    "Polymarket": "polymarket",
    "Geo": "geo",
    "Earnings": "earnings",
    "AI": "ai",
}

inject_theme()
init_session()
sidebar.render()

status, color, detail = is_market_open()
st.markdown(
    f'<div class="s-topbar"><div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">'
    f'<span class="s-brand">SENTINEL</span>'
    f'<span class="s-pill"><span class="s-dot" style="background:{color}"></span>US EQUITIES · {status}</span>'
    f'<span class="dim" style="font-size:12px">{detail}</span></div>'
    f'<span class="dim num" style="font-size:12px">{now_pst()}</span></div>',
    unsafe_allow_html=True,
)
st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

page = st.segmented_control(
    "Navigation", options=list(PAGES), default="Brief", key="main_nav",
    label_visibility="collapsed", width="stretch",
) or "Brief"

try:
    importlib.import_module(f"sentinel.pages.{PAGES[page]}").render()
except Exception:
    logging.getLogger("sentinel.app").exception("Page %s failed", page)
    st.error(f"The {page} page hit an error. Details were written to the server log.")
