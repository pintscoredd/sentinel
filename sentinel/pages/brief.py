"""Morning brief: tape, sentiment, watchlist, sectors, Polymarket, geo headlines."""
from __future__ import annotations


import streamlit as st

from sentinel.core.cache import prefetch
from sentinel.core.formatting import _esc, fmt_p, fmt_vol
from sentinel.data.market import calc_stock_fear_greed, get_vix_full, multi_quotes, sector_etfs, yahoo_quote
from sentinel.data.news import google_news, is_market_relevant
from sentinel.data.polymarket import polymarket_events
from sentinel.data.screener import breadth, market_screener
from sentinel.data.sessions import exchange_status
from sentinel.state import save_watchlist
from sentinel.ui.components import (
    cards, divider, empty, exchange_board, gdelt_date, poly_status, quote_cards, render_news_card, render_poly_card,
    section, signed, table, tkr,
)
from sentinel.ui.palette import DOWN, FLAT, TEXT, UP

STRIP = [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^RUT", "Russell 2000"), ("^VIX", "VIX"),
         ("^TNX", "US 10Y"), ("DX-Y.NYB", "Dollar index"), ("GC=F", "Gold"), ("CL=F", "WTI crude"),
         ("BTC-USD", "Bitcoin")]


@st.fragment(run_every="60s")
def _sessions():
    rows = exchange_status()
    n_open = sum(r["status"] == "OPEN" for r in rows)
    section("World markets", f"{n_open} of {len(rows)} exchanges open now · regular hours, holidays not shown")
    exchange_board(rows)


@st.fragment(run_every="60s")
def _tape():
    qs = multi_quotes(tuple(t for t, _ in STRIP))
    if qs:
        quote_cards(qs, dict(STRIP), min_width=128)
    else:
        empty("Quotes unavailable (Yahoo rate limit or network). Retrying every minute.")


def _sentiment():
    vix, vix_rank, posture = get_vix_full()
    fg, fg_label = calc_stock_fear_greed()
    vq = yahoo_quote("^VIX")
    items = []
    if vix:
        regime = "Low" if vix < 15 else "Normal" if vix < 20 else "Elevated" if vix < 30 else "Stress"
        items.append(("VIX", f"{vix:.2f}", f"{regime} · {vix_rank:.0f}th pct (1Y)" if vix_rank is not None else regime))
    if vq:
        items.append(("VIX day change", f"{vq['pct']:+.2f}%", "falling vol = risk-on" if vq["pct"] < 0 else "rising vol = risk-off",
                      FLAT, DOWN if vq["pct"] > 0 else UP))
    if fg is not None:
        c = UP if fg >= 55 else DOWN if fg < 45 else TEXT
        items.append(("Stock fear & greed", f"{fg}", fg_label, FLAT, c))
    if posture:
        items.append(("Vol posture", posture.title(), "from VIX 1Y rank", FLAT,
                      UP if posture == "RISK-ON" else DOWN if posture == "RISK-OFF" else TEXT))
    b = breadth(market_screener())
    if b:
        items.append(("Market breadth", f"{b['pct_up']:.0f}% up", f"{b['up']:,} advancers · {b['down']:,} decliners",
                      FLAT, UP if b["pct_up"] >= 55 else DOWN if b["pct_up"] <= 45 else TEXT))
    if items:
        cards(items, 150)
    else:
        empty("Sentiment inputs unavailable.")


def _watchlist():
    ss = st.session_state
    with st.form("wl_add_form", clear_on_submit=True, border=False):
        c1, c2 = st.columns([4, 1])
        new = c1.text_input("Add ticker", placeholder="Add ticker, e.g. TSLA", label_visibility="collapsed")
        if c2.form_submit_button("Add", width="stretch"):
            t = new.strip().upper()[:16]
            if t and t not in ss.watchlist:
                if yahoo_quote(t):
                    ss.watchlist.append(t)
                    save_watchlist(ss.watchlist)
                else:
                    st.toast(f"No quote found for {t}")
    qs = {q["ticker"]: q for q in multi_quotes(tuple(ss.watchlist))} if ss.watchlist else {}
    rows = []
    for t in ss.watchlist:
        q = qs.get(t)
        if not q:
            rows.append([tkr(t), "—", "—", "—", "—"])
            continue
        rows.append([tkr(t), fmt_p(q["price"], t), signed(q["pct"], "{:+.2f}", "%", True),
                     signed(q["change"], "{:+,.2f}"), fmt_vol(q.get("volume"))])
    table(["Ticker", "Last", "Chg %", "Chg", "Volume"], rows, empty_text="Watchlist is empty.")
    if ss.watchlist:
        c1, c2 = st.columns([4, 1])
        rm = c1.selectbox("Remove", ["—"] + ss.watchlist, label_visibility="collapsed", key="wl_rm")
        if c2.button("Remove", width="stretch", disabled=rm == "—"):
            ss.watchlist = [x for x in ss.watchlist if x != rm]
            save_watchlist(ss.watchlist)
            st.rerun()


def _sectors():
    df = sector_etfs()
    if df.empty:
        empty("Sector data unavailable.")
        return
    df = df.sort_values("Pct", ascending=False)
    mx = max(df["Pct"].abs().max(), 0.01)
    rows = []
    for r in df.itertuples():
        w = abs(r.Pct) / mx * 100
        bar = (f'<div class="s-bar" style="min-width:90px"><div style="width:{w:.0f}%;'
               f'background:{UP if r.Pct >= 0 else DOWN}"></div></div>')
        rows.append([_esc(r.Sector), tkr(r.ETF), signed(r.Pct, "{:+.2f}", "%", True), bar])
    table(["Sector", "ETF", "Day", ""], rows, align="lrrl")


def _polymarket():
    events = polymarket_events(40)
    if not events:
        empty("Polymarket unavailable.")
        return
    active = [e for e in events if poly_status(e)[0] == "ACTIVE"][:5]
    for e in active:
        st.markdown(render_poly_card(e), unsafe_allow_html=True)


def _geo():
    query = _geo_query()
    arts = google_news(query, 30)
    seen, shown = set(), 0
    for a in arts or []:
        t = a.get("title", "")
        k = t.strip().lower()
        if not t or k in seen or not is_market_relevant(t, a.get("domain", "")):
            continue
        seen.add(k)
        st.markdown(render_news_card(t, a.get("url"), a.get("domain", ""), gdelt_date(a.get("seendate"))),
                    unsafe_allow_html=True)
        shown += 1
        if shown >= 6:
            break
    if not shown:
        empty("News feed unavailable right now.")


def _geo_query():
    return st.session_state.geo_watch.strip() or "(war OR sanctions OR tariff OR blockade OR ceasefire)"


def render():
    wl = tuple(st.session_state.watchlist)
    prefetch(lambda: multi_quotes(tuple(t for t, _ in STRIP)), get_vix_full, calc_stock_fear_greed,
             lambda: yahoo_quote("^VIX"), sector_etfs, market_screener, lambda: polymarket_events(40),
             lambda: google_news(_geo_query(), 30), *([lambda: multi_quotes(wl)] if wl else []))
    _sessions()
    section("Market tape", "Day change vs prior close · refreshes every 60 s")
    _tape()
    divider()
    left, right = st.columns([3, 2], gap="large")
    with left:
        section("Sentiment")
        _sentiment()
        section("Watchlist")
        _watchlist()
        section("Sector pulse", "SPDR sector ETFs")
        _sectors()
    with right:
        section("Polymarket · most traded")
        _polymarket()
        section("Geo watch", "Google News · last 48 h")
        _geo()
