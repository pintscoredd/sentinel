"""Markets: overview, single-ticker deep dive, sector rotation, volatility.

Sub-sections are lazy (segmented control) so only the visible one fetches data.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import streamlit as st

from sentinel.core.cache import prefetch
from sentinel.core.formatting import _esc, fmt_p, fmt_vol
from sentinel.data.cross_asset import get_sector_rrg, stat_arb_screener
from sentinel.data.market import get_futures, get_global_indices, get_vix_full, sector_etfs, top_movers, yahoo_quote
from sentinel.data.news import finnhub_news, is_market_relevant
from sentinel.data.screener import breadth, large_caps, market_screener, movers, sector_table
from sentinel.data.options import get_gamma_squeeze_scanner, get_iv_skew, get_iv_term_structure, get_rv_iv_spread
from sentinel.pages.ticker import render_ticker
from sentinel.state import key
from sentinel.ui.components import (
    cards, divider, empty, note, render_news_card, render_stat_arb_cards, section, signed, table, tkr,
)
from sentinel.ui.palette import DOWN, SERIES, TEXT, TEXT_DIM, UP, signed_color
from sentinel.ui.charts import market_heatmap
from sentinel.ui.theme import dark_fig, go, plot

SUBPAGES = ["Overview", "Heatmap", "Ticker", "Rotation", "Volatility"]


# ── Overview ────────────────────────────────────────────────────────────────
def _global_indices():
    section("Global equity indices", "Last close · day change · annualised realised volatility")
    df = get_global_indices()
    if df.empty:
        empty("Index data unavailable.")
        return
    rows, classes = [], []
    for region in ("Americas", "EMEA", "APAC"):
        sub = df[df["Region"] == region]
        if sub.empty:
            continue
        rows.append([region]); classes.append("sec")
        for _, r in sub.iterrows():
            v10, v30 = r["10D Vol"], r["30D Vol"]
            rows.append([
                f'<span class="dim" style="font-size:11px;margin-right:8px">{_esc(r["Flag"])}</span>{_esc(r["Index"])}',
                f'{r["Value"]:,.2f}', signed(r["Change"], "{:+,.2f}"), signed(r["% Chg"], "{:+.2f}", "%", True),
                f"{v10:.1f}%" if v10 is not None and v10 == v10 else "—",
                f"{v30:.1f}%" if v30 is not None and v30 == v30 else "—",
                f'<span class="dim">{_esc(r["AsOf"])}</span>',
            ])
            classes.append("")
    table(["Index", "Last", "Change", "Change %", "10D vol", "30D vol", "As of"], rows, row_classes=classes)


@st.fragment(run_every="60s")
def _futures():
    section("Futures", "Front-month continuous contracts · refreshes every 60 s")
    rows = [[tkr(f["ticker"]), _esc(f["name"]), fmt_p(f["price"], f["ticker"]),
             signed(f["change"], "{:+,.2f}"), signed(f["pct"], "{:+.2f}", "%", True)] for f in get_futures()]
    table(["Contract", "Name", "Last", "Change", "Change %"], rows, align="llrrr",
          empty_text="Futures data unavailable.")


def _sectors():
    section("Sector performance", "SPDR sector ETFs · day change")
    df = sector_etfs()
    if df.empty:
        empty("Sector data unavailable.")
        return
    df = df.sort_values("Pct")
    fig = dark_fig(max(300, 28 * len(df)), hovermode="closest")
    fig.add_trace(go.Bar(x=df["Pct"], y=[f"{s} · {e}" for s, e in zip(df["Sector"], df["ETF"])], orientation="h",
                         marker_color=[UP if v >= 0 else DOWN for v in df["Pct"]], marker_line_width=0,
                         text=[f"{v:+.2f}%" for v in df["Pct"]], textposition="outside",
                         textfont=dict(size=10, color=TEXT_DIM), hovertemplate="%{y}: %{x:+.2f}%<extra></extra>"))
    fig.update_layout(xaxis=dict(ticksuffix="%"), yaxis=dict(side="left"), margin=dict(l=8, r=40, t=16, b=8))
    plot(fig, key="sector_bar")


def _movers():
    df = market_screener()
    if not df.empty:
        section("Top movers", "US stocks above $10B market cap · day change · Nasdaq screener")
        gainers, losers = movers(df, 10)
        c1, c2 = st.columns(2)
        for col, data, title in ((c1, gainers, "Gainers"), (c2, losers, "Losers")):
            with col:
                rows = [[tkr(r.symbol), f'<span class="dim">{_esc(r.name[:28])}</span>', fmt_p(r.price),
                         signed(r.pct, "{:+.2f}", "%", True), fmt_vol(r.volume)] for r in data.itertuples()]
                table([title, "Company", "Last", "Change %", "Volume"], rows, align="llrrr",
                      empty_text=f"No {title.lower()} today.")
        return
    section("Top movers", "~120 large caps · day change vs prior close")
    gainers, losers = top_movers()
    c1, c2 = st.columns(2)
    for col, data, title in ((c1, gainers, "Gainers"), (c2, losers, "Losers")):
        with col:
            rows = [[tkr(q["ticker"]), fmt_p(q["price"]), signed(q["pct"], "{:+.2f}", "%", True),
                     signed(q["change"], "{:+,.2f}"), fmt_vol(q["volume"])] for q in data]
            table([title, "Last", "Change %", "Change", "Volume"], rows, empty_text=f"No {title.lower()} today.")


def _news():
    fk = key("finnhub_key")
    if not fk:
        return
    divider()
    section("Market news", "Finnhub")
    shown = 0
    for art in finnhub_news(fk):
        title, src = art.get("headline", ""), art.get("source", "")
        if not is_market_relevant(title, src):
            continue
        ts = art.get("datetime", 0)
        d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""
        st.markdown(render_news_card(title, art.get("url"), src, d), unsafe_allow_html=True)
        shown += 1
        if shown >= 8:
            break


def _overview():
    prefetch(get_global_indices, get_futures, sector_etfs, market_screener)
    _global_indices()
    divider()
    left, right = st.columns([1, 1], gap="large")
    with left:
        _futures()
    with right:
        _sectors()
    divider()
    _movers()
    _news()


# ── Heatmap ─────────────────────────────────────────────────────────────────
def _heatmap():
    df = market_screener()
    if df.empty:
        empty("Market snapshot unavailable (Nasdaq screener did not respond). Try again in a minute.")
        return
    b = breadth(df)
    ad = f"{b['ad_ratio']:.2f}" if b.get("ad_ratio") else "—"
    cards([
        ("Advancers / decliners", f"{b['up']:,} / {b['down']:,}", f"A/D ratio {ad} · {b['n']:,} stocks > $300M",
         TEXT_DIM, signed_color(b["up"] - b["down"])),
        ("Share of stocks up", f"{b['pct_up']:.0f}%", "broad participation" if b["pct_up"] >= 60
         else "narrow / weak" if b["pct_up"] <= 40 else "mixed", TEXT_DIM, signed_color(b["pct_up"] - 50)),
        ("Cap-weighted move", f"{b['cap_weighted']:+.2f}%", "what the index feels", TEXT_DIM, signed_color(b["cap_weighted"])),
        ("Equal-weighted move", f"{b['equal_weighted']:+.2f}%", "what the average stock did", TEXT_DIM,
         signed_color(b["equal_weighted"])),
        ("Moves beyond ±4%", f"{b['big_up']} up · {b['big_down']} down", "stocks > $300M", TEXT_DIM, TEXT),
    ], 170)
    c1, c2 = st.columns([3, 1])
    with c2:
        n = st.select_slider("Companies shown", [50, 100, 200, 300, 500], value=200, key="hm_n")
    with c1:
        section("US market heatmap", "Area = market cap · colour = day change (capped at ±3%) · click a sector to zoom")
    fig = market_heatmap(large_caps(df, n))
    if fig:
        plot(fig, key="heatmap")
    st.caption("Source: Nasdaq stock screener (delayed). Sector labels follow Nasdaq's classification.")
    divider()
    left, right = st.columns([3, 2], gap="large")
    with left:
        section("Sector breadth", "Cap-weighted change and share of members up · stocks > $300M")
        st_ = sector_table(df)
        rows = []
        for r in st_.itertuples():
            w = max(0.0, min(100.0, r.pct_up))
            bar = (f'<div class="s-bar" style="min-width:90px"><div style="width:{w:.0f}%;'
                   f'background:{UP if w >= 50 else DOWN}"></div></div>')
            rows.append([_esc(r.sector), signed(r.pct, "{:+.2f}", "%", True), f"{r.pct_up:.0f}%", bar, f"{r.n:,}"])
        table(["Sector", "Cap-wtd", "% up", "", "Stocks"], rows, align="lrrlr")
    with right:
        section("Most active", "By share volume today")
        act = df.nlargest(12, "volume")
        rows = [[tkr(r.symbol), fmt_p(r.price), signed(r.pct, "{:+.2f}", "%", True), fmt_vol(r.volume)]
                for r in act.itertuples()]
        table(["Ticker", "Last", "Change %", "Volume"], rows)


# ── Rotation ────────────────────────────────────────────────────────────────
_QUAD = {  # quadrant → (head colour, background tint, plain-English meaning)
    "LEADING": (UP, "rgba(63,207,142,0.07)", "outperforming and still accelerating"),
    "WEAKENING": ("#D4D4D4", "rgba(255,255,255,0.035)", "outperforming but losing momentum"),
    "LAGGING": (DOWN, "rgba(242,85,90,0.07)", "underperforming and still decelerating"),
    "IMPROVING": ("#8A8A8A", "rgba(255,255,255,0.02)", "underperforming but momentum turning up"),
}
_ARROWS = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]


def _arrow(deg):
    return _ARROWS[int(((deg % 360) + 22.5) // 45) % 8]


def _rotation():
    section("Sector rotation (RRG)", "Each sector vs the S&P 500. Right = stronger relative trend, up = that trend "
                                     "is accelerating. Sectors normally rotate clockwise: Improving → Leading → "
                                     "Weakening → Lagging.")
    rrg = get_sector_rrg()
    if not rrg:
        empty("RRG data unavailable.")
    else:
        c1, c2 = st.columns([1, 3])
        tail = c1.select_slider("Tail", options=[1, 2, 4, 6, 8], value=4, key="rrg_tail",
                                format_func=lambda n: f"{n}-week tail" if n > 1 else "No tail")
        all_etfs = [r["etf"] for r in rrg]
        pick = c2.multiselect("Sectors", all_etfs, default=all_etfs, key="rrg_pick",
                              format_func=lambda e: f"{e} · {next(r['sector'] for r in rrg if r['etf'] == e)}",
                              label_visibility="collapsed")
        shown = [r for r in rrg if r["etf"] in pick] or rrg
        pts_x = [x for r in shown for x in r["trail_ratio"][-tail:]]
        pts_y = [y for r in shown for y in r["trail_momentum"][-tail:]]
        span = max(max(abs(v - 100) for v in pts_x + pts_y) * 1.18, 2.0)
        lo, hi = 100 - span, 100 + span

        fig = dark_fig(620, hovermode="closest", margin=dict(l=8, r=8, t=8, b=8))
        for (x0, x1, y0, y1, q, ax, ay) in ((100, hi, 100, hi, "LEADING", 1, 1), (100, hi, lo, 100, "WEAKENING", 1, -1),
                                            (lo, 100, lo, 100, "LAGGING", -1, -1), (lo, 100, 100, hi, "IMPROVING", -1, 1)):
            fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, fillcolor=_QUAD[q][1], line_width=0, layer="below")
            fig.add_annotation(x=100 + ax * span * 0.97, y=100 + ay * span * 0.95, text=q.title(), showarrow=False,
                               xanchor="right" if ax > 0 else "left", yanchor="top" if ay > 0 else "bottom",
                               font=dict(size=15, color=_QUAD[q][0]), opacity=0.55)
        fig.add_hline(y=100, line=dict(color="#444", width=1))
        fig.add_vline(x=100, line=dict(color="#444", width=1))
        for r in shown:
            color = _QUAD[r["quadrant"]][0]
            xs, ys = r["trail_ratio"][-tail:], r["trail_momentum"][-tail:]
            if len(xs) > 1:
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", line=dict(color=color, width=1.6, shape="spline"),
                                         marker=dict(size=[4] * (len(xs) - 1) + [0], color=color), opacity=0.55,
                                         hoverinfo="skip", showlegend=False))
                fig.add_annotation(x=xs[-1], y=ys[-1], ax=xs[-2], ay=ys[-2], xref="x", yref="y", axref="x", ayref="y",
                                   showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=1.6, arrowcolor=color, text="")
            fig.add_trace(go.Scatter(
                x=[xs[-1]], y=[ys[-1]], mode="markers+text", text=[r["etf"]], textposition="top center",
                textfont=dict(size=12, color="#EDEDED"), showlegend=False,
                marker=dict(size=14, color=color, line=dict(width=2, color="#000")),
                hovertemplate=(f"<b>{r['sector']} ({r['etf']})</b><br>{r['quadrant'].title()} — {_QUAD[r['quadrant']][2]}"
                               f"<br>RS-ratio %{{x:.2f}} · RS-momentum %{{y:.2f}}"
                               + (f"<br>1M vs SPY {r['rel_1m']:+.1f}%" if r.get("rel_1m") is not None else "")
                               + "<extra></extra>")))
        fig.update_layout(xaxis=dict(title="Relative strength (RS-ratio)", range=[lo, hi], showgrid=False, zeroline=False),
                          yaxis=dict(title="Relative momentum (RS-momentum)", range=[lo, hi], side="left", showgrid=False,
                                     zeroline=False, scaleanchor="x", scaleratio=1))
        left, right = st.columns([3, 2], gap="large")
        with left:
            plot(fig, key="rrg")
        with right:
            order = {"LEADING": 0, "WEAKENING": 1, "IMPROVING": 2, "LAGGING": 3}
            rows = []
            for r in sorted(rrg, key=lambda r: (order[r["quadrant"]], -r["rs_ratio"])):
                color = _QUAD[r["quadrant"]][0]
                rows.append([
                    f'{tkr(r["etf"])} <span class="dim">{_esc(r["sector"])}</span>',
                    f'<span style="color:{color};font-weight:600">{r["quadrant"].title()}</span>',
                    f'<span title="direction of travel this week" style="font-size:15px">{_arrow(r["heading_deg"])}</span>',
                    signed(r.get("rel_1m"), "{:+.1f}", "%"),
                ])
            table(["Sector", "Quadrant", "Heading", "1M vs SPY"], rows, align="llcr")
            st.caption("Heading = direction the sector moved on the graph over the last week.")
    divider()
    section("Statistical arbitrage", "Engle-Granger cointegration on ~1 year of daily closes · z-score of the spread")
    arb = stat_arb_screener()
    st.markdown(render_stat_arb_cards(arb), unsafe_allow_html=True)


# ── Volatility ──────────────────────────────────────────────────────────────
def _vol_surface():
    spy, vix = yahoo_quote("SPY"), get_vix_full()[0]
    if not (spy and vix):
        return
    section("Risk-neutral price distribution", f"SPY lognormal density using VIX {vix:.1f} as a flat volatility "
                                               "(no skew) · darker = less likely")
    s0, sigma = spy["price"], vix / 100
    days = np.linspace(2, 90, 30)
    k = s0 * np.linspace(0.85, 1.15, 40)
    K, D = np.meshgrid(k, days)
    T = D / 365
    d2 = (np.log(s0 / K) - 0.5 * sigma ** 2 * T) / (sigma * np.sqrt(T))
    pdf = np.exp(-0.5 * d2 ** 2) / (K * sigma * np.sqrt(2 * np.pi * T))
    pdf = pdf / pdf.max(axis=1, keepdims=True)  # normalise each expiry so all horizons are visible
    fig = go.Figure(go.Heatmap(z=pdf, x=k, y=days, colorscale=[[0, "#000000"], [1, "#FFFFFF"]], showscale=False,
                               hovertemplate="Strike %{x:.0f}<br>%{y:.0f} days<br>Relative density %{z:.2f}<extra></extra>"))
    fig.add_vline(x=s0, line=dict(color=UP, width=1, dash="dot"))
    from sentinel.ui.theme import chart_layout
    fig.update_layout(**chart_layout(height=320, hovermode="closest", margin=dict(l=8, r=48, t=16, b=8)))
    fig.update_layout(xaxis=dict(title="Strike", tickprefix="$"), yaxis=dict(title="Days to expiry", side="left"))
    plot(fig, key="rnd_heat")


def _volatility():
    c1, _ = st.columns([1, 3])
    with c1:
        t = st.text_input("Underlying", value=st.session_state.master_ticker or "SPY", key="iv_ts_tkr").upper().strip() or "SPY"
    term, skew, rv = get_iv_term_structure(t), get_iv_skew(t), get_rv_iv_spread(t)
    if rv:
        cards([
            ("Realised vol (20D)", f"{rv['rv20']:.1f}%"),
            (f"ATM implied ({rv['dte']}D)", f"{rv['front_iv']:.1f}%"),
            ("Realised − implied", f"{rv['spread']:+.1f} pts", "positive = options cheap vs realised",
             TEXT_DIM, signed_color(rv["spread"])),
            ("Read", rv["signal"].title(), "", TEXT_DIM, UP if rv["signal"] == "BUY VOL" else DOWN if rv["signal"] == "SELL VOL" else TEXT),
        ])
    left, right = st.columns(2)
    with left:
        section("IV term structure", "ATM implied volatility by expiry")
        if term:
            fig = dark_fig(300, hovermode="x unified")
            fig.add_trace(go.Scatter(x=[d["dte"] for d in term], y=[d["atm_iv"] for d in term], mode="lines+markers",
                                     line=dict(color=SERIES[0], width=2), marker=dict(size=6),
                                     customdata=[d["expiry"] for d in term],
                                     hovertemplate="%{customdata} · %{x}d<br>ATM IV %{y:.1f}%<extra></extra>"))
            fig.update_layout(xaxis=dict(title="Days to expiry"), yaxis=dict(ticksuffix="%"))
            plot(fig, key=f"ivts_{t}")
        else:
            empty("No listed options data for this symbol.")
    with right:
        section("25-delta skew", "Put IV − call IV at 25Δ; positive = downside protection is bid")
        if skew:
            fig = dark_fig(300, showlegend=True, hovermode="x unified")
            dtes = [d["dte"] for d in skew]
            fig.add_trace(go.Scatter(x=dtes, y=[d["iv_25p"] for d in skew], name="25Δ put", line=dict(color=DOWN, width=1.5)))
            fig.add_trace(go.Scatter(x=dtes, y=[d["iv_atm"] for d in skew], name="ATM", line=dict(color=SERIES[0], width=2)))
            fig.add_trace(go.Scatter(x=dtes, y=[d["iv_25c"] for d in skew], name="25Δ call", line=dict(color=UP, width=1.5)))
            fig.update_layout(xaxis=dict(title="Days to expiry"), yaxis=dict(ticksuffix="%"))
            plot(fig, key=f"skew_{t}")
        else:
            empty("Skew unavailable.")
    divider()
    _vol_surface()
    divider()
    section("Gamma-squeeze scanner", "High short interest + volume spike vs 20-day average (retail-heavy universe)")
    sq = get_gamma_squeeze_scanner()
    rows = [[tkr(s["ticker"]), f'${s["price"]:,.2f}', f'{s["short_pct"]:.1f}%', f'{s["short_ratio"]:.1f}',
             f'{s["vol_ratio"]:.1f}×', f'<b>{s["squeeze_score"]:.0f}</b>',
             _esc(s["signal"].replace("🔴 ", "").replace("🟡 ", "").replace("🟢 ", "").title())] for s in (sq or [])[:12]]
    table(["Ticker", "Last", "Short % float", "Days to cover", "Volume ×", "Score", "Signal"], rows,
          empty_text="No squeeze candidates right now.")


def render():
    sub = st.segmented_control("Section", SUBPAGES, default="Overview", key="mk_sub",
                               label_visibility="collapsed") or "Overview"
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    if sub == "Overview":
        _overview()
    elif sub == "Heatmap":
        _heatmap()
    elif sub == "Ticker":
        with st.form("ticker_lookup", border=False):
            c1, c2 = st.columns([3, 1])
            t = c1.text_input("Ticker", value=st.session_state.master_ticker, placeholder="NVDA, AAPL, SPY, BTC-USD…",
                              label_visibility="collapsed")
            if c2.form_submit_button("Look up", width="stretch"):
                st.session_state.master_ticker = t.upper().strip()[:16]
        if st.session_state.master_ticker:
            render_ticker(st.session_state.master_ticker)
        else:
            note("Enter a symbol to load quote, chart, fundamentals, earnings, insiders and short interest.")
    elif sub == "Rotation":
        _rotation()
    else:
        _volatility()
