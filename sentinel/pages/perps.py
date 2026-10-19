"""Hyperliquid perpetuals: market screener, funding, order book, candles."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sentinel.core.formatting import _esc, fmt_pct, fmt_usd
from sentinel.data.hyperliquid import (
    CANDLE_INTERVALS, hl_candles, hl_funding_history, hl_markets, hl_order_book,
    hl_perp_dexs, hl_recent_trades, hl_summary,
)
from sentinel.ui.charts import candlestick_chart
from sentinel.ui.components import cards, colored, divider, empty, note, section, signed, table, tkr
from sentinel.ui.palette import DOWN, FLAT, SERIES, TEXT_DIM, UP, signed_color
from sentinel.ui.theme import dark_fig, go, plot

_SORTS = {
    "24h volume": ("volume_24h_usd", False),
    "Open interest": ("oi_usd", False),
    "24h change ↑": ("chg_24h_pct", False),
    "24h change ↓": ("chg_24h_pct", True),
    "Funding APR ↑": ("funding_apr_pct", False),
    "Funding APR ↓": ("funding_apr_pct", True),
}


def _px(v):
    if v is None:
        return "—"
    v = float(v)
    if v >= 1000:
        return f"{v:,.1f}"
    if v >= 1:
        return f"{v:,.3f}".rstrip("0").rstrip(".") if v < 10 else f"{v:,.2f}"
    return f"{v:.6g}"


def render():
    section("Hyperliquid perpetuals", "Live public data from api.hyperliquid.xyz · funding is paid hourly · "
                                     "APR = hourly rate × 8,760 · OI converted to USD at mark.")

    dexs = hl_perp_dexs()
    c1, c2, c3 = st.columns([1.2, 1.2, 2])
    with c1:
        dex = st.selectbox("Venue", dexs, format_func=lambda d: "Hyperliquid (main)" if d == "" else f"HIP-3 · {d}",
                           key="hl_dex")
    with c2:
        sort_by = st.selectbox("Sort by", list(_SORTS), key="hl_sort")
    with c3:
        query = st.text_input("Filter", placeholder="BTC, ETH, SOL…", key="hl_q").strip().upper()

    @st.fragment(run_every="20s")
    def _overview():
        df = hl_markets(dex)
        if df.empty:
            note("Hyperliquid API unavailable right now — retrying automatically.", "warn")
            return
        s = hl_summary(df)
        cards([
            ("Markets", f"{s['markets']}", f"{s['advancers']} up · {s['decliners']} down"),
            ("Open interest", fmt_usd(s["oi_usd"])),
            ("24h volume", fmt_usd(s["volume_24h_usd"])),
            ("OI-weighted funding", fmt_pct(s["oi_weighted_funding_apr"]) + " APR" if s["oi_weighted_funding_apr"] is not None else "—",
             f"{s['positive_funding_share']:.0f}% of markets longs pay", TEXT_DIM,
             signed_color(s["oi_weighted_funding_apr"] or 0)),
        ])
        view = df
        if query:
            view = view[view["symbol"].str.contains(query, regex=False, na=False)]
        col, asc = _SORTS[sort_by]
        view = view.sort_values(col, ascending=asc, na_position="last").head(60)
        rows = [[
            tkr(r.symbol), _px(r.mark), signed(r.chg_24h_pct, "{:+.2f}", "%"),
            fmt_usd(r.volume_24h_usd), fmt_usd(r.oi_usd),
            signed(r.funding_1h_pct, "{:+.4f}", "%"), signed(r.funding_apr_pct, "{:+.1f}", "%"),
            signed(r.basis_pct, "{:+.3f}", "%"), f"{r.max_leverage}×",
        ] for r in view.itertuples()]
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        table(["Market", "Mark", "24h", "24h volume", "Open interest", "Funding 1h", "Funding APR",
               "Mark vs oracle", "Max lev."], rows, max_height=520, empty_text="No markets match the filter.")

    _overview()

    df = hl_markets(dex)
    if df.empty:
        return

    divider()
    section("Funding extremes", "Positive funding: longs pay shorts. Annualised from the current hourly rate.")
    liquid = df[df["oi_usd"] >= max(250_000, df["oi_usd"].quantile(0.25))]
    top = liquid.nlargest(8, "funding_apr_pct")
    bot = liquid.nsmallest(8, "funding_apr_pct")
    both = pd.concat([top, bot]).drop_duplicates("coin").sort_values("funding_apr_pct")
    fig = dark_fig(max(260, 26 * len(both)), title=dict(text="Funding APR · liquid markets (OI ≥ $250K)"),
                   hovermode="closest")
    fig.add_trace(go.Bar(
        x=both["funding_apr_pct"], y=both["symbol"], orientation="h",
        marker_color=[UP if v > 0 else DOWN for v in both["funding_apr_pct"]], marker_line_width=0,
        text=[f"{v:+.1f}%" for v in both["funding_apr_pct"]], textposition="outside",
        textfont=dict(size=10, color=TEXT_DIM), hovertemplate="%{y}: %{x:+.2f}% APR<extra></extra>",
    ))
    fig.update_layout(xaxis=dict(ticksuffix="%"), yaxis=dict(side="left"), margin=dict(l=8, r=40, t=36, b=8))
    plot(fig, key="hl_funding_bar")

    divider()
    section("Market detail")
    coins = df["coin"].tolist()
    default = coins.index("BTC") if "BTC" in coins else 0
    d1, d2, d3 = st.columns([1.4, 1, 1])
    with d1:
        coin = st.selectbox("Market", coins, index=default, key=f"hl_coin_{dex}",
                            format_func=lambda c: c.split(":", 1)[-1])
    with d2:
        interval = st.selectbox("Candle interval", list(CANDLE_INTERVALS), index=2, key="hl_iv")
    with d3:
        bars = st.select_slider("Bars", options=[60, 120, 200, 300, 500], value=200, key="hl_bars")

    @st.fragment(run_every="15s")
    def _detail():
        row = df[df["coin"] == coin]
        live = hl_markets(dex)
        lrow = live[live["coin"] == coin] if not live.empty else row
        r = (lrow if not lrow.empty else row).iloc[0]
        book = hl_order_book(coin)
        cards([
            ("Mark", _px(r["mark"]), fmt_pct(r["chg_24h_pct"]) + " 24h", signed_color(r["chg_24h_pct"])),
            ("Oracle", _px(r["oracle"]), f"basis {r['basis_pct']:+.3f}%" if r["basis_pct"] is not None else ""),
            ("Funding", f"{r['funding_1h_pct']:+.4f}%/h", f"{r['funding_apr_pct']:+.1f}% APR",
             signed_color(r["funding_apr_pct"])),
            ("Open interest", fmt_usd(r["oi_usd"]), f"{r['oi_base']:,.2f} {r['symbol']}"),
            ("24h volume", fmt_usd(r["volume_24h_usd"])),
            ("Spread", f"{book['spread_bps']:.2f} bps" if book else "—",
             f"book imbalance {book['imbalance_pct']:+.0f}%" if book else "",
             signed_color(book.get("imbalance_pct", 0)) if book else TEXT_DIM),
        ], min_width=140)

        candles = hl_candles(coin, interval, bars)
        if candles.empty:
            empty("No candle data for this market.")
        else:
            plot(candlestick_chart(candles, title=f"{coin.split(':', 1)[-1]}-PERP · {interval}", height=440),
                 key=f"hl_candles_{coin}_{interval}")

        left, right = st.columns([3, 2])
        with left:
            fh = hl_funding_history(coin, 7)
            if fh.empty:
                empty("No funding history.")
            else:
                f = dark_fig(260, title=dict(text="Funding APR · last 7 days (hourly)"), hovermode="x unified")
                f.add_trace(go.Bar(x=fh.index, y=fh["funding_apr_pct"],
                                   marker_color=[UP if v >= 0 else DOWN for v in fh["funding_apr_pct"]],
                                   marker_line_width=0, hovertemplate="%{y:+.2f}% APR<extra></extra>"))
                avg = fh["funding_apr_pct"].mean()
                f.add_hline(y=avg, line=dict(color=SERIES[1], dash="dot", width=1),
                            annotation_text=f"7d avg {avg:+.1f}%", annotation_font=dict(size=10, color=SERIES[1]))
                f.update_layout(yaxis=dict(ticksuffix="%"))
                plot(f, key=f"hl_fh_{coin}")
        with right:
            if book:
                bids, asks = book["bids"], book["asks"]
                f = dark_fig(260, title=dict(text="Order book depth (top 20 levels, USD)"), hovermode="x unified")
                f.add_trace(go.Scatter(x=bids["px"], y=bids["cum_usd"], fill="tozeroy", mode="lines", name="Bids",
                                       line=dict(color=UP, width=1.5, shape="hv"), fillcolor="rgba(63,207,142,0.15)"))
                f.add_trace(go.Scatter(x=asks["px"], y=asks["cum_usd"], fill="tozeroy", mode="lines", name="Asks",
                                       line=dict(color=DOWN, width=1.5, shape="hv"), fillcolor="rgba(242,85,90,0.15)"))
                f.update_layout(yaxis=dict(tickprefix="$"))
                plot(f, key=f"hl_book_{coin}")
            else:
                empty("Order book unavailable.")

        b1, b2 = st.columns(2)
        with b1:
            if book:
                rows = []
                for (_, b), (_, a) in zip(book["bids"].head(10).iterrows(), book["asks"].head(10).iterrows()):
                    rows.append([colored(_px(b["px"]), UP), f"{b['sz']:,.4g}", f"{a['sz']:,.4g}", colored(_px(a["px"]), DOWN)])
                table(["Bid", "Size", "Size", "Ask"], rows, align="rrrr")
        with b2:
            trades = hl_recent_trades(coin)
            if trades.empty:
                empty("No recent trades.")
            else:
                rows = [[t.time.strftime("%H:%M:%S"),
                         colored(t.side, UP if t.side == "BUY" else DOWN if t.side == "SELL" else FLAT, True),
                         _px(t.px), f"{t.sz:,.4g}", fmt_usd(t.usd)] for t in trades.head(10).itertuples()]
                table(["Time (UTC)", "Side", "Price", "Size", "Notional"], rows)
        st.caption(f"{_esc(coin)} · refreshes every 15 s · data © Hyperliquid public API")

    _detail()
