"""Crypto spot: CoinGecko market, sentiment, BTC ETF flow proxy, charts."""
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from sentinel.config import ETF_TICKERS
from sentinel.core.formatting import _esc, fmt_p, fmt_usd
from sentinel.data.crypto import crypto_global, crypto_markets, fear_greed_crypto, fetch_btc_etf_flows
from sentinel.ui.charts import render_crypto_etf_chart
from sentinel.ui.components import cards, divider, empty, note, section, signed, table, tkr, tv_chart
from sentinel.ui.palette import DOWN, TEXT, TEXT_DIM, UP, signed_color
from sentinel.ui.theme import plot


def render():
    g = crypto_global()
    fv, fl = fear_greed_crypto()
    if g:
        cap = g.get("total_market_cap", {}).get("usd", 0)
        vol = g.get("total_volume", {}).get("usd", 0)
        chg = g.get("market_cap_change_percentage_24h_usd")
        dom = g.get("market_cap_percentage", {})
        items = [
            ("Total market cap", fmt_usd(cap), f"{chg:+.2f}% 24h" if chg is not None else "", signed_color(chg or 0)),
            ("24h volume", fmt_usd(vol)),
            ("BTC dominance", f"{dom.get('btc', 0):.1f}%"),
            ("ETH dominance", f"{dom.get('eth', 0):.1f}%"),
        ]
        if fv is not None:
            items.append(("Fear & greed", f"{fv}", fl, TEXT_DIM, UP if fv >= 55 else DOWN if fv < 45 else TEXT))
        cards(items, 150)
    else:
        note("CoinGecko global data unavailable (rate limited) — retrying on next refresh.", "warn")

    divider()
    left, right = st.columns([5, 4], gap="large")
    with left:
        section("Top 20 by market cap", "CoinGecko")
        coins = crypto_markets()
        rows = []
        for c in coins or []:
            if not isinstance(c, dict) or not c.get("current_price"):
                continue
            rows.append([f'{c.get("market_cap_rank") or ""}', tkr(str(c.get("symbol", "")).upper()),
                         f'<span class="dim">{_esc(c.get("name", ""))}</span>', fmt_p(c["current_price"]),
                         signed(c.get("price_change_percentage_24h"), "{:+.2f}", "%", True),
                         fmt_usd(c.get("total_volume")), fmt_usd(c.get("market_cap"))])
        table(["#", "Coin", "Name", "Price", "24h", "Volume", "Market cap"], rows, align="rllrrrr",
              empty_text="CoinGecko unavailable (rate limited).")
    with right:
        section("BTC / USD")
        sym = st.segmented_control("Chart", ["BTC", "ETH", "SOL"], default="BTC", key="cr_chart",
                                   label_visibility="collapsed") or "BTC"
        components.html(tv_chart(f"COINBASE:{sym}USD", 480), height=485)

    divider()
    section("Spot bitcoin ETFs", "Daily directional dollar-volume proxy: volume × typical price × sign of the day's move. "
                                 "This is NOT creations/redemptions — treat it as a sentiment gauge.")
    df = fetch_btc_etf_flows()
    if df is None or df.empty:
        empty("ETF data unavailable.")
        return
    fig = render_crypto_etf_chart(df)
    if fig:
        plot(fig, key="etf_flows")
    last = df.iloc[-1]
    by_etf = {t: float(last[t]) for t in ETF_TICKERS if t in last.index}
    top = max(by_etf.items(), key=lambda kv: abs(kv[1])) if by_etf else ("—", 0.0)
    cards([
        ("Latest session", df.index[-1].strftime("%b %d, %Y")),
        ("Net proxy", f"{last['Total']:+.2f}B", "", TEXT_DIM, signed_color(last["Total"])),
        ("Up / down funds", f"{sum(v > 0 for v in by_etf.values())} / {sum(v < 0 for v in by_etf.values())}"),
        ("Largest", top[0], f"{top[1]:+.2f}B", signed_color(top[1])),
    ], 150)
