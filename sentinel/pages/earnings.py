"""Earnings calendar, insider buying across the watchlist, short interest."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import streamlit as st
import streamlit.components.v1 as components

from sentinel.core.formatting import _esc, fmt_usd, fmt_vol
from sentinel.data.fundamentals import (
    earnings_week, finnhub_insider, finnhub_officers, get_earnings_calendar, get_earnings_matrix,
    get_finra_short_volume, smart_money_conviction_buys,
)
from sentinel.data.options import earnings_expected_move
from sentinel.ui.earnings_grid import earnings_board_html
from sentinel.state import key
from sentinel.ui.components import cards, colored, divider, empty, insider_tx_label, note, section, signed, table, tkr
from sentinel.ui.palette import DOWN, TEXT, TEXT_DIM, UP, signed_color


def _week_start(offset: int) -> date:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    if today.weekday() >= 5:  # weekend: "this week" means the coming one
        monday += timedelta(days=7)
    return monday + timedelta(weeks=offset)


def _calendar():
    c1, c2 = st.columns([3, 1])
    labels = {-1: "Last week", 0: "This week", 1: "Next week", 2: "In 2 weeks"}
    with c1:
        off = st.segmented_control("Week", list(labels), format_func=labels.get, default=0, key="earn_week",
                                   label_visibility="collapsed")
    with c2:
        per = st.select_slider("Per slot", [4, 6, 8, 12], value=6, key="earn_per", label_visibility="collapsed",
                               format_func=lambda n: f"Top {n} per slot")
    monday = _week_start(off if off is not None else 0)
    rows = earnings_week(monday)
    if not rows:
        note("The Nasdaq earnings calendar did not respond. Showing the large-cap fallback list.", "warn")
        df = get_earnings_calendar(date.today().isoformat(), tuple(st.session_state.watchlist))
        rows = [{"date": r["EarningsDate"].isoformat(), "symbol": r["Ticker"], "name": r["Company"], "slot": "tbd",
                 "market_cap": None, "eps_est": r["EPS Est"], "n_est": None, "last_eps": None, "last_date": "",
                 "fiscal_q": ""} for _, r in df.iterrows()]
    html, height = earnings_board_html(rows, monday, st.session_state.watchlist, per)
    components.html(html, height=height, scrolling=True)
    st.caption("Source: Nasdaq earnings calendar · logos: Financial Modeling Prep · times are as announced by companies.")
    return rows


def _deep_dive(rows):
    section("Deep dive", "Options-implied move and earnings track record")
    if not rows:
        empty("No reports this week.")
        return
    ranked = sorted(rows, key=lambda r: -(r.get("market_cap") or 0))[:150]
    slot_lbl = {"bmo": "before open", "amc": "after close", "tbd": "time TBD"}
    opts = {r["symbol"]: f"{r['symbol']} · {r['name'][:32]} · {datetime.strptime(r['date'], '%Y-%m-%d'):%a %b %d} "
                         f"{slot_lbl.get(r['slot'], '')}" for r in ranked}
    sym = st.selectbox("Company", list(opts), format_func=opts.get, key="earn_pick", label_visibility="collapsed")
    r = next(x for x in ranked if x["symbol"] == sym)
    em = earnings_expected_move(sym, r["date"], r["slot"])
    growth = None
    if r.get("eps_est") is not None and r.get("last_eps"):
        growth = (r["eps_est"] / abs(r["last_eps"]) - 1) * 100 * (1 if r["last_eps"] > 0 else -1)
    cards([
        ("Expected move", f"±{em['move_pct']:.1f}%" if em else "—",
         f"±${em['straddle']:,.2f} straddle · exp {em['expiry']}" if em else "no listed options"),
        ("Consensus EPS", f"${r['eps_est']:.2f}" if r.get("eps_est") is not None else "—",
         f"{r['n_est']} analysts" if r.get("n_est") else ""),
        ("Year-ago EPS", f"${r['last_eps']:.2f}" if r.get("last_eps") is not None else "—",
         f"implied growth {growth:+.1f}%" if growth is not None else "", signed_color(growth or 0)),
        ("Market cap", fmt_usd(r.get("market_cap"))),
    ], 160)
    em_data = get_earnings_matrix(sym)
    if em_data:
        hist = []
        for yr in sorted(em_data["quarterly"], reverse=True):
            for ql in reversed(em_data["q_labels"]):
                act = em_data["quarterly"][yr].get(ql)
                if act is None:
                    continue
                est = em_data["estimates"].get(yr, {}).get(ql)
                surp = em_data["surprise_pct"].get(yr, {}).get(ql)
                hist.append([f"FY{yr} {ql}", f"{act:.2f}", f"{est:.2f}" if est is not None else "—",
                             signed(surp, "{:+.1f}", "%", True) if surp is not None else "—",
                             colored("Beat", UP, True) if est is not None and act >= est else
                             colored("Miss", DOWN, True) if est is not None else "—"])
        table(["Quarter", "Actual EPS", "Estimate", "Surprise", ""], hist[:8], empty_text="No EPS history.")
        st.caption(f"Beat rate {em_data.get('beat_rate', 0):.0f}% across reported quarters (Yahoo Finance).")


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
    rows = _calendar()
    divider()
    _deep_dive(rows)
    divider()
    _short_interest()
    divider()
    fk = key("finnhub_key")
    if fk:
        _insiders(fk)
    else:
        note("Insider scans use Finnhub. Add FINNHUB_API_KEY in secrets or the sidebar.")
    st.caption(f"Updated {datetime.now():%H:%M}")
