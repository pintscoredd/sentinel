"""Institutional holdings from SEC 13F-HR filings (EDGAR, keyless).

Each quarter, managers with over $100M in US equities file a 13F listing their
long positions. Filings are due 45 days after quarter end, so they show where
a fund *was*, not where it is today.

The SEC asks automated clients to identify themselves with a contact email in
the User-Agent. Set SEC_CONTACT (an email) in secrets or the environment; the
default below is a generic placeholder.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import pandas as pd

from sentinel.core.cache import stale_cached_source
from sentinel.core.http import _get_http_session
from sentinel.core.secrets import get_secret

logger = logging.getLogger("sentinel.data")

# Well-known filers (CIK). Names come from EDGAR at runtime.
FUNDS = {
    "Berkshire Hathaway (Buffett)": 1067983,
    "Pershing Square (Ackman)": 1336528,
    "Scion Asset Management (Burry)": 1649339,
    "Bridgewater Associates (Dalio)": 1350694,
    "Renaissance Technologies": 1037389,
    "Citadel Advisors (Griffin)": 1423053,
    "Duquesne Family Office (Druckenmiller)": 1536411,
    "Appaloosa (Tepper)": 1656456,
    "Third Point (Loeb)": 1040273,
    "Baupost Group (Klarman)": 1061768,
    "Greenlight Capital (Einhorn)": 1079114,
    "Soros Fund Management": 1029160,
    "Tiger Global Management": 1167483,
    "Coatue Management": 1135730,
    "Viking Global Investors": 1103804,
    "Lone Pine Capital": 1061165,
    "Icahn Carl C": 921669,
    "ARK Investment Management (Wood)": 1697748,
}


def _ua() -> dict:
    contact = get_secret("SEC_CONTACT").get_secret_value() or "admin@sentinel-dashboard.dev"
    return {"User-Agent": f"Sentinel Dashboard {contact}", "Accept-Encoding": "gzip, deflate"}


def _get(url, as_json=True):
    r = _get_http_session().get(url, headers=_ua(), timeout=20)
    r.raise_for_status()
    return r.json() if as_json else r.text


@stale_cached_source(ttl=12 * 3600, retry_ttl=900)
def fund_filings(cik: int, n: int = 2) -> list[dict]:
    """Latest *n* original 13F-HR filings: accession, filed date, period of report."""
    try:
        d = _get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    except Exception as e:
        logger.warning("EDGAR submissions %s failed: %s", cik, e)
        return []
    r = (d.get("filings") or {}).get("recent") or {}
    out = []
    for i, form in enumerate(r.get("form", [])):
        if form == "13F-HR":
            out.append({"cik": int(cik), "name": d.get("name", ""), "accession": r["accessionNumber"][i],
                        "filed": r["filingDate"][i], "period": r["reportDate"][i]})
            if len(out) >= n:
                break
    return out


def _strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


@stale_cached_source(ttl=7 * 24 * 3600, retry_ttl=900)
def filing_holdings(cik: int, accession: str) -> pd.DataFrame:
    """Positions in one 13F filing, aggregated per issuer/CUSIP/class (value in $)."""
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
    try:
        items = _get(f"{base}/index.json")["directory"]["item"]
        xmls = [it["name"] for it in items if it["name"].lower().endswith(".xml") and "primary_doc" not in it["name"].lower()]
        if not xmls:
            return pd.DataFrame()
        # The information table is the largest XML in the filing.
        xmls.sort(key=lambda n: -int(next((it.get("size") or 0 for it in items if it["name"] == n), 0) or 0))
        root = ET.fromstring(_get(f"{base}/{xmls[0]}", as_json=False).encode())
    except Exception as e:
        logger.warning("13F holdings %s %s failed: %s", cik, accession, e)
        return pd.DataFrame()
    rows = []
    for node in root.iter():
        if _strip_ns(node.tag) != "infoTable":
            continue
        f = {}
        for child in node.iter():
            f[_strip_ns(child.tag)] = (child.text or "").strip()
        rows.append({
            "issuer": f.get("nameOfIssuer", ""), "cls": f.get("titleOfClass", ""), "cusip": f.get("cusip", ""),
            "value": pd.to_numeric(f.get("value"), errors="coerce"),
            "shares": pd.to_numeric(f.get("sshPrnamt"), errors="coerce"),
            "put_call": f.get("putCall", ""),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.groupby(["cusip", "put_call"], as_index=False).agg(
        issuer=("issuer", "first"), cls=("cls", "first"), value=("value", "sum"), shares=("shares", "sum"))
    return df.sort_values("value", ascending=False).reset_index(drop=True)


def _fix_units(cur: pd.DataFrame, prev: pd.DataFrame, filed: str):
    """Filings before 2023 report value in $ thousands; detect and normalise to dollars."""
    if cur.empty:
        return cur
    if filed < "2023-01-01":
        cur = cur.assign(value=cur["value"] * 1000)
    return cur


def fund_report(cik: int) -> dict:
    """Latest holdings with weights and quarter-over-quarter changes."""
    fl = fund_filings(cik, 2)
    if not fl:
        return {}
    cur = _fix_units(filing_holdings(cik, fl[0]["accession"]), None, fl[0]["filed"])
    if cur.empty:
        return {"filing": fl[0], "holdings": cur}
    prev = pd.DataFrame()
    if len(fl) > 1:
        prev = _fix_units(filing_holdings(cik, fl[1]["accession"]), None, fl[1]["filed"])
    total = cur["value"].sum()
    cur = cur.assign(weight=cur["value"] / total * 100 if total else 0.0)
    key = ["cusip", "put_call"]
    if not prev.empty:
        m = cur.merge(prev[key + ["shares", "value"]].rename(columns={"shares": "prev_shares", "value": "prev_value"}),
                      on=key, how="outer", indicator=True)
        m["issuer"] = m["issuer"].fillna(m["cusip"].map(prev.set_index("cusip")["issuer"].to_dict()))
        m[["value", "shares", "weight"]] = m[["value", "shares", "weight"]].fillna(0)
        m[["prev_value", "prev_shares"]] = m[["prev_value", "prev_shares"]].fillna(0)

        def change(r):
            if r["_merge"] == "left_only":
                return "New"
            if r["_merge"] == "right_only":
                return "Exited"
            if r["prev_shares"] and abs(r["shares"] / r["prev_shares"] - 1) < 0.005:
                return "Unchanged"
            return "Added" if r["shares"] > r["prev_shares"] else "Reduced"

        m["change"] = m.apply(change, axis=1)
        m["share_chg_pct"] = ((m["shares"] / m["prev_shares"] - 1) * 100).where(m["prev_shares"] > 0)
        cur = m.drop(columns="_merge").sort_values("value", ascending=False).reset_index(drop=True)
    else:
        cur = cur.assign(change="", share_chg_pct=float("nan"), prev_value=0.0, prev_shares=0.0)
    return {
        "filing": fl[0], "previous": fl[1] if len(fl) > 1 else None, "holdings": cur,
        "total": float(total), "positions": int((cur["value"] > 0).sum()),
        "prev_total": float(prev["value"].sum()) if not prev.empty else None,
    }


def clean_issuer(name: str) -> str:
    return re.sub(r"\s+(INC|CORP|CO|LTD|PLC|HLDGS?|GROUP|COM|NEW|DEL|CL [A-Z])\.?$", "", str(name).strip(), flags=re.I).title()
