"""Options: listed chain + strategy builder, and the SPX 0DTE / gamma dashboard."""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from sentinel.analytics.options_math import (
    bs_greeks_engine, bs_price, compute_max_pain, compute_pcr, get_iv_newton, year_fraction_to_expiry,
)
from sentinel.analytics.payoff import Leg, analyze
from sentinel.core.formatting import _esc, fmt_p, fmt_usd
from sentinel.data.macro import get_risk_free_rate
from sentinel.data.market import yahoo_quote
from sentinel.data.options import options_chain, options_expiries, score_options_chain
from sentinel.data.zero_dte import (
    compute_cboe_gex_profile, compute_cboe_pcr, compute_cboe_total_gex, compute_gex_profile, compute_spx_direction,
    fetch_0dte_chain, fetch_cboe_gex, fetch_vix_data, find_gamma_flip, generate_recommendation, get_spx_metrics,
)
from sentinel.data.market import is_0dte_market_open
from sentinel.state import has_alpaca, key
from sentinel.ui.charts import render_0dte_gex_chart
from sentinel.ui.components import (
    cards, divider, empty, note, render_options_table, render_scored_options, render_unusual_trade,
    section, table,
)
from sentinel.ui.palette import DOWN, SERIES, TEXT, TEXT_DIM, UP, signed_color
from sentinel.ui.theme import dark_fig, go, plot
from sentinel.ui.zero_dte import render_0dte_gex_decoder, render_0dte_recommendation, render_0dte_trade_log

# (kind, signed qty multiplier, strike slot) — slots are ascending strikes K1 < K2 < …
STRATEGIES = {
    "Long call": [("call", 1, 1)],
    "Long put": [("put", 1, 1)],
    "Short call": [("call", -1, 1)],
    "Short put": [("put", -1, 1)],
    "Covered call": [("stock", 1, 0), ("call", -1, 1)],
    "Protective put": [("stock", 1, 0), ("put", 1, 1)],
    "Bull call spread": [("call", 1, 1), ("call", -1, 2)],
    "Bear put spread": [("put", -1, 1), ("put", 1, 2)],
    "Bull put spread": [("put", 1, 1), ("put", -1, 2)],
    "Bear call spread": [("call", -1, 1), ("call", 1, 2)],
    "Long straddle": [("call", 1, 1), ("put", 1, 1)],
    "Long strangle": [("put", 1, 1), ("call", 1, 2)],
    "Short strangle": [("put", -1, 1), ("call", -1, 2)],
    "Iron condor": [("put", 1, 1), ("put", -1, 2), ("call", -1, 3), ("call", 1, 4)],
    "Iron butterfly": [("put", 1, 1), ("put", -1, 2), ("call", -1, 2), ("call", 1, 3)],
    "Collar": [("stock", 1, 0), ("put", 1, 1), ("call", -1, 2)],
    "Call ratio backspread": [("call", -1, 1), ("call", 2, 2)],
    "Put ratio backspread": [("put", 2, 1), ("put", -1, 2)],
}


def _mid(df, strike):
    """Mid (bid/ask) for the contract nearest *strike*, else last trade, else None."""
    if df is None or df.empty:
        return None
    row = df.iloc[(df["strike"] - strike).abs().argsort()[:1]].iloc[0]
    b, a, last = (float(row.get(c) or 0) for c in ("bid", "ask", "lastPrice"))
    if b > 0 and a >= b:
        return (a + b) / 2
    return last if last > 0 else None


def _atm_iv(calls, puts, spot, T=None, r=0.04):
    """ATM implied vol solved from live mid prices (Yahoo's IV field is unreliable near expiry)."""
    vals = []
    for df, side in ((calls, "call"), (puts, "put")):
        if df is None or df.empty:
            continue
        for _, row in df.iloc[(df["strike"] - spot).abs().argsort()[:2]].iterrows():
            k = float(row["strike"])
            mid = _mid(df, k)
            iv = get_iv_newton(spot, k, T, r, mid, side) if (mid and T) else None
            if iv is None or not (0.01 < iv < 5):
                y = float(row.get("impliedVolatility") or 0)
                iv = y if 0.02 < y < 5 else None
            if iv:
                vals.append(iv)
    return float(np.median(vals)) if vals else None


def _strategy_builder(t, spot, calls, puts, expiry):
    section("Strategy builder", "P&L at expiry · premiums from live mid prices (Black-Scholes if no quote)")
    strikes = sorted(set((calls["strike"] if calls is not None else pd.Series(dtype=float)).tolist()) |
                     set((puts["strike"] if puts is not None else pd.Series(dtype=float)).tolist()))
    T = year_fraction_to_expiry(expiry) if expiry else 30 / 365
    r = get_risk_free_rate(key("fred_key"))
    atm_iv = _atm_iv(calls, puts, spot, T, r) or 0.25

    c1, c2, c3 = st.columns([2, 1, 1])
    strat = c1.selectbox("Strategy", list(STRATEGIES), key=f"lv_strat_{t}")
    qty = c2.number_input("Contracts", 1, 500, 1, key=f"lv_qty_{t}")
    iv_pct = c3.number_input("IV for Greeks / PoP (%)", 1.0, 300.0, round(atm_iv * 100, 1), 0.5, key=f"lv_iv_{t}_{expiry}",
                             help="Defaults to the ATM implied volatility of this expiry.")
    legs_spec = STRATEGIES[strat]
    slots = sorted({s for _, _, s in legs_spec if s})
    chosen = {}
    if strikes and slots:
        atm_i = int(np.argmin([abs(k - spot) for k in strikes]))
        step = max(1, len(strikes) // 40)
        cols = st.columns(len(slots))
        for j, slot in enumerate(slots):
            offset = (j - (len(slots) - 1) / 2) * 2 * step
            default = strikes[int(min(max(atm_i + offset, 0), len(strikes) - 1))]
            chosen[slot] = cols[j].select_slider(f"K{slot}", options=strikes, value=default, key=f"lv_k{slot}_{t}_{expiry}")
        ks = [chosen[s] for s in slots]
        if ks != sorted(ks):
            note("Strikes should increase K1 < K2 < … for this structure; results use the order shown.", "warn")

    sigma = iv_pct / 100
    legs = []
    for kind, mult, slot in legs_spec:
        if kind == "stock":
            legs.append(Leg("stock", mult * qty))
            continue
        k = chosen.get(slot, spot)
        prem = _mid(calls if kind == "call" else puts, k)
        if prem is None:
            prem = bs_price(spot, k, T, r, sigma, kind)
        legs.append(Leg(kind, mult * qty, k, prem))
    res = analyze(legs, spot, T, r, sigma)

    debit = res["net_debit"]
    mp, ml = res["max_profit"], res["max_loss"]
    bes = res["breakevens"]
    cards([
        ("Net debit" if debit >= 0 else "Net credit", fmt_usd(abs(debit)), f"{qty} × {strat.lower()}"),
        ("Max profit", "Unlimited" if math.isinf(mp) else fmt_usd(mp), "", TEXT_DIM, UP),
        ("Max loss", "Unlimited" if math.isinf(ml) else fmt_usd(ml), "", TEXT_DIM, DOWN),
        ("Breakeven", " / ".join(f"{b:,.2f}" for b in bes) if bes else "—",
         " / ".join(f"{(b / spot - 1) * 100:+.1f}%" for b in bes) if bes else ""),
        ("Probability of profit", f"{res['pop']:.0f}%" if res["pop"] is not None else "—", "risk-neutral, at expiry"),
    ], 150)

    lo, hi = spot * 0.8, spot * 1.2
    m = (res["grid"] >= lo) & (res["grid"] <= hi)
    x, y = res["grid"][m], res["pnl"][m]
    fig = dark_fig(320, hovermode="x unified", title=dict(text=f"{t} · {strat} · expiry {expiry}"))
    fig.add_trace(go.Scatter(x=x, y=np.where(y >= 0, y, 0), fill="tozeroy", mode="none", fillcolor="rgba(63,207,142,0.18)",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=np.where(y < 0, y, 0), fill="tozeroy", mode="none", fillcolor="rgba(242,85,90,0.18)",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=TEXT, width=2),
                             hovertemplate="Price %{x:,.2f}<br>P&L %{y:$,.0f}<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="#333", width=1))
    fig.add_vline(x=spot, line=dict(color=SERIES[2], dash="dot", width=1), annotation_text=f"spot {spot:,.2f}",
                  annotation_font=dict(size=10, color=TEXT_DIM))
    for b in bes:
        if lo <= b <= hi:
            fig.add_vline(x=b, line=dict(color=SERIES[1], width=1))
    fig.update_layout(yaxis=dict(tickprefix="$"), xaxis=dict(tickformat=",.0f"))
    plot(fig, key=f"payoff_{t}")

    g = res["greeks"]
    cards([
        ("Position delta", f"{g['delta']:+,.1f}", "shares-equivalent"),
        ("Gamma", f"{g['gamma']:+,.3f}", "Δ change per $1"),
        ("Theta", f"{g['theta']:+,.2f}", "$ per calendar day", TEXT_DIM, signed_color(g["theta"])),
        ("Vega", f"{g['vega']:+,.2f}", "$ per 1 vol point"),
    ], 150)
    st.caption(f"T = {T * 365:.1f} days to 4 pm ET expiry · r = {r * 100:.2f}% · σ = {iv_pct:.1f}%")


def _chain_section():
    with st.form("opt_lookup", border=False):
        c1, c2 = st.columns([3, 1])
        t = c1.text_input("Underlying", value=st.session_state.master_ticker or "SPY",
                          placeholder="SPY, NVDA, AAPL…", label_visibility="collapsed")
        if c2.form_submit_button("Load chain", width="stretch"):
            st.session_state.master_ticker = t.upper().strip()[:16]
    t = st.session_state.master_ticker or "SPY"
    q = yahoo_quote(t)
    if not q:
        note(f"No quote for {t}.", "warn")
        return
    exps = options_expiries(t)
    if not exps:
        note(f"No listed options found for {t}.", "warn")
        return

    def _fmt(d):
        try:
            dt = datetime.strptime(d, "%Y-%m-%d").date()
            return f"{dt:%b %d, %Y} · {(dt - datetime.today().date()).days}d"
        except ValueError:
            return d

    c1, c2 = st.columns([2, 3])
    with c1:
        today = datetime.today().date()
        default_i = next((i for i, e in enumerate(exps)
                          if (datetime.strptime(e, "%Y-%m-%d").date() - today).days >= 7), 0)
        expiry = st.selectbox("Expiry", exps, index=default_i, key=f"opt_exp_{t}", format_func=_fmt)
    calls, puts, expiry = options_chain(t, expiry)
    with c2:
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        cards([(t, fmt_p(q["price"], t), f"{q['pct']:+.2f}% today", signed_color(q["pct"]))], 150)
    if calls is None and puts is None:
        note("Options chain failed to load (Yahoo rate limit). Try again shortly.", "warn")
        return
    spot = float(q["price"])
    chain_list = ([{"strike": s, "type": "call", "oi": o} for s, o in zip(calls["strike"], calls["openInterest"].fillna(0))] if calls is not None else []) + \
                 ([{"strike": s, "type": "put", "oi": o} for s, o in zip(puts["strike"], puts["openInterest"].fillna(0))] if puts is not None else [])
    pcr = compute_pcr(chain_list)
    mp = compute_max_pain(chain_list)
    T = year_fraction_to_expiry(expiry)
    atm = _atm_iv(calls, puts, spot, T, get_risk_free_rate(key("fred_key")))
    em = spot * atm * math.sqrt(T) if atm else None
    cards([
        ("ATM implied vol", f"{atm * 100:.1f}%" if atm else "—"),
        ("Expected move (1σ)", f"±{em:,.2f}" if em else "—", f"±{em / spot * 100:.1f}% to expiry" if em else ""),
        ("Put / call OI", f"{pcr:.2f}" if pcr else "—", ">1 = more puts open"),
        ("Max pain", f"{mp:,.2f}" if mp else "—", f"{(mp / spot - 1) * 100:+.1f}% vs spot" if mp else ""),
    ], 150)
    divider()
    _strategy_builder(t, spot, calls, puts, expiry)
    divider()
    section("Contract screener", "Score = unusual volume/OI, IV rank within chain and closeness to 0.5 delta")
    scored = score_options_chain(calls, puts, spot, vix=(fetch_vix_data() or {}).get("vix"), expiry_date=expiry,
                                 fred_key=key("fred_key"))
    a, b = st.columns(2)
    with a:
        st.markdown(f'<div class="s-card-lbl" style="color:{UP}">Calls</div>', unsafe_allow_html=True)
        st.markdown(render_scored_options(scored["top_calls"], "calls"), unsafe_allow_html=True)
    with b:
        st.markdown(f'<div class="s-card-lbl" style="color:{DOWN}">Puts</div>', unsafe_allow_html=True)
        st.markdown(render_scored_options(scored["top_puts"], "puts"), unsafe_allow_html=True)
    if scored.get("unusual"):
        st.markdown(render_unusual_trade(scored["unusual"], t, _fmt(expiry)), unsafe_allow_html=True)
    with st.expander("Full chain (24 strikes nearest spot)"):
        a, b = st.columns(2)
        a.markdown(render_options_table(calls, "calls", spot), unsafe_allow_html=True)
        b.markdown(render_options_table(puts, "puts", spot), unsafe_allow_html=True)
    with st.expander("Black-Scholes calculator"):
        c = st.columns(5)
        s_ = c[0].number_input("Spot", value=spot, format="%.2f", key=f"bs_s_{t}")
        k_ = c[1].number_input("Strike", value=spot, format="%.2f", key=f"bs_k_{t}")
        d_ = c[2].number_input("Days", value=max(T * 365, 0.1), format="%.1f", key=f"bs_d_{t}")
        v_ = c[3].number_input("IV %", value=(atm or 0.2) * 100, format="%.1f", key=f"bs_v_{t}")
        side = c[4].selectbox("Type", ["call", "put"], key=f"bs_side_{t}")
        r = get_risk_free_rate(key("fred_key"))
        price = bs_price(s_, k_, d_ / 365, r, v_ / 100, side)
        g = bs_greeks_engine(s_, k_, d_ / 365, r, v_ / 100, side)
        cards([("Price", f"${price:,.2f}"), ("Delta", f"{g['delta']:+.4f}"), ("Gamma", f"{g['gamma']:.5f}"),
               ("Theta / day", f"{g['theta']:+.4f}"), ("Vega / vol pt", f"{g['vega']:.4f}"), ("Rho / 1%", f"{g['rho']:+.4f}")], 120)


# ── SPX 0DTE ────────────────────────────────────────────────────────────────
def _zero_dte():
    is_open, msg = is_0dte_market_open()
    vix = fetch_vix_data() or {}
    spot_cboe, opts = fetch_cboe_gex("SPX")
    spx = get_spx_metrics() if has_alpaca() else None
    chain, chain_status = fetch_0dte_chain("SPY") if has_alpaca() else ([], "No Alpaca keys")
    if not has_alpaca():
        note("SPX gamma levels below use CBOE delayed data (keyless). Add ALPACA_API_KEY and ALPACA_SECRET_KEY to "
             "secrets for the live SPY 0DTE chain, VWAP and the direction model.")
    if not is_open:
        st.markdown(f'<div class="s-note s-fade">{_esc(msg)} — showing the latest available data.</div>',
                    unsafe_allow_html=True)

    spot = spot_cboe or (spx or {}).get("spot")
    pcr = compute_pcr(chain) if chain else compute_cboe_pcr(opts)
    cards([
        ("SPX", f"{spot:,.2f}" if spot else "—", "CBOE delayed" if spot_cboe else ""),
        ("VIX", f"{vix['vix']:.2f}" if vix.get("vix") else "—",
         f"VIX9D {vix['vix9d']:.2f}" if vix.get("vix9d") else ""),
        ("Term structure", "Contango" if vix.get("contango") else "Backwardation" if vix.get("contango") is False else "—",
         "9D below 30D = calm" if vix.get("contango") else "9D above 30D = near-term stress", TEXT_DIM,
         UP if vix.get("contango") else DOWN if vix.get("contango") is False else TEXT),
        ("Put / call OI", f"{pcr:.2f}" if pcr else "—", "0DTE chain" if chain else "all SPX expiries"),
        ("Session VWAP", f"{spx['vwap']:,.2f}" if spx and spx.get("vwap") else "—", "Alpaca SPY × live ratio" if spx else ""),
    ], 150)

    divider()
    section("Gamma exposure", "Dealer GEX by strike, $M per 1% move (assumes dealers long calls / short puts)")
    c1, c2 = st.columns(2)
    exp_choice = c1.selectbox("Expiries", ["Nearest (0DTE)", "≤ 7 days", "≤ 30 days", "≤ 90 days", "All"], key="gex_exp")
    rng = c2.selectbox("Strike window", ["±1.5%", "±3%", "±5%"], index=0, key="gex_rng")
    days = {"Nearest (0DTE)": 1, "≤ 7 days": 7, "≤ 30 days": 30, "≤ 90 days": 90, "All": 3650}[exp_choice]
    pct = {"±1.5%": 0.015, "±3%": 0.03, "±5%": 0.05}[rng]

    if spot_cboe and opts is not None:
        gex = compute_cboe_gex_profile(spot_cboe, opts, expiry_limit_days=days, strike_pct=pct + 0.02)
        total = compute_cboe_total_gex(spot_cboe, opts)
        ratio, src = 1.0, "CBOE delayed SPX chain"
    elif chain and spx and spx.get("spy_spot"):
        ratio = spx["spx_spy_ratio"]
        gex = compute_gex_profile(chain, spx["spy_spot"])
        total, src = None, "Alpaca SPY 0DTE chain (scaled to SPX)"
    else:
        gex, total, ratio, src = {}, None, 1.0, ""
    if not gex:
        empty("Gamma data unavailable (CBOE delayed feed did not respond).")
    else:
        flip = find_gamma_flip(gex)
        mp_raw = compute_max_pain(chain) if chain else None  # None when the chain has no open interest
        mp = mp_raw * (spx["spx_spy_ratio"] if spx else 1) if mp_raw else None
        wall_k, wall_v = max(gex.items(), key=lambda kv: abs(kv[1]))
        left, right = st.columns([3, 2])
        with left:
            fig = render_0dte_gex_chart(gex, flip, (mp / ratio) if mp else None, spot_spx=spot, display_pct=pct,
                                        spx_spy_ratio=ratio)
            if fig:
                plot(fig, key="gex_chart")
            st.caption(f"Source: {src}" + (f" · net GEX all expiries {fmt_usd(total * 1e9)}" if total is not None else ""))
        with right:
            fig = dark_fig(500, hovermode="y unified", title=dict(text="GEX by strike ($M)"))
            ks = sorted(gex)
            fig.add_trace(go.Bar(y=[k * ratio for k in ks], x=[gex[k] for k in ks], orientation="h",
                                 marker_color=[UP if gex[k] >= 0 else DOWN for k in ks], marker_line_width=0,
                                 hovertemplate="%{y:,.0f}: $%{x:,.1f}M<extra></extra>"))
            if spot:
                fig.add_hline(y=spot, line=dict(color=TEXT, width=1, dash="dot"))
            fig.update_layout(yaxis=dict(range=[spot * (1 - pct), spot * (1 + pct)] if spot else None, tickformat=",.0f"),
                              bargap=0.15)
            plot(fig, key="gex_bars")
        st.markdown(render_0dte_gex_decoder(flip * ratio if flip else None, mp, wall_k * ratio, wall_v, spot),
                    unsafe_allow_html=True)

    if not chain or not spx:
        if has_alpaca():
            note(f"0DTE chain: {chain_status}", "warn")
        return

    divider()
    section("Direction model", "Weighted signals from gamma, VWAP, put/call, max pain, VIX regime, RSI and MACD")
    d = compute_spx_direction(chain, spx, vix)
    if d:
        cards([
            ("Bias", d["direction"].title(), f"confidence {d['confidence'].lower()}", TEXT_DIM, d["direction_color"]),
            ("Score", f"{d['score']:+.1f}", f"of ±{d['max_score']:.1f}"),
            ("Expected range", d["expected_range"], f"1σ day move ±{d['daily_em']:.0f} pts (VIX {d['vix']:.1f})"),
        ], 180)
        rows = [[_esc(n), _esc(v), f'<span style="color:{signed_color(w)}">{w:+.1f}</span>', f'<span class="dim">{_esc(desc)}</span>']
                for n, v, w, desc, _ in d["signals"]]
        table(["Signal", "Value", "Weight", "Read"], rows, align="llrw")

    divider()
    section("Trade analyzer", "Research tool only — not a recommendation to trade.")
    log = st.session_state.trade_log_0dte
    a, b = st.columns([1, 4])
    if a.button("Analyze now", key="analyze_0dte", width="stretch"):
        rec = generate_recommendation(chain, spx, vix)
        if rec:
            st.session_state._last_rec = rec
            if "NO TRADE" not in rec["recommendation"]:
                log.append(f"{datetime.now():%H:%M} {rec['recommendation'].replace('RECOMMENDATION: ', '')}")
                del log[:-10]
    if b.button("Clear log", key="clear_log_0dte"):
        log.clear()
        st.session_state.pop("_last_rec", None)
    if st.session_state.get("_last_rec"):
        st.markdown(render_0dte_recommendation(st.session_state._last_rec), unsafe_allow_html=True)
    if log:
        st.markdown(render_0dte_trade_log(log), unsafe_allow_html=True)

    with st.expander("Kelly position sizing"):
        c = st.columns(3)
        p = c[0].number_input("Win rate (%)", 1.0, 99.0, 55.0, 1.0) / 100
        b_ = c[1].number_input("Avg win / avg loss", 0.1, 20.0, 1.5, 0.1)
        bank = c[2].number_input("Account size ($)", 100.0, 1e9, 10_000.0, 100.0)
        f = max(0.0, p - (1 - p) / b_)
        cards([("Full Kelly", f"{f * 100:.1f}%"), ("Half Kelly", f"{f * 50:.1f}%"),
               ("Half-Kelly risk", fmt_usd(bank * f / 2), "max capital at risk per trade")], 150)


def render():
    subs = ["Chain & strategy", "Exposure (GEX)", "SPX 0DTE"]
    if st.session_state.get("opt_sub") not in subs:
        st.session_state["opt_sub"] = subs[0]
    sub = st.segmented_control("Section", subs, key="opt_sub", label_visibility="collapsed") or subs[0]
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    if sub == "Chain & strategy":
        _chain_section()
    elif sub == "Exposure (GEX)":
        from sentinel.pages import exposure
        exposure.render()
    else:
        @st.fragment(run_every="60s")
        def _live():
            _zero_dte()
        _live()
