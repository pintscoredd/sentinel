"""Markets → Funds: 13F holdings of well-known managers and what they changed last quarter."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import streamlit as st

from sentinel.core.formatting import _esc, fmt_usd
from sentinel.data.funds import FUNDS, clean_issuer, fund_report
from sentinel.ui.components import cards, colored, divider, empty, note, section, table
from sentinel.ui.palette import DOWN, FLAT, SERIES, TEXT_DIM, UP
from sentinel.ui.theme import dark_fig, go, plot

_CHG_COLOR = {"New": UP, "Added": UP, "Reduced": DOWN, "Exited": DOWN, "Unchanged": FLAT}


def _label(r, dups=()):
    name = clean_issuer(r["issuer"])
    if r["issuer"] in dups:  # e.g. Alphabet Class A and Class C are separate CUSIPs
        cls = str(r.get("cls") or "")
        m = __import__("re").search(r"CL(?:ASS)?\s*([A-Z])\b", cls.upper())
        name += f" · Cl {m.group(1)}" if m else f" · {cls.title()[:12]}"
    return f"{name} ({r['put_call']})" if r.get("put_call") else name


def _single(name):
    rep = fund_report(FUNDS[name])
    if not rep or rep.get("holdings") is None or rep["holdings"].empty:
        empty("Could not load this fund's latest 13F from SEC EDGAR. Try again shortly.")
        return
    f, h = rep["filing"], rep["holdings"]
    age = (date.today() - date.fromisoformat(f["filed"])).days
    live = h[h["value"] > 0]
    dups = set(h.loc[h["issuer"].duplicated(keep=False) & (h["put_call"] == ""), "issuer"])
    chg = h["change"].value_counts()
    tot_chg = (rep["total"] / rep["prev_total"] - 1) * 100 if rep.get("prev_total") else None
    cards([
        ("Reported portfolio", fmt_usd(rep["total"]), f"quarter ending {f['period']}"),
        ("Positions", f"{rep['positions']}", f"top 10 = {live['weight'].head(10).sum():.0f}% of value"),
        ("Value vs prior filing", f"{tot_chg:+.1f}%" if tot_chg is not None else "—", "includes price moves", TEXT_DIM,
         UP if (tot_chg or 0) >= 0 else DOWN),
        ("Changes", f"{chg.get('New', 0)} new · {chg.get('Exited', 0)} exited",
         f"{chg.get('Added', 0)} added · {chg.get('Reduced', 0)} reduced"),
        ("Filed", f["filed"], f"{age} days ago" + (" · may be stale" if age > 140 else ""), TEXT_DIM,
         DOWN if age > 140 else TEXT_DIM),
    ], 170)
    left, right = st.columns([2, 3], gap="large")
    with left:
        top = live.head(15).iloc[::-1]
        fig = dark_fig(max(320, 24 * len(top)), hovermode="closest", title=dict(text="Largest positions · % of portfolio"))
        fig.add_trace(go.Bar(x=top["weight"], y=[_label(r, dups) for _, r in top.iterrows()], orientation="h",
                             marker_color=[_CHG_COLOR.get(c, SERIES[1]) for c in top["change"]], marker_line_width=0,
                             text=[f"{w:.1f}%" for w in top["weight"]], textposition="outside",
                             textfont=dict(size=10, color=TEXT_DIM),
                             hovertemplate="%{y}: %{x:.2f}%<extra></extra>"))
        fig.update_layout(xaxis=dict(ticksuffix="%"), yaxis=dict(side="left"), margin=dict(l=8, r=40, t=36, b=8))
        plot(fig, key="fund_top")
        st.caption("Bar colour = last quarter's action: green new/added, red reduced, grey unchanged.")
    with right:
        q = st.text_input("Filter holdings", placeholder="Company name", key="fund_q").strip().lower()
        view = h if not q else h[h["issuer"].str.lower().str.contains(q, regex=False)]
        rows = []
        for _, r in view.head(80).iterrows():
            c = r["change"]
            pct = r["share_chg_pct"]
            act = colored(c + (f" {pct:+.0f}%" if c in ("Added", "Reduced") and pct == pct else ""), _CHG_COLOR.get(c, FLAT))
            rows.append([_esc(_label(r, dups)), fmt_usd(r["value"]) if r["value"] else '<span class="dim">—</span>',
                         f"{r['weight']:.2f}%" if r["value"] else "—", f"{r['shares']:,.0f}" if r["shares"] else "—", act])
        table(["Holding", "Value", "Weight", "Shares", "Last quarter"], rows, align="wrrrl", max_height=560,
              empty_text="No holdings match.")
    sec_url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={f['cik']}&type=13F-HR"
               "&dateb=&owner=include&count=40")
    st.markdown(f'<a class="dim" style="font-size:12px;text-decoration:none" href="{_esc(sec_url)}" target="_blank" '
                f'rel="noopener noreferrer">All 13F filings on SEC EDGAR ↗</a>', unsafe_allow_html=True)


def _consensus():
    section("Across all tracked funds", "Stocks most added to / cut from in the latest filings · $ change in position value")
    if not st.session_state.get("funds_scan"):
        if st.button("Scan all funds", key="funds_scan_btn"):
            st.session_state["funds_scan"] = True
            st.rerun()
        st.caption(f"Loads the last two 13Fs of all {len(FUNDS)} funds from SEC EDGAR (cached for a week).")
        return
    with st.spinner("Reading filings from SEC EDGAR…"), ThreadPoolExecutor(max_workers=4) as pool:
        reps = dict(zip(FUNDS, pool.map(lambda c: fund_report(c), FUNDS.values())))
    frames = []
    for name, rep in reps.items():
        h = (rep or {}).get("holdings")
        if h is None or h.empty or "prev_value" not in h:
            continue
        h = h[h["put_call"] == ""].copy()
        h["fund"] = name.split(" (")[0]
        h["flow"] = h["value"] - h["prev_value"]
        frames.append(h[["fund", "issuer", "cusip", "change", "flow", "value"]])
    if not frames:
        empty("No filings could be loaded.")
        return
    allh = pd.concat(frames)
    # Stock picks only (ETF trusts are hedges/cash parking), with share classes merged per company.
    allh = allh[~allh["issuer"].str.upper().str.contains(r"\bETF\b|ISHARES|SPDR|SELECT SECTOR|INVESCO QQQ|VANGUARD|\bTR\b|TRUST",
                                                        regex=True)]
    allh["cusip"] = allh["issuer"].map(clean_issuer)
    # Use share-driven actions only (exclude unchanged positions whose value moved with price).
    acts = allh[allh["change"].isin(["New", "Added", "Reduced", "Exited"])]
    g = acts.groupby("cusip").agg(issuer=("issuer", "first"), flow=("flow", "sum"),
                                  buyers=("change", lambda s: int(s.isin(["New", "Added"]).sum())),
                                  sellers=("change", lambda s: int(s.isin(["Reduced", "Exited"]).sum())),
                                  funds=("fund", lambda s: ", ".join(sorted(set(s)))[:90]))
    held = allh[allh["value"] > 0].groupby("cusip")["fund"].nunique().rename("held_by")
    g["issuer"] = g.index
    g = g.join(held).fillna({"held_by": 0})
    c1, c2 = st.columns(2, gap="large")
    for col, d, title, color in ((c1, g.nlargest(15, "flow"), "Most bought", UP), (c2, g.nsmallest(15, "flow"), "Most sold", DOWN)):
        with col:
            rows = [[_esc(clean_issuer(r.issuer)), colored(("+" if r.flow >= 0 else "−") + fmt_usd(abs(r.flow)), color),
                     f"{r.buyers}↑ {r.sellers}↓", f'<span class="dim">{_esc(r.funds)}</span>'] for r in d.itertuples()]
            table([title, "Position $ chg", "Funds", "Who"], rows, align="lrrw", empty_text="—")
    pop = g.nlargest(12, "held_by")
    note("Most widely held among tracked funds: " + ", ".join(
        f"{_esc(clean_issuer(r.issuer))} ({int(r.held_by)})" for r in pop.itertuples()), html=True)


def render():
    section("Institutional holdings (13F)", "Quarterly long positions filed with the SEC · up to 45 days delayed")
    name = st.selectbox("Fund", list(FUNDS), key="fund_sel")
    _single(name)
    divider()
    _consensus()
    st.caption("13F filings list US-listed long positions and options only. Shorts, cash, bonds and non-US holdings are "
               "not reported. Values are at quarter-end prices.")
