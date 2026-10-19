"""Earnings calendar, insider buying across the watchlist, short interest."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import streamlit as st

from sentinel.core.formatting import _esc, fmt_usd, fmt_vol
from sentinel.data.fundamentals import (
    finnhub_insider, finnhub_officers, get_earnings_calendar, get_finra_short_volume, smart_money_conviction_buys,
)
from sentinel.state import key
from sentinel.ui.components import colored, divider, empty, insider_tx_label, note, section, table, tkr
from sentinel.ui.palette import DOWN, TEXT, TEXT_DIM, UP


def _calendar():
    section("Upcoming earnings", "Large caps + your watchlist · next report date and consensus EPS (Yahoo)")
    extra = tuple(t for t in st.session_state.watchlist if "-" not in t and "^" not in t and "=" not in t)
    df = get_earnings_calendar(date.today().isoformat(), extra)
    if df.empty:
        empty("Earnings calendar unavailable (Yahoo rate limit). Try again shortly.")
        return
    today = date.today()
    rows, classes = [], []
    for _, r in df.iterrows():
        eps = r["EPS Est"]
        days = (r["EarningsDate"] - today).days
        if days < -3:
            continue
        when = "Today" if days == 0 else "Tomorrow" if days == 1 else (f"in {days}d" if days > 0 else f"{-days}d ago")
        rows.append([f"{r['EarningsDate']:%a %b %d}", f'<span class="dim">{when}</span>', tkr(r["Ticker"]),
                     _esc(r["Company"]), f"{eps:.2f}" if eps is not None and eps == eps else "—"])
        classes.append("hl" if 0 <= days <= 1 else "")
    table(["Date", "", "Ticker", "Company", "EPS est."], rows, align="llllr", row_classes=classes,
          empty_text="No reports in the window.")


def _insiders(fk):
    tickers = [t for t in st.session_state.watchlist if "-" not in t and "^" not in t and "=" not in t][:8]
    if not tickers:
        empty("Add equities to your watchlist to scan insider activity.")
        return

    def _one(t):
        return t, finnhub_insider(t, fk), finnhub_officers(t, fk)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_one, tickers))

    section("Open-market insider purchases", "Form 4 code P across your watchlist (excludes awards, exercises, tax sales)")
    buys = []
    for t, ins, roles in results:
        for b in smart_money_conviction_buys(ins or [], roles or {}):
            buys.append({**b, "ticker": t})
    buys.sort(key=lambda b: (b["score"], b["dollar_value"]), reverse=True)
    rows = [[tkr(b["ticker"]), _esc(b["name"][:28]), _esc(b["role"][:28]), b["date"], f"{b['shares']:,}",
             fmt_usd(b["dollar_value"]), f"<b>{b['score']}</b>"] for b in buys[:12]]
    table(["Ticker", "Insider", "Role", "Date", "Shares", "Value", "Score"], rows,
          empty_text="No open-market purchases in recent filings.")

    section("Latest insider transactions")
    rows = []
    for t, ins, _ in results:
        for tx in (ins or [])[:3]:
            lbl, cls = insider_tx_label(tx)
            chg = int(tx.get("change") or 0)
            px = float(tx.get("transactionPrice") or 0)
            rows.append([tkr(t), _esc(str(tx.get("name", ""))[:28]),
                         colored(lbl.title(), UP if cls == "buy" else DOWN, True),
                         f"{chg:+,}", fmt_usd(abs(chg) * px) if px else "—",
                         f'<span class="dim">{_esc(str(tx.get("transactionDate", ""))[:10])}</span>'])
    table(["Ticker", "Insider", "Type", "Shares", "Value", "Date"], rows, empty_text="No recent filings.")


def _short_interest():
    section("Short interest", "Watchlist · exchange-reported, updated twice a month")
    tickers = [t for t in st.session_state.watchlist if "-" not in t and "^" not in t and "=" not in t][:10]
    with ThreadPoolExecutor(max_workers=4) as pool:
        data = list(pool.map(lambda t: (t, get_finra_short_volume(t)), tickers))
    rows = []
    for t, si in data:
        if not si:
            rows.append([tkr(t), "—", "—", "—"])
            continue
        pct = si["short_pct_float"]
        c = DOWN if (pct or 0) >= 20 else TEXT if (pct or 0) >= 10 else TEXT_DIM
        rows.append([tkr(t), colored(f"{pct:.2f}%", c, True) if pct is not None else "—",
                     fmt_vol(si["short_shares"]) if si["short_shares"] is not None else "—",
                     f"{si['days_to_cover']:.1f}" if si["days_to_cover"] is not None else "—"])
    table(["Ticker", "Short % float", "Shares short", "Days to cover"], rows, empty_text="Watchlist is empty.")


def render():
    left, right = st.columns([1, 1], gap="large")
    with left:
        _calendar()
    with right:
        _short_interest()
    divider()
    fk = key("finnhub_key")
    if fk:
        _insiders(fk)
    else:
        note("Insider scans use Finnhub. Add FINNHUB_API_KEY in secrets or the sidebar.")
    st.caption(f"Updated {datetime.now():%H:%M}")
