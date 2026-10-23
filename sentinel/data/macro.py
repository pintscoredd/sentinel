"""Macro data: rates, calendar, liquidity, curve.

FRED is the primary source. Without a FRED key, `fred_series` falls back to keyless
official feeds for the series they cover: Treasury.gov (constant-maturity yields),
BLS (CPI, core CPI, unemployment, payrolls) and the NY Fed (effective fed funds).
"""
from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd
import streamlit as st

from sentinel.core.http import (
    _fetch_robust_json, _get_http_session, get_yf_ticker,
)
from sentinel.core.secrets import unwrap_secret as _unwrap_secret

from sentinel.config import DEFAULT_RISK_FREE_RATE
from sentinel.core.secrets import get_secret

logger = logging.getLogger("sentinel.data")


@st.cache_data(ttl=3600, show_spinner=False)
def fred_series(series_id, key, limit=36, start=None):
    """Observations for a FRED series (ascending by date), or None.

    *limit* counts observations; pass *start* ("YYYY-MM-DD") for a date window
    instead, since daily and monthly series need very different counts.
    """
    key = _unwrap_secret(key)
    if not key:
        df = _keyless_series(series_id, start)
        if df is None or df.empty:
            return None
        return df if start else df.tail(int(limit)).reset_index(drop=True)
    params = {"series_id": series_id, "api_key": key, "file_type": "json", "sort_order": "desc"}
    if start:
        params["observation_start"] = start
    else:
        params["limit"] = int(limit)
    data = _fetch_robust_json("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=10)
    if not data:
        return None
    df = pd.DataFrame(data.get("observations", []))
    if df.empty or "value" not in df:
        return None
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # FRED uses "." for missing
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["value"]).sort_values("date")[["date", "value"]].reset_index(drop=True)
    return df if not df.empty else None


# ── Keyless fallbacks ──────────────────────────────────────────────────────────
_TREASURY_COLS = {"DGS1MO": "1 Mo", "DGS3MO": "3 Mo", "DGS6MO": "6 Mo", "DGS1": "1 Yr", "DGS2": "2 Yr",
                  "DGS3": "3 Yr", "DGS5": "5 Yr", "DGS7": "7 Yr", "DGS10": "10 Yr", "DGS20": "20 Yr", "DGS30": "30 Yr"}
# FRED id → BLS id (seasonally adjusted where FRED's is).
_BLS_IDS = {"CPIAUCSL": "CUSR0000SA0", "CPILFESL": "CUSR0000SA0L1E", "UNRATE": "LNS14000000", "PAYEMS": "CES0000000001"}
_UA = {"User-Agent": "Mozilla/5.0 (Sentinel market dashboard)"}


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def treasury_curve_year(year: int):
    """Daily Treasury par yield curve for one calendar year (Treasury.gov CSV, keyless)."""
    url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
           f"{int(year)}/all?type=daily_treasury_yield_curve&field_tdr_date_value={int(year)}&page&_format=csv")
    try:
        r = _get_http_session().get(url, headers=_UA, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
    except Exception as e:
        logger.warning("Treasury curve %s failed: %s", year, e)
        return None
    if "Date" not in df:
        return None
    df["date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _bls_bundle(start_year: int):
    """All mapped BLS series in one request (the keyless API allows ~25 requests/day per IP)."""
    try:
        r = _get_http_session().post("https://api.bls.gov/publicAPI/v1/timeseries/data/", headers=_UA, timeout=20,
                                     json={"seriesid": list(_BLS_IDS.values()), "startyear": str(start_year),
                                           "endyear": str(date.today().year)})
        data = r.json()
    except Exception as e:
        logger.warning("BLS request failed: %s", e)
        return {}
    if data.get("status") != "REQUEST_SUCCEEDED":
        logger.warning("BLS: %s", data.get("message"))
        return {}
    out = {}
    for ser in (data.get("Results") or {}).get("series", []):
        rows = [(pd.Timestamp(int(o["year"]), int(o["period"][1:]), 1), pd.to_numeric(o["value"], errors="coerce"))
                for o in ser.get("data", []) if str(o.get("period", "")).startswith("M") and o["period"] != "M13"]
        if rows:
            out[ser["seriesID"]] = pd.DataFrame(rows, columns=["date", "value"]).dropna().sort_values("date")
    return out


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def _nyfed_effr():
    start = (date.today().replace(year=date.today().year - 6)).isoformat()
    data = _fetch_robust_json("https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json",
                              params={"startDate": start, "endDate": date.today().isoformat()}, timeout=15)
    rows = [(pd.Timestamp(x["effectiveDate"]), x.get("percentRate")) for x in (data or {}).get("refRates", [])]
    if not rows:
        return None
    return pd.DataFrame(rows, columns=["date", "value"]).dropna().sort_values("date").reset_index(drop=True)


def _keyless_series(series_id, start=None):
    start_ts = pd.Timestamp(start) if start else pd.Timestamp.today() - pd.Timedelta(days=800)
    df = None
    if series_id in _TREASURY_COLS:
        col = _TREASURY_COLS[series_id]
        frames = [treasury_curve_year(y) for y in range(start_ts.year, date.today().year + 1)]
        frames = [f for f in frames if f is not None and col in f]
        if frames:
            df = pd.concat([f[["date", col]] for f in frames]).rename(columns={col: "value"})
    elif series_id in _BLS_IDS:
        # Ask for 12 extra months so year-over-year changes have a base.
        df = _bls_bundle(min(start_ts.year - 1, date.today().year - 2)).get(_BLS_IDS[series_id])
    elif series_id in ("DFF", "FEDFUNDS"):
        df = _nyfed_effr()
        if df is not None and series_id == "FEDFUNDS":
            df = df.set_index("date")["value"].resample("MS").mean().dropna().reset_index()
    if df is None or df.empty:
        return None
    df = df.copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna().drop_duplicates("date").sort_values("date")
    return df[df["date"] >= start_ts - pd.DateOffset(months=13 if series_id in _BLS_IDS else 0)].reset_index(drop=True)


@st.cache_data(ttl=3600)
def get_risk_free_rate(fred_key=None):
    """Fetch current 3-month T-bill rate as risk-free proxy.
    
    Cached for 1 hour — the 3-month T-bill rate doesn't change frequently.
    H9 fix: was called multiple times per options scoring without caching.
    """
    fred_key = _unwrap_secret(fred_key)
    if fred_key:
        df = fred_series("DTB3", fred_key, 5)
        if df is not None and not df.empty:
            return round(df["value"].iloc[-1] / 100, 4)
    try:
        tk = get_yf_ticker("^IRX")
        if tk is not None:
            h = tk.history(period="5d")
            if h is not None and not h.empty:
                return round(float(h["Close"].iloc[-1]) / 100, 4)
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    return DEFAULT_RISK_FREE_RATE


@st.cache_data(ttl=3600)
def get_macro_overview(fred_key):
    """Fetch macro economic indicators.
    
    M2 fix: Parallelized FRED API calls with ThreadPoolExecutor(max_workers=5)
    to reduce latency from sequential 9-call waterfall to ~2 parallel batches.
    """
    if not fred_key: return None
    import concurrent.futures
    
    SERIES = {
        "cpi": ("CPIAUCSL", 24),
        "pce": ("PCEPILFE", 24),
        "unemp": ("UNRATE", 6),
        "dgs2": ("DGS2", 3),
        "dgs10": ("DGS10", 3),
        "fedfunds": ("FEDFUNDS", 6),
        "hy": ("BAMLH0A0HYM2", 6),
        "m2": ("M2SL", 18),
        "gdp": ("GDPC1", 12),
    }
    
    raw = {}
    def _fetch(key_info):
        key, (series_id, months) = key_info
        try:
            return key, fred_series(series_id, fred_key, months)
        except Exception:
            return key, None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for key, df in pool.map(_fetch, SERIES.items()):
            raw[key] = df
    
    signals = {}
    
    try:
        df_cpi = raw.get("cpi")
        if df_cpi is not None and len(df_cpi) >= 13:
            cpi_yoy = round((df_cpi["value"].iloc[-1] / df_cpi["value"].iloc[-13] - 1) * 100, 2)
            if cpi_yoy < 2.5: cpi_score, cpi_label, cpi_color = 2, f"Cooling ({cpi_yoy:.1f}%)", "#3FCF8E"
            elif cpi_yoy < 3.5: cpi_score, cpi_label, cpi_color = 1, f"Elevated ({cpi_yoy:.1f}%)", "#BDBDBD"
            elif cpi_yoy < 5.0: cpi_score, cpi_label, cpi_color = -1, f"High ({cpi_yoy:.1f}%)", "#F2555A"
            else: cpi_score, cpi_label, cpi_color = -2, f"Very High ({cpi_yoy:.1f}%)", "#F2555A"
            signals["CPI Inflation"] = {"score": cpi_score, "label": cpi_label, "color": cpi_color, "val": cpi_yoy}
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    try:
        df_pce = raw.get("pce")
        if df_pce is not None and len(df_pce) >= 13:
            pce_yoy = round((df_pce["value"].iloc[-1] / df_pce["value"].iloc[-13] - 1) * 100, 2)
            if pce_yoy < 2.5: pce_score, pce_label, pce_color = 2, f"Near Target ({pce_yoy:.1f}%)", "#3FCF8E"
            elif pce_yoy < 3.0: pce_score, pce_label, pce_color = 1, f"Slightly Elevated ({pce_yoy:.1f}%)", "#BDBDBD"
            else: pce_score, pce_label, pce_color = -1, f"Above Target ({pce_yoy:.1f}%)", "#F2555A"
            signals["Core PCE"] = {"score": pce_score, "label": pce_label, "color": pce_color, "val": pce_yoy}
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    try:
        df_unemp = raw.get("unemp")
        if df_unemp is not None and not df_unemp.empty:
            urate = df_unemp["value"].iloc[-1]
            trend = "↑" if urate > (df_unemp["value"].iloc[-2] if len(df_unemp) > 1 else urate) else "↓"
            if urate < 4.0: u_score, u_label, u_color = 2, f"Full Employment ({urate:.1f}% {trend})", "#3FCF8E"
            elif urate < 4.5: u_score, u_label, u_color = 1, f"Near Full Emp. ({urate:.1f}% {trend})", "#BDBDBD"
            elif urate < 5.5: u_score, u_label, u_color = -1, f"Rising ({urate:.1f}% {trend})", "#F2555A"
            else: u_score, u_label, u_color = -2, f"High Unemployment ({urate:.1f}% {trend})", "#F2555A"
            signals["Unemployment"] = {"score": u_score, "label": u_label, "color": u_color, "val": urate}
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    try:
        df_2y, df_10y = raw.get("dgs2"), raw.get("dgs10")
        if df_2y is not None and df_10y is not None and not df_2y.empty and not df_10y.empty:
            spread = round(df_10y["value"].iloc[-1] - df_2y["value"].iloc[-1], 2)
            if spread > 0.5: yc_score, yc_label, yc_color = 2, f"Steep (+{spread:.2f}% — Growth)", "#3FCF8E"
            elif spread > 0: yc_score, yc_label, yc_color = 1, f"Flat (+{spread:.2f}%)", "#BDBDBD"
            elif spread > -0.5: yc_score, yc_label, yc_color = -1, f"Inverted ({spread:.2f}%)", "#F2555A"
            else: yc_score, yc_label, yc_color = -2, f"Deep Inversion ({spread:.2f}%)", "#F2555A"
            signals["Yield Curve (10-2Y)"] = {"score": yc_score, "label": yc_label, "color": yc_color, "val": spread}
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    try:
        df_ff = raw.get("fedfunds")
        if df_ff is not None and not df_ff.empty:
            ffr = df_ff["value"].iloc[-1]
            prev_ffr = df_ff["value"].iloc[-2] if len(df_ff) > 1 else ffr
            ff_trend = "cutting" if ffr < prev_ffr else ("hiking" if ffr > prev_ffr else "hold")
            if ff_trend == "cutting" and ffr < 4.0: ff_score, ff_label, ff_color = 2, f"Easing ({ffr:.2f}% — {ff_trend.upper()})", "#3FCF8E"
            elif ff_trend == "cutting": ff_score, ff_label, ff_color = 1, f"Beginning Cuts ({ffr:.2f}%)", "#BDBDBD"
            elif ff_trend == "hiking": ff_score, ff_label, ff_color = -1, f"Tightening ({ffr:.2f}% — {ff_trend.upper()})", "#F2555A"
            elif ffr > 5.0: ff_score, ff_label, ff_color = -1, f"Restrictive ({ffr:.2f}% — HOLD)", "#F2555A"
            else: ff_score, ff_label, ff_color = 1, f"Neutral ({ffr:.2f}% — HOLD)", "#BDBDBD"
            signals["Fed Funds Rate"] = {"score": ff_score, "label": ff_label, "color": ff_color, "val": ffr}
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    try:
        df_hy = raw.get("hy")
        if df_hy is not None and not df_hy.empty:
            hy = df_hy["value"].iloc[-1]
            hy_trend = "↑" if hy > (df_hy["value"].iloc[-2] if len(df_hy) > 1 else hy) else "↓"
            if hy < 3.5: hy_score, hy_label, hy_color = 2, f"Tight ({hy:.2f}% {hy_trend} — Risk-On)", "#3FCF8E"
            elif hy < 4.5: hy_score, hy_label, hy_color = 1, f"Normal ({hy:.2f}% {hy_trend})", "#BDBDBD"
            elif hy < 6.0: hy_score, hy_label, hy_color = -1, f"Wide ({hy:.2f}% {hy_trend} — Stress)", "#F2555A"
            else: hy_score, hy_label, hy_color = -2, f"Very Wide ({hy:.2f}% {hy_trend} — Crisis)", "#F2555A"
            signals["HY Credit Spread"] = {"score": hy_score, "label": hy_label, "color": hy_color, "val": hy}
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    try:
        df_m2 = raw.get("m2")
        if df_m2 is not None and len(df_m2) >= 13:
            m2_yoy = round((df_m2["value"].iloc[-1] / df_m2["value"].iloc[-13] - 1) * 100, 2)
            if m2_yoy > 5: m2_score, m2_label, m2_color = -1, f"Expanding Rapidly ({m2_yoy:+.1f}% YoY)", "#F2555A"
            elif m2_yoy > 0: m2_score, m2_label, m2_color = 1, f"Modest Growth ({m2_yoy:+.1f}% YoY)", "#BDBDBD"
            else: m2_score, m2_label, m2_color = 2, f"Contracting ({m2_yoy:+.1f}% YoY)", "#3FCF8E"
            signals["M2 Money Supply"] = {"score": m2_score, "label": m2_label, "color": m2_color, "val": m2_yoy}
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    try:
        df_gdp = raw.get("gdp")
        if df_gdp is not None and len(df_gdp) >= 5:
            latest_gdp, prev_gdp, year_ago_gdp = df_gdp["value"].iloc[-1], df_gdp["value"].iloc[-2], df_gdp["value"].iloc[-5]
            gdp_yoy, gdp_q = round((latest_gdp / year_ago_gdp - 1) * 100, 2), round((latest_gdp / prev_gdp - 1) * 4 * 100, 2)
            if gdp_yoy >= 3.0: gdp_score, gdp_label, gdp_color = 2, f"Strong ({gdp_yoy:.1f}% YoY, {gdp_q:+.1f}% ann.)", "#3FCF8E"
            elif gdp_yoy >= 2.0: gdp_score, gdp_label, gdp_color = 1, f"Moderate ({gdp_yoy:.1f}% YoY)", "#BDBDBD"
            elif gdp_yoy >= 0.5: gdp_score, gdp_label, gdp_color = -1, f"Slowing ({gdp_yoy:.1f}% YoY)", "#F2555A"
            else: gdp_score, gdp_label, gdp_color = -2, f"Contraction ({gdp_yoy:.1f}% YoY)", "#F2555A"
            signals["GDP Growth"] = {"score": gdp_score, "label": gdp_label, "color": gdp_color, "val": gdp_yoy}
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    total_score = sum(s["score"] for s in signals.values())
    max_score = len(signals) * 2
    pct = (total_score / max_score * 100) if max_score else 0

    if pct >= 50:   env_label, env_color, env_desc = "EXPANSIONARY", "#3FCF8E", "Macro conditions are broadly supportive. Risk-on bias."
    elif pct >= 10: env_label, env_color, env_desc = "MIXED / NEUTRAL", "#BDBDBD", "Macro signals are mixed. Selective positioning warranted."
    elif pct >= -30: env_label, env_color, env_desc = "CAUTIONARY", "#D4D4D4", "More headwinds than tailwinds. Elevated inflation or tightening financial conditions."
    else:            env_label, env_color, env_desc = "CONTRACTIONARY", "#F2555A", "Multiple macro red flags. Elevated recession risk."

    return {"signals": signals, "total_score": total_score, "max_score": max_score, "pct": pct, "env_label": env_label, "env_color": env_color, "env_desc": env_desc}


_FRED_RELEASES_HIGH = ("consumer price index", "employment situation", "gross domestic product",
                       "personal income and outlays", "fomc")
_FRED_RELEASES_MED = ("producer price index", "retail", "industrial production", "new residential construction",
                      "unemployment insurance weekly claims", "job openings", "adp national employment",
                      "international trade in goods", "surveys of consumers", "durable")

# Second (decision) day of each scheduled FOMC meeting, per federalreserve.gov.
FOMC_DECISIONS = [
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]


@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_calendar(fred_key=None, days_back=0, finnhub_key=None):
    """Upcoming US macro releases.

    Source order: Finnhub economic calendar (has actual/forecast; needs a key),
    FRED release dates (needs a FRED key), then a rule-of-thumb schedule marked
    ``source="est."`` so the UI can label it as an estimate.
    """
    from datetime import date as _date, timedelta as _td
    import calendar as _cal
    today = _date.today()
    start_date = today - _td(days=days_back)
    horizon = today + _td(days=45)
    results = []

    fk = _unwrap_secret(finnhub_key) or get_secret("FINNHUB_API_KEY").get_secret_value()
    if fk:
        data = _fetch_robust_json(
            "https://finnhub.io/api/v1/calendar/economic",
            params={"from": start_date.isoformat(), "to": horizon.isoformat(), "token": fk}, timeout=12,
        )
        HIGH_KW = ["cpi", "fomc", "fed interest rate", "nonfarm", "non-farm", "payroll", "gdp", "pce", "employment situation"]
        MED_KW = ["ppi", "retail sales", "ism", "pmi", "housing starts", "durable goods", "jolts", "adp", "jobless",
                  "consumer confidence", "industrial production", "trade balance", "michigan"]
        for ev in (data or {}).get("economicCalendar", []) or []:
            if str(ev.get("country", "US")).upper() not in ("US", "USA", ""):
                continue
            name = (ev.get("event") or "").strip()
            if not name:
                continue
            nl, impact = name.lower(), str(ev.get("impact") or "").upper()
            is_high = impact == "HIGH" or any(kw in nl for kw in HIGH_KW)
            is_med = impact == "MEDIUM" or any(kw in nl for kw in MED_KW)
            if not (is_high or is_med):
                continue
            try:
                ev_date = _date.fromisoformat(str(ev.get("time") or "")[:10])
            except ValueError:
                continue
            if not (start_date <= ev_date <= horizon):
                continue

            def _s(v):
                return "" if v is None else str(v)

            results.append({
                "date": ev_date, "name": name, "importance": "HIGH" if is_high else "MEDIUM",
                "actual": _s(ev.get("actual")), "forecast": _s(ev.get("estimate")), "previous": _s(ev.get("prev")),
                "unit": _s(ev.get("unit")), "source": "Finnhub",
            })
        if results:
            results.sort(key=lambda x: x["date"])
            return results[:40]

    fred_key = _unwrap_secret(fred_key)
    if fred_key:
        data = _fetch_robust_json(
            "https://api.stlouisfed.org/fred/releases/dates",
            params={"api_key": fred_key, "file_type": "json", "realtime_start": start_date.isoformat(),
                    "realtime_end": horizon.isoformat(), "limit": 1000, "sort_order": "asc",
                    "include_release_dates_with_no_data": "true"},
            timeout=12,
        )
        seen = set()
        for rel in (data or {}).get("release_dates", []) or []:
            name = str(rel.get("release_name", ""))
            nl = name.lower()
            imp = "HIGH" if any(k in nl for k in _FRED_RELEASES_HIGH) else (
                "MEDIUM" if any(k in nl for k in _FRED_RELEASES_MED) else None)
            if not imp:
                continue
            try:
                d = _date.fromisoformat(str(rel.get("date", ""))[:10])
            except ValueError:
                continue
            if start_date <= d <= horizon and (d, name) not in seen:
                seen.add((d, name))
                results.append({"date": d, "name": name, "importance": imp, "actual": "", "forecast": "",
                                "previous": "", "unit": "", "source": "FRED"})
        if results:
            results.sort(key=lambda x: x["date"])
            return results[:40]

    def _nth_weekday(year, month, n, weekday):
        count = 0
        for day in range(1, _cal.monthrange(year, month)[1] + 1):
            if _date(year, month, day).weekday() == weekday:
                count += 1
                if count == n:
                    return _date(year, month, day)
        return None

    def _last_weekday(year, month, weekday):
        last = None
        for day in range(1, _cal.monthrange(year, month)[1] + 1):
            if _date(year, month, day).weekday() == weekday:
                last = _date(year, month, day)
        return last

    static = []
    for dm in range(0, 3):
        m = ((today.month - 1 + dm) % 12) + 1
        y = today.year + ((today.month - 1 + dm) // 12)
        static += [
            ("Employment Situation (Jobs Report)", _nth_weekday(y, m, 1, 4), "HIGH"),
            ("Consumer Price Index (CPI)", _nth_weekday(y, m, 2, 2), "HIGH"),
            ("Producer Price Index (PPI)", _nth_weekday(y, m, 2, 3), "MEDIUM"),
            ("Retail Sales", _nth_weekday(y, m, 2, 4), "MEDIUM"),
            ("Personal Income & Outlays (PCE)", _last_weekday(y, m, 4), "HIGH"),
            ("GDP", _last_weekday(y, m, 3), "HIGH") if m in (1, 4, 7, 10) else (None, None, None),
        ]
    for fd in FOMC_DECISIONS:
        static.append(("FOMC Rate Decision", _date.fromisoformat(fd), "HIGH"))
    seen = set()
    for name, d, imp in static:
        if not name or not d or (d, name) in seen or not (today <= d <= horizon):
            continue
        seen.add((d, name))
        results.append({"date": d, "name": name, "importance": imp, "actual": "", "forecast": "",
                        "previous": "", "unit": "", "source": "est."})
    results.sort(key=lambda x: x["date"])
    return results[:40]


@st.cache_data(ttl=3600)
def get_net_liquidity(fred_key, lookback=365):
    """Calculate Net Liquidity = WALCL - WTREGEN - RRPONTSYD from FRED.
    
    WALCL: Fed Total Assets (Millions)
    WTREGEN: Treasury General Account (Millions)
    RRPONTSYD: Reverse Repo (Billions → converted to Millions)
    """
    if not fred_key:
        return None
    try:
        start = (pd.Timestamp.today() - pd.Timedelta(days=int(lookback * 2))).strftime("%Y-%m-%d")
        walcl = fred_series("WALCL", fred_key, start=start)
        wtregen = fred_series("WTREGEN", fred_key, start=start)
        rrp = fred_series("RRPONTSYD", fred_key, start=start)

        if walcl is None or wtregen is None or rrp is None:
            return None
        if walcl.empty or wtregen.empty or rrp.empty:
            return None

        walcl = walcl.set_index("date").resample("W-WED")["value"].last().ffill()
        wtregen = wtregen.set_index("date").resample("W-WED")["value"].last().ffill()
        rrp = rrp.set_index("date").resample("W-WED")["value"].last().ffill() * 1000

        df = pd.DataFrame({
            "WALCL": walcl,
            "TGA": wtregen,
            "RRP": rrp,
        }).dropna()

        if df.empty:
            return None

        df["Net_Liquidity"] = df["WALCL"] - df["TGA"] - df["RRP"]
        df["Net_Liquidity_T"] = df["Net_Liquidity"] / 1e6
        df = df.reset_index().rename(columns={"date": "Date"})
        return df
    except Exception as e:
        logger.error("Net liquidity calculation error: %s", e)
        return None


_YIELD_MATURITIES = [
    ("DGS1MO", "1M"), ("DGS3MO", "3M"), ("DGS6MO", "6M"),
    ("DGS1", "1Y"), ("DGS2", "2Y"), ("DGS3", "3Y"),
    ("DGS5", "5Y"), ("DGS7", "7Y"), ("DGS10", "10Y"),
    ("DGS20", "20Y"), ("DGS30", "30Y"),
]


@st.cache_data(ttl=3600)
def get_yield_curve_history(fred_key, lookback_weeks=52):
    """Fetch yield curve data across all maturities for 3D surface/animation.
    
    Returns DataFrame with columns: Date, Maturity, Yield, Maturity_Num
    """
    try:
        all_data = {}
        for series_id, label in _YIELD_MATURITIES:
            df = fred_series(series_id, fred_key, start=(pd.Timestamp.today() - pd.Timedelta(weeks=lookback_weeks + 2)).strftime("%Y-%m-%d"))
            if df is not None and not df.empty:
                s = df.set_index("date")["value"]
                all_data[label] = s

        if len(all_data) < 5:
            return None

        combined = pd.DataFrame(all_data).dropna(how="all")
        combined = combined.ffill()

        combined = combined.resample("W-FRI").last().dropna(how="all")

        maturity_map = {"1M": 1/12, "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2,
                        "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30}

        rows = []
        for date_idx, row in combined.iterrows():
            for mat_label, val in row.items():
                if pd.notna(val):
                    rows.append({
                        "Date": date_idx,
                        "Maturity": mat_label,
                        "Yield": float(val),
                        "Maturity_Num": maturity_map.get(mat_label, 0),
                    })

        return pd.DataFrame(rows) if rows else None
    except Exception as e:
        logger.error("Yield curve history fetch failed: %s", {"error": str(e)})
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_economic_surprise_index(finnhub_key=None):
    """Recent US releases vs consensus (Finnhub calendar actual vs estimate).

    Each surprise is (actual − forecast) / |forecast|, clipped to ±50% so a
    0.1 vs 0.2 print cannot dominate the average. Positive = data came in above
    consensus (stronger growth or hotter inflation — not "good" or "bad").
    """
    fk = _unwrap_secret(finnhub_key) or get_secret("FINNHUB_API_KEY").get_secret_value()
    if not fk:
        return {"items": [], "_no_key": True}
    cal = get_macro_calendar(None, days_back=45, finnhub_key=fk)
    items = []
    for ev in cal or []:
        if ev.get("source") != "Finnhub":
            continue
        try:
            actual = float(str(ev.get("actual", "")).replace("%", "").replace(",", "").strip())
            forecast = float(str(ev.get("forecast", "")).replace("%", "").replace(",", "").strip())
        except ValueError:
            continue
        if abs(forecast) < 1e-9:
            continue
        surprise = max(-50.0, min(50.0, (actual - forecast) / abs(forecast) * 100))
        items.append({"name": ev.get("name", ""), "date": str(ev.get("date", "")), "actual": actual,
                      "forecast": forecast, "unit": ev.get("unit", ""), "surprise_pct": round(surprise, 1),
                      "importance": ev.get("importance")})
    if not items:
        return None
    items.sort(key=lambda x: x["date"], reverse=True)
    pool = [i for i in items if i["importance"] == "HIGH"] or items
    avg = sum(i["surprise_pct"] for i in pool) / len(pool)
    above = sum(1 for i in pool if i["surprise_pct"] > 0)
    label = "ABOVE CONSENSUS" if avg > 2 else ("BELOW CONSENSUS" if avg < -2 else "IN LINE")
    return {"items": items[:12], "avg_surprise_pct": round(avg, 1), "label": label,
            "above": above, "count": len(pool)}


_CB_SERIES = [
    ("Federal Reserve", "US", "DFEDTARU", "Upper bound of target range"),
    ("European Central Bank", "EU", "ECBDFR", "Deposit facility rate"),
    ("Bank of England", "GB", "IUDSOIA", "SONIA (tracks Bank Rate)"),
    ("Bank of Japan", "JP", "IRSTCB01JPM156N", "OECD policy-rate series (monthly)"),
    ("Bank of Canada", "CA", "IRSTCB01CAM156N", "OECD policy-rate series (monthly)"),
    ("Reserve Bank of Australia", "AU", "IRSTCB01AUM156N", "OECD policy-rate series (monthly)"),
    ("Swiss National Bank", "CH", "IRSTCB01CHM156N", "OECD policy-rate series (monthly)"),
]


@st.cache_data(ttl=3600, show_spinner=False)
def get_central_bank_rates(fred_key=None):
    """Policy rates from FRED with the 6-month change and the observation date.

    No hard-coded fallbacks: a series that cannot be fetched is omitted rather
    than shown with a stale guess.
    """
    import concurrent.futures
    fred_key = _unwrap_secret(fred_key)
    if not fred_key:
        return []
    start = (pd.Timestamp.today() - pd.Timedelta(days=400)).strftime("%Y-%m-%d")

    def _fetch(item):
        return item, fred_series(item[2], fred_key, start=start)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for (name, cc, sid, desc), df in pool.map(_fetch, _CB_SERIES):
            if df is None or df.empty:
                continue
            last = df.iloc[-1]
            ref = df[df["date"] <= last["date"] - pd.Timedelta(days=182)]
            prev = float(ref["value"].iloc[-1]) if not ref.empty else float(df["value"].iloc[0])
            rate = float(last["value"])
            chg = rate - prev
            stance = "EASING" if chg <= -0.1 else ("TIGHTENING" if chg >= 0.1 else "ON HOLD")
            age_days = (pd.Timestamp.today().normalize() - last["date"]).days
            results.append({"name": name, "flag": cc, "rate": rate, "change": chg, "stance": stance,
                            "as_of": last["date"].strftime("%Y-%m-%d"), "stale": age_days > 75,
                            "series": sid, "desc": desc})
    results.sort(key=lambda x: x["rate"], reverse=True)
    return results


@st.cache_data(ttl=1800, show_spinner=False)
def get_yield_curve_inversions(fred_key=None):
    """Key Treasury spreads (constant-maturity yields, same observation date)."""
    SPREADS = [
        ("10Y − 2Y", "DGS10", "DGS2", "Classic recession indicator"),
        ("10Y − 3M", "DGS10", "DGS3MO", "NY Fed recession-probability model input"),
        ("30Y − 10Y", "DGS30", "DGS10", "Long-end term premium"),
        ("5Y − 2Y", "DGS5", "DGS2", "Belly vs front end"),
        ("10Y − 1Y", "DGS10", "DGS1", "Near-term vs long-term outlook"),
        ("30Y − 2Y", "DGS30", "DGS2", "Full curve slope"),
    ]
    import concurrent.futures
    fred_key = _unwrap_secret(fred_key)  # keyless: Treasury.gov via fred_series
    ids = sorted({x for _, a, b, _ in SPREADS for x in (a, b)})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        raw = dict(pool.map(lambda sid: (sid, fred_series(sid, fred_key, 10)), ids))
    results = []
    for label, long_id, short_id, desc in SPREADS:
        dl, ds = raw.get(long_id), raw.get(short_id)
        if dl is None or ds is None:
            continue
        both = dl.merge(ds, on="date", suffixes=("_l", "_s")).dropna()
        if both.empty:
            continue
        row = both.iloc[-1]
        spread = float(row["value_l"] - row["value_s"])
        inverted = spread < 0
        results.append({
            "label": label, "long_rate": float(row["value_l"]), "short_rate": float(row["value_s"]),
            "spread": spread, "inverted": inverted,
            "status": "INVERTED" if inverted else ("FLAT" if abs(spread) < 0.10 else "NORMAL"),
            "as_of": row["date"].strftime("%Y-%m-%d"), "description": desc,
        })
    return results
