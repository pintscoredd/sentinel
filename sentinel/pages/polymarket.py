"""Polymarket: most-traded events, search, liquidity view."""
from __future__ import annotations

from urllib.parse import quote

import streamlit as st

from sentinel.core.formatting import _esc, _safe_float, fmt_usd
from sentinel.data.polymarket import _parse_poly_field, live_markets, polymarket_events, polymarket_markets, score_poly_mispricing
from sentinel.ui.components import (
    cards, divider, empty, note, poly_url, render_poly_card, section, table,
)
from sentinel.ui.palette import FLAT, SERIES, TEXT_DIM, UP
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
