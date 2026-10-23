"""SENTINEL — market & global-intelligence terminal.

Run:  streamlit run sentinel_app.py
"""
import importlib
import logging

import streamlit as st

st.set_page_config(page_title="Sentinel", page_icon="◼", layout="wide", initial_sidebar_state="collapsed")

from sentinel.pages import sidebar  # noqa: E402
from sentinel.state import init_session  # noqa: E402
from sentinel.ui.terminal import (  # noqa: E402
    SCREENS, install_hotkeys, render_command_bar, render_footer, render_header, render_nav,
)
from sentinel.ui.theme import inject_theme  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# yfinance logs expected misses (e.g. no fundamentals for ETFs) at ERROR level.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

inject_theme()
init_session()
sidebar.render()

render_header()
render_command_bar()
page = render_nav()
install_hotkeys()

try:
    importlib.import_module(f"sentinel.pages.{SCREENS[page][0]}").render()
except Exception:
    logging.getLogger("sentinel.app").exception("Page %s failed", page)
    st.error(f"The {page} page hit an error. Details were written to the server log.")
render_footer(page)
