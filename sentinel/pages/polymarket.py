"""Polymarket: most-traded events, search, liquidity view."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd
import streamlit as st

from sentinel.core.formatting import _esc, _safe_float, fmt_usd
from sentinel.data.polymarket import (
    _parse_poly_field, live_markets, market_tokens, poly_holders, poly_leaderboard, poly_price_history, poly_trades,
    polymarket_events, polymarket_markets, score_poly_mispricing,
)
from sentinel.ui.components import (
    cards, colored, divider, empty, note, poly_url, render_poly_card, section, table,
)
from sentinel.ui.palette import DOWN, FLAT, SERIES, TEXT_DIM, UP
from sentinel.ui.theme import dark_fig, go, plot


def _lead(evt):
    best_name, best_p = None, -1.0
    for mk in live_markets(evt):
        pp = _parse_poly_field(mk.get("outcomePrices"))
        p = _safe_float(pp[0], -1) if pp else -1
        if p > best_p:
            best_p, best_name = p, (mk.get("groupItemTitle") or mk.get("question") or "Yes")
    return (best_name or "—"), max(best_p, 0) * 100


def render():
    events = polymarket_events(100)
    if not events:
        note("Polymarket API unavailable right now.", "warn")
        return
    vol24 = sum(_safe_float(e.get("volume24hr")) for e in events)
    liq = sum(_safe_float(e.get("liquidity")) for e in events)
    cards([("Open events (top 100)", f"{len(events)}"), ("24h volume", fmt_usd(vol24)), ("Liquidity", fmt_usd(liq))], 160)

    divider()
    q = st.text_input("Search events", placeholder="Fed, recession, election, bitcoin…", key="poly_q").strip().lower()
    shown = [e for e in events if q in str(e.get("title", "")).lower()] if q else events
    top = shown[:12]
    if not top:
        empty("No events match.")
    else:
        section("Most traded events", "Leading outcome and its implied probability")
        rows = []
        for e in top:
            name, p = _lead(e)
            rows.append([
                f'<a href="{_esc(poly_url(e))}" target="_blank" rel="noopener noreferrer">{_esc(e.get("title", "")[:80])}</a>',
                _esc(str(name)[:40]), f"<b>{p:.0f}%</b>", fmt_usd(_safe_float(e.get("volume24hr"))),
                fmt_usd(_safe_float(e.get("volume"))), f'<span class="dim">{_esc((e.get("endDate") or "")[:10])}</span>',
            ])
        table(["Event", "Leading outcome", "Prob.", "24h vol", "Total vol", "Ends"], rows, align="wlrrrr")

        fig = dark_fig(max(280, 30 * len(top)), hovermode="y unified", barmode="overlay",
                       title=dict(text="Volume: total vs last 24h"), showlegend=True)
        labels = [e.get("title", "")[:48] for e in top]
        fig.add_trace(go.Bar(y=labels, x=[_safe_float(e.get("volume")) for e in top], orientation="h", name="Total",
                             marker_color=SERIES[4], marker_line_width=0))
        fig.add_trace(go.Bar(y=labels, x=[_safe_float(e.get("volume24hr")) for e in top], orientation="h", name="24h",
                             marker_color=SERIES[0], marker_line_width=0, width=0.4))
        fig.update_layout(xaxis=dict(type="log", tickprefix="$"), yaxis=dict(autorange="reversed", side="left"),
                          margin=dict(l=8, r=16, t=56, b=8))
        plot(fig, key="poly_vol")

    divider()
    _explorer(shown or events)

    divider()
    left, right = st.columns([3, 2], gap="large")
    with left:
        section("Event cards")
        for e in top[:6]:
            st.markdown(render_poly_card(e), unsafe_allow_html=True)
    with right:
        section("Liquidity view", "Thin markets: quoted odds are less reliable. "
                                  "‘Adjusted’ shrinks the price toward 50% by liquidity — a caution flag, not an edge.")
        mis = score_poly_mispricing(polymarket_markets(100), limit=12)
        rows = []
        for m in mis:
            url = f"https://polymarket.com/event/{quote(m['event_slug'] or m['slug'], safe='-_')}"
            rows.append([
                f'<a href="{_esc(url)}" target="_blank" rel="noopener noreferrer">{_esc(m["title"][:60])}</a>',
                f"{m['yes_pct']:.0f}%", f'<span class="dim">{m["adj_pct"]:.0f}%</span>',
                f'<span style="color:{UP if m["tier"] == "Deep" else FLAT if m["tier"] == "Medium" else TEXT_DIM}">{m["tier"]}</span>',
                f"{m['spread_c']:.1f}¢" if m["spread_c"] is not None else "—",
            ])
        table(["Market", "Yes", "Adjusted", "Depth", "Spread"], rows, align="wrrlr", empty_text="No open markets.")
        st.caption("Crowd odds only · not financial advice.")


_INTERVALS = {"1D": "1d", "1W": "1w", "1M": "1m", "All": "max"}


def _ago(ts):
    secs = max(0, int(datetime.now(timezone.utc).timestamp()) - int(ts))
    return f"{secs // 60}m ago" if secs < 3600 else f"{secs // 3600}h ago" if secs < 86400 else f"{secs // 86400}d ago"


def _profile(wallet, name):
    if not wallet:
        return _esc(name or "—")
    return (f'<a href="https://polymarket.com/profile/{_esc(wallet)}" target="_blank" rel="noopener noreferrer">'
            f'{_esc((name or wallet[:10])[:22])}</a>')


def _explorer(events):
    section("Market explorer", "Price history, largest holders and the live tape for any open event")
    c1, c2, c3 = st.columns([3, 3, 1.4])
    with c1:
        evts = [e for e in events[:100] if live_markets(e)]
        if not evts:
            empty("No open events.")
            return
        ev = st.selectbox("Event", evts, format_func=lambda e: str(e.get("title", ""))[:90], key="px_event")
    mkts = sorted(live_markets(ev), key=lambda m: -_safe_float(m.get("volumeNum", m.get("volume"))))
    with c2:
        mk = st.selectbox("Market", mkts, format_func=lambda m: str(m.get("groupItemTitle") or m.get("question"))[:80],
                          key="px_market", disabled=len(mkts) == 1)
    with c3:
        iv = st.segmented_control("Range", list(_INTERVALS), default="1W", key="px_iv") or "1W"

    # Chart: every outcome of a binary market, or the YES line of the top 6 markets in a multi-market event.
    series = []
    if len(mkts) > 1:
        for m in mkts[:6]:
            toks = market_tokens(m)
            if toks:
                series.append((str(m.get("groupItemTitle") or m.get("question"))[:32], toks[0][1]))
    else:
        series = [(lbl, tok) for lbl, tok in market_tokens(mk)]
    fig = dark_fig(340, hovermode="x unified", showlegend=True,
                   title=dict(text=f"Implied probability · {iv}" + (" · top markets (YES)" if len(mkts) > 1 else "")))
    added = False
    for i, (lbl, tok) in enumerate(series):
        h = poly_price_history(tok, _INTERVALS[iv])
        if not h:
            continue
        added = True
        df = pd.DataFrame(h, columns=["t", "p"])
        fig.add_trace(go.Scatter(x=pd.to_datetime(df["t"], unit="s"), y=df["p"] * 100, mode="lines", name=lbl,
                                 line=dict(color=SERIES[i % len(SERIES)] if len(series) > 2 else (UP if i == 0 else DOWN),
                                           width=2 if i == 0 else 1.5),
                                 hovertemplate="%{y:.1f}%<extra>" + _esc(lbl) + "</extra>"))
    if added:
        fig.update_layout(yaxis=dict(ticksuffix="%", range=[0, 100]), legend=dict(orientation="h", y=-0.15))
        plot(fig, key="px_hist")
    else:
        empty("No price history for this market yet.")

    cond = mk.get("conditionId")
    left, right = st.columns(2, gap="large")
    outs = [o for o, _ in market_tokens(mk)] or ["Yes", "No"]
    with left:
        section("Largest holders", f"Shares held · {_esc(str(mk.get('groupItemTitle') or mk.get('question'))[:60])}")
        hold = poly_holders(cond) if cond else {}
        cols = st.columns(2)
        for idx, col in enumerate(cols):
            with col:
                lst = hold.get(idx, [])
                rows = [[_profile(h["wallet"], h["name"]), f"{h['amount']:,.0f}"] for h in lst[:10]]
                table([outs[idx] if idx < len(outs) else f"Outcome {idx}", "Shares"], rows, align="lr",
                      empty_text="No holders.")
    with right:
        section("Recent trades", "Latest fills on this market")
        tr = poly_trades(cond, 20) if cond else []
        rows = [[f'<span class="dim">{_ago(t["ts"])}</span>',
                 f'<span style="color:{UP if t["side"] == "BUY" else DOWN}">{_esc(t["side"].title())}</span>',
                 _esc(str(t["outcome"])[:16]), f"{t['price'] * 100:.1f}¢", fmt_usd(t["price"] * t["size"]),
                 _profile(t["wallet"], t["name"])] for t in tr]
        table(["When", "Side", "Outcome", "Price", "Value", "Trader"], rows, align="llwrrl", max_height=420,
              empty_text="No recent trades.")

    divider()
    l1, l2, l3 = st.columns([3, 1.6, 1.4])
    with l1:
        section("Trader leaderboard", "Polymarket's public ranking")
    with l2:
        per = st.segmented_control("Period", ["DAY", "WEEK", "MONTH", "ALL"], default="WEEK", key="lb_per",
                                   format_func=str.title) or "WEEK"
    with l3:
        by = st.segmented_control("Rank by", ["PNL", "VOL"], default="PNL", key="lb_by",
                                  format_func=lambda x: "Profit" if x == "PNL" else "Volume") or "PNL"
    lb = poly_leaderboard(per, by, 25)
    rows = [[f"{r['rank']}", _profile(r["wallet"], r["name"]),
             colored(("+" if r["pnl"] >= 0 else "−") + fmt_usd(abs(r["pnl"])), UP if r["pnl"] >= 0 else DOWN),
             fmt_usd(r["volume"])] for r in lb]
    table(["#", "Trader", "Profit", "Volume"], rows, align="llrr", max_height=480, empty_text="Leaderboard unavailable.")
