"""Terminal chrome: status bar with live tape and world clocks, command line, hotkeys, footer.

Command line (press "/" to focus):
  AAPL            ticker deep dive          GEX SPX       dealer exposure
  CHAIN TSLA      options chain & builder   0DTE          SPX 0DTE
  HEAT / MOVERS   market heatmap / overview RRG / VOL     rotation / volatility
  13F BERKSHIRE   fund holdings             MACRO RATES   macro sections
  PERPS ETH       Hyperliquid filtered      POLY FED      Polymarket search
  GEO / EARN      globe / earnings          AI <question> ask the assistant
Number keys 1–0 switch screens when no input has focus.
"""
from __future__ import annotations

import html

import streamlit as st
import streamlit.components.v1 as components

from sentinel.data.market import is_market_open, multi_quotes

# Screen label → (module, hotkey, short code shown in the nav)
SCREENS = {
    "Brief": ("brief", "1", "BRIEF"),
    "Markets": ("markets", "2", "MKTS"),
    "Options": ("options", "3", "OPTS"),
    "Macro": ("macro", "4", "MACRO"),
    "Crypto": ("crypto", "5", "CRYPTO"),
    "Perps": ("perps", "6", "PERPS"),
    "Polymarket": ("polymarket", "7", "POLY"),
    "Geo": ("geo", "8", "GEO"),
    "Earnings": ("earnings", "9", "EARN"),
    "AI": ("ai", "0", "AI"),
}

TAPE = [("^GSPC", "SPX"), ("^NDX", "NDX"), ("^RUT", "RUT"), ("^VIX", "VIX"), ("^TNX", "UST10Y"),
        ("DX-Y.NYB", "DXY"), ("EURUSD=X", "EURUSD"), ("JPY=X", "USDJPY"), ("GC=F", "GOLD"), ("CL=F", "WTI"),
        ("HG=F", "COPPER"), ("BTC-USD", "BTC"), ("ETH-USD", "ETH")]

HELP = [
    ("AAPL", "Ticker deep dive (any symbol)"), ("GEX SPX", "Dealer gamma/delta/vanna exposure"),
    ("CHAIN TSLA", "Options chain & strategy builder"), ("0DTE", "SPX 0DTE desk"),
    ("HEAT", "Market heatmap & breadth"), ("MOVERS", "Indices, futures, movers"),
    ("RRG", "Sector rotation"), ("VOL", "Volatility & skew"), ("13F BERKSHIRE", "Fund holdings (13F)"),
    ("MACRO · RATES · LIQ", "Macro sections"), ("CRYPTO", "Crypto"), ("PERPS ETH", "Hyperliquid, filtered"),
    ("POLY FED", "Polymarket search"), ("GEO", "Globe"), ("EARN", "Earnings calendar"),
    ("AI what moved oil?", "Ask the assistant"), ("HELP", "This list"),
]

_ALIAS = {"HEAT": ("Markets", "mk_sub", "Heatmap"), "HMAP": ("Markets", "mk_sub", "Heatmap"),
          "BREADTH": ("Markets", "mk_sub", "Heatmap"), "MOVERS": ("Markets", "mk_sub", "Overview"),
          "MKTS": ("Markets", "mk_sub", "Overview"), "MARKETS": ("Markets", "mk_sub", "Overview"),
          "RRG": ("Markets", "mk_sub", "Rotation"), "ROTATION": ("Markets", "mk_sub", "Rotation"),
          "VOL": ("Markets", "mk_sub", "Volatility"), "13F": ("Markets", "mk_sub", "Funds (13F)"),
          "FUNDS": ("Markets", "mk_sub", "Funds (13F)"), "0DTE": ("Options", "opt_sub", "SPX 0DTE"),
          "OPTS": ("Options", "opt_sub", "Chain & strategy"), "MACRO": ("Macro", "mac_sub", "Overview"),
          "RATES": ("Macro", "mac_sub", "Rates"), "LIQ": ("Macro", "mac_sub", "Liquidity & flows"),
          "BRIEF": ("Brief", None, None), "CRYPTO": ("Crypto", None, None), "GEO": ("Geo", None, None),
          "EARN": ("Earnings", None, None), "EARNINGS": ("Earnings", None, None), "AI": ("AI", None, None),
          "PERPS": ("Perps", None, None), "HL": ("Perps", None, None), "POLY": ("Polymarket", None, None)}


def _go(screen, sub_key=None, sub_val=None):
    ss = st.session_state
    ss["main_nav"] = screen
    if sub_key:
        ss[sub_key] = sub_val


def run_command() -> None:
    """Form callback: parse the command line and switch screens before the next run renders them."""
    ss = st.session_state
    raw = str(ss.get("cmd_input", "")).strip()
    ss["cmd_input"] = ""
    ss["cmd_msg"] = ""
    if not raw:
        return
    parts = raw.split()
    head, rest = parts[0].upper(), " ".join(parts[1:])
    if head in ("HELP", "?", "H"):
        ss["cmd_help"] = not ss.get("cmd_help", False)
        return
    ss["cmd_help"] = False
    if head == "GEX" or head == "EXPOSURE":
        _go("Options", "opt_sub", "Exposure (GEX)")
        if rest:
            ss["exp_tk_in"] = rest.upper()[:8]
            ss["exp_tk"] = rest.upper()[:8]
    elif head in ("CHAIN", "OPT", "OPTIONS"):
        _go("Options", "opt_sub", "Chain & strategy")
        if rest:
            ss["master_ticker"] = rest.upper()[:16]
    elif head in ("13F", "FUNDS") and rest:
        from sentinel.data.funds import FUNDS
        match = next((n for n in FUNDS if rest.lower() in n.lower()), None)
        _go("Markets", "mk_sub", "Funds (13F)")
        if match:
            ss["fund_sel"] = match
        else:
            ss["cmd_msg"] = f"No tracked fund matches “{rest}”."
    elif head in ("PERPS", "HL") and rest:
        _go("Perps")
        ss["hl_q"] = rest.upper()
    elif head == "POLY" and rest:
        _go("Polymarket")
        ss["poly_q"] = rest
    elif head == "AI" and rest:
        _go("AI")
        ss["ai_pending"] = rest
    elif head in _ALIAS:
        _go(*_ALIAS[head])
    elif len(parts) == 1 and 1 <= len(head) <= 12 and all(c.isalnum() or c in ".-=^" for c in head):
        _go("Markets", "mk_sub", "Ticker")
        ss["master_ticker"] = head
    else:
        ss["cmd_msg"] = f"Unknown command “{raw[:40]}”. Type HELP."


@st.cache_data(ttl=60, show_spinner=False)
def _tape_quotes():
    return {q["ticker"]: q for q in (multi_quotes(tuple(t for t, _ in TAPE)) or [])}


def _tape_html() -> str:
    qs = _tape_quotes()
    items = []
    for sym, label in TAPE:
        q = qs.get(sym)
        if not q:
            continue
        cls = "up" if q["pct"] > 0 else "dn" if q["pct"] < 0 else "flat"
        arrow = "▲" if q["pct"] > 0 else "▼" if q["pct"] < 0 else "■"
        price = f"{q['price']:,.4f}" if abs(q["price"]) < 10 and "=" in sym else f"{q['price']:,.2f}"
        items.append(f'<span class="ti"><b>{html.escape(label)}</b> {price} '
                     f'<span class="{cls}">{arrow}{abs(q["pct"]):.2f}%</span></span>')
    if not items:
        return '<span class="ti dim">QUOTES UNAVAILABLE</span>'
    row = "".join(items)
    return f'<div class="tape-track">{row}{row}</div>'  # duplicated for a seamless loop


def render_header() -> None:
    status, color, detail = is_market_open()
    st.markdown(
        f'<div class="t-bar">'
        f'<div class="t-left"><span class="t-brand">SENTINEL<span class="t-cursor">▌</span></span>'
        f'<span class="t-stat"><span class="s-dot" style="background:{color}"></span>NYSE {html.escape(status)}</span></div>'
        f'<div class="t-tape">{_tape_html()}</div>'
        f'<div class="t-clocks">'
        f'<span>NY <b data-tz="America/New_York">--:--:--</b></span>'
        f'<span>LDN <b data-tz="Europe/London">--:--</b></span>'
        f'<span>TKY <b data-tz="Asia/Tokyo">--:--</b></span>'
        f'<span>UTC <b data-tz="UTC">--:--</b></span></div></div>',
        unsafe_allow_html=True)
    _ = detail


def render_command_bar() -> None:
    with st.container(key="cmdbar"):
        with st.form("cmd_form", clear_on_submit=False, border=False):
            c1, c2 = st.columns([12, 1])
            c1.text_input("Command", key="cmd_input", label_visibility="collapsed",
                          placeholder="›  AAPL · GEX SPX · HEAT · 13F BERKSHIRE · PERPS ETH · AI why is oil up?   (press / to focus · HELP)")
            c2.form_submit_button("GO", on_click=run_command, width="stretch")
    msg = st.session_state.get("cmd_msg")
    if msg:
        st.markdown(f'<div class="t-msg">{html.escape(msg)}</div>', unsafe_allow_html=True)
    if st.session_state.get("cmd_help"):
        rows = "".join(f'<div><b>{html.escape(c)}</b><span>{html.escape(d)}</span></div>' for c, d in HELP)
        st.markdown(f'<div class="t-help">{rows}<div class="hint">Keys: 1–0 switch screens · / command line · '
                    f'Esc leave a field</div></div>', unsafe_allow_html=True)


def render_nav() -> str:
    if st.session_state.get("main_nav") not in SCREENS:
        st.session_state["main_nav"] = st.session_state.get("_last_page") or "Brief"
    with st.container(key="main_nav_wrap"):
        page = st.segmented_control(
            "Navigation", options=list(SCREENS), key="main_nav", label_visibility="collapsed",
            width="stretch", format_func=lambda p: f"{SCREENS[p][1]} {SCREENS[p][2]}",
        )
    # Clicking the active tab deselects it (None): stay on the last screen instead of jumping to Brief.
    page = page or st.session_state.get("_last_page") or "Brief"
    st.session_state["_last_page"] = page
    return page


def render_footer(page: str) -> None:
    st.markdown(
        f'<div class="t-foot"><span><b>{html.escape(SCREENS[page][2])}</b> &lt;GO&gt;</span>'
        f'<span>1–0 SCREENS · / COMMAND · HELP</span>'
        f'<span class="t-foot-r">DATA DELAYED · NOT INVESTMENT ADVICE</span></div>',
        unsafe_allow_html=True)


_KEYS_JS = """
<script>
(function () {
  const P = window.parent, D = P.document;
  if (P.__sentinelTerminal) return;
  P.__sentinelTerminal = true;
  const order = "1234567890";
  D.addEventListener("keydown", function (e) {
    const t = e.target, tag = (t && t.tagName || "").toLowerCase();
    const typing = tag === "input" || tag === "textarea" || (t && t.isContentEditable);
    if (e.key === "Escape" && typing) { t.blur(); return; }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "/") {
      const inp = D.querySelector(".st-key-cmdbar input");
      if (inp) { e.preventDefault(); inp.focus(); inp.select(); }
      return;
    }
    const i = order.indexOf(e.key);
    if (i >= 0) {
      const btns = D.querySelectorAll(".st-key-main_nav_wrap button");
      if (btns[i]) { e.preventDefault(); btns[i].click(); P.scrollTo({top: 0}); }
    }
  }, true);
  function tick() {
    const now = new Date();
    D.querySelectorAll("[data-tz]").forEach(function (el) {
      const withSec = el.dataset.tz === "America/New_York";
      el.textContent = now.toLocaleTimeString("en-GB", {timeZone: el.dataset.tz, hour: "2-digit", minute: "2-digit",
        second: withSec ? "2-digit" : undefined, hour12: false});
    });
  }
  tick(); setInterval(tick, 1000);
})();
</script>
"""


def install_hotkeys() -> None:
    """Zero-height component that installs keyboard shortcuts and live clocks in the parent page (once)."""
    with st.container(key="hotkeys"):
        components.html(_KEYS_JS, height=0)
