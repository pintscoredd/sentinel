"""Cross-asset analytics: stat-arb, RRG, vol, correlations, COT, sovereigns."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import streamlit as st

from sentinel.core.http import _yf_semaphore, get_yf_ticker, yf
from sentinel.data.market import _extract_ohlcv_frames

logger = logging.getLogger("sentinel.data")


@st.cache_data(ttl=3600)
def stat_arb_screener(pairs=None):
    """Statistical Arbitrage Screener using Engle-Granger Cointegration & OLS Half-Life."""
    try:
        import statsmodels.api as sm
        from statsmodels.tsa.stattools import coint
        import numpy as np
    except ImportError:
        return None
        
    if not pairs:
        pairs = [("GLD", "GDX"), ("XOM", "CVX"), ("JPM", "BAC"), ("QQQ", "XLK"), ("SPY", "TLT")]
    
    results = []
    end = datetime.today()
    start = end - timedelta(days=252)
    
    all_tickers = list(set([t for pair in pairs for t in pair]))
    try:
        with _yf_semaphore:
            bulk_raw = yf.download(
                all_tickers, start=start, end=end, progress=False,
                threads=True, auto_adjust=True, group_by="column",
            )
        # yfinance MultiIndex vs flat Close handling
        if isinstance(bulk_raw.columns, pd.MultiIndex):
            if "Close" in bulk_raw.columns.get_level_values(0):
                bulk_data = bulk_raw["Close"]
            else:
                bulk_data = bulk_raw.xs("Close", axis=1, level=0, drop_level=True)
        else:
            bulk_data = bulk_raw["Close"] if "Close" in bulk_raw.columns else bulk_raw
    except Exception as e:
        logger.error(f"stat_arb_screener bulk download failed: {e}")
        return None
    
    for t1, t2 in pairs:
        try:
            if isinstance(bulk_data, pd.DataFrame):
                if t1 not in bulk_data.columns or t2 not in bulk_data.columns:
                    continue
                stk1 = bulk_data[t1].dropna()
                stk2 = bulk_data[t2].dropna()
            else:
                continue
            
            df = pd.DataFrame({t1: stk1, t2: stk2}).dropna()
            if len(df) < 100:
                continue
            
            _, pvalue_fwd, _ = coint(df[t1], df[t2])
            _, pvalue_rev, _ = coint(df[t2], df[t1])
            
            if pvalue_fwd <= pvalue_rev:
                pvalue = pvalue_fwd
                dep, indep = t1, t2
                direction_label = f"{t1} ~ {t2}"
            else:
                pvalue = pvalue_rev
                dep, indep = t2, t1
                direction_label = f"{t2} ~ {t1}"
            
            Y = df[dep]
            X = sm.add_constant(df[indep])
            model = sm.OLS(Y, X).fit()
            beta = float(model.params.iloc[1])
            
            # Log-spread residual more stable across price scales than raw $
            spread = df[dep] - beta * df[indep]
            # Use robust MAD-based scale for z when available
            med = float(spread.median())
            mad = float((spread - med).abs().median())
            robust_std = 1.4826 * mad if mad > 1e-12 else float(spread.std())
            std_spread = robust_std if robust_std > 0 else float(spread.std())
            
            spread_lag = spread.shift(1).dropna()
            spread_diff = spread.diff().dropna()
            aligned = pd.concat([spread_diff, spread_lag], axis=1, join="inner").dropna()
            if len(aligned) < 30:
                continue
            lag_with_const = sm.add_constant(aligned.iloc[:, 1])
            ou_model = sm.OLS(aligned.iloc[:, 0], lag_with_const).fit()
            ou_intercept = float(ou_model.params.iloc[0])
            ou_lambda = -float(ou_model.params.iloc[1])
            half_life = (np.log(2) / ou_lambda) if ou_lambda > 1e-8 else float("inf")
            
            if ou_lambda > 1e-8:
                eq_mean = ou_intercept / ou_lambda
            else:
                eq_mean = med
            
            z_score = (float(spread.iloc[-1]) - eq_mean) / std_spread if std_spread > 0 else 0.0
            
            clamped_hl = max(3.0, min(float(half_life) if math.isfinite(half_life) else 60.0, 60.0))
            entry_thresh = 1.0 + (clamped_hl / 60.0) * 1.5
            lean_thresh = entry_thresh * 0.6
            
            signal = "Neutral"
            if z_score < -entry_thresh: signal = f"Long {dep} / Short {indep}"
            elif z_score > entry_thresh: signal = f"Short {dep} / Long {indep}"
            elif z_score < -lean_thresh: signal = f"Leaning Long {dep}"
            elif z_score > lean_thresh: signal = f"Leaning Short {dep}"
            
            results.append({
                "t1": t1, "t2": t2,
                "direction": direction_label,
                "pvalue": round(float(pvalue), 4),
                "zscore": round(float(z_score), 2),
                "half_life": round(float(half_life), 1) if math.isfinite(half_life) else 999.0,
                "beta": round(float(beta), 3),
                "coint": pvalue < 0.05,
                "signal": signal,
                "entry_thresh": round(entry_thresh, 2),
            })
        except Exception:
            continue
            
    if results:
        results.sort(key=lambda x: abs(x["zscore"]), reverse=True)
        return results
    return None


@st.cache_data(ttl=600, show_spinner=False)
def get_cross_asset_volatility():
    """CBOE implied-vol indices with their 6-month percentile rank."""
    if yf is None:
        return None
    labels = {"^VIX": "VIX · S&P 500", "^VXN": "VXN · Nasdaq-100", "^GVZ": "GVZ · Gold",
              "^OVX": "OVX · Crude oil", "^MOVE": "MOVE · Treasuries"}
    tickers = list(labels)
    try:
        with _yf_semaphore:
            data = yf.download(tickers, period="6mo", progress=False, threads=True, auto_adjust=True)
    except Exception as e:
        logger.error("Cross-asset vol fetch failed: %s", e)
        return None
    frames = _extract_ohlcv_frames(data, tickers)
    rows = []
    for t in tickers:
        frame = frames.get(t)
        if frame is None or "Close" not in frame:
            continue
        close = frame["Close"].dropna()
        if len(close) < 20:
            continue
        cur, prev = float(close.iloc[-1]), float(close.iloc[-2])
        rank = float((close < cur).mean() * 100)
        rows.append({
            "ticker": t, "label": labels[t], "current": cur, "change_pct": (cur / prev - 1) * 100 if prev else 0.0,
            "percentile": rank, "regime": "LOW" if rank < 25 else ("ELEVATED" if rank >= 75 else "NORMAL"),
        })
    return rows or None


@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_correlation_matrix(lookback_days=60):
    """Pearson + Spearman correlation of daily moves across 7 macro assets.

    All series come from one download so they share a date index (mixing a
    tz-aware Ticker.history index with yf.download's naive index silently
    produced all-NaN SPY/TLT columns). Yields use daily changes in points,
    prices use percent returns.
    """
    if yf is None:
        return None
    labels = {"SPY": "S&P 500", "TLT": "Bonds 20Y", "GLD": "Gold", "USO": "Oil",
              "UUP": "Dollar", "^TNX": "10Y Yield", "HYG": "HY Credit"}
    tickers = list(labels)
    try:
        with _yf_semaphore:
            data = yf.download(tickers, period="6mo", progress=False, threads=True, auto_adjust=True)
    except Exception as e:
        logger.error("Correlation download failed: %s", e)
        return None
    frames = _extract_ohlcv_frames(data, tickers)
    closes = pd.DataFrame({t: frames[t]["Close"] for t in tickers if t in frames and "Close" in frames[t]})
    if closes.empty:
        return None
    closes = closes.ffill(limit=2)
    moves = pd.DataFrame({
        t: (closes[t].diff() if t == "^TNX" else closes[t].pct_change()) for t in closes.columns
    }).dropna(how="any").tail(lookback_days)
    if len(moves) < 20:
        return None
    pearson = moves.corr(method="pearson")
    spearman = moves.corr(method="spearman")
    names = [labels.get(t, t) for t in pearson.columns]
    pearson.index = pearson.columns = names
    spearman.index = spearman.columns = names
    return {"pearson": pearson, "spearman": spearman, "labels": names, "lookback_days": len(moves)}


@st.cache_data(ttl=1800, show_spinner=False)
def get_sector_rrg(tail_weeks: int = 8):
    """Relative Rotation Graph inputs for SPDR sectors vs SPY (JdK-style approximation).

    RS-ratio  = 100 × (ETF/SPY) / its 50-day mean          (relative trend)
    RS-mom    = 100 + 10-day % change of RS-ratio            (rate of change of that trend)
    Tails are weekly (Friday) samples so the path shows rotation over time.
    """
    if yf is None:
        return None
    names = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health Care",
             "XLP": "Staples", "XLU": "Utilities", "XLY": "Discretionary", "XLB": "Materials",
             "XLC": "Communication", "XLRE": "Real Estate", "XLI": "Industrials"}
    tickers = list(names) + ["SPY"]
    try:
        with _yf_semaphore:
            data = yf.download(tickers, period="1y", progress=False, threads=True, auto_adjust=True)
    except Exception as e:
        logger.error("RRG download failed: %s", e)
        return None
    frames = _extract_ohlcv_frames(data, tickers)
    if "SPY" not in frames:
        return None
    spy = frames["SPY"]["Close"].dropna()
    rows = []
    for etf, sector in names.items():
        if etf not in frames:
            continue
        px = frames[etf]["Close"].dropna()
        both = pd.concat([px, spy], axis=1, join="inner").dropna()
        if len(both) < 80:
            continue
        rs = both.iloc[:, 0] / both.iloc[:, 1]
        ratio = (rs / rs.rolling(50).mean() * 100).dropna()
        mom = (ratio.pct_change(10) * 100 + 100).dropna()
        df = pd.concat([ratio.rename("r"), mom.rename("m")], axis=1).dropna()
        if df.empty:
            continue
        # Last observation of each week (the current week ends at today's value).
        weekly = df.groupby(df.index.to_period("W-FRI")).tail(1).tail(tail_weeks)
        r, m = float(df["r"].iloc[-1]), float(df["m"].iloc[-1])
        quadrant = ("LEADING" if r >= 100 and m >= 100 else "WEAKENING" if r >= 100
                    else "LAGGING" if m < 100 else "IMPROVING")
        prev = weekly.iloc[-2] if len(weekly) >= 2 else weekly.iloc[-1]
        rows.append({
            "etf": etf, "sector": sector, "rs_ratio": r, "rs_momentum": m, "quadrant": quadrant,
            "trail_ratio": [float(x) for x in weekly["r"]], "trail_momentum": [float(x) for x in weekly["m"]],
            "heading_deg": float(np.degrees(np.arctan2(m - prev["m"], r - prev["r"]))),
            "speed": float(np.hypot(r - prev["r"], m - prev["m"])),
            "perf_1m": float(px.iloc[-1] / px.iloc[-22] - 1) * 100 if len(px) > 22 else None,
            "rel_1m": float((px.iloc[-1] / px.iloc[-22]) / (spy.iloc[-1] / spy.iloc[-22]) - 1) * 100 if len(px) > 22 else None,
        })
    return rows or None

_COT_CONTRACTS = {
    "13874A": ("E-mini S&P 500", "ES"),
    "209742": ("Nasdaq-100 Mini", "NQ"),
    "088691": ("Gold", "GC"),
    "067651": ("WTI Crude", "CL"),
    "043602": ("10Y T-Note", "ZN"),
}


def _cot_field(row, *names):
    for n in names:
        v = row.get(n)
        if v not in (None, ""):
            return v
    return None


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_cot_positioning():
    """Net non-commercial (speculator) positioning from the CFTC legacy COT file.

    Free, keyless, published weekly (Friday, data as of Tuesday). Handles both
    the spaced ("CFTC Contract Market Code") and underscored header styles.
    """
    import csv
    import io
    import zipfile

    year = datetime.today().year
    for yr in (year, year - 1):
        try:
            resp = requests.get(f"https://www.cftc.gov/files/dea/history/deacot{yr}.zip",
                                timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                continue
            by_code: dict[str, list] = {}
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                name = next((n for n in z.namelist() if n.lower().endswith((".txt", ".csv"))), None)
                if not name:
                    continue
                with z.open(name) as f:
                    for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace")):
                        code = str(_cot_field(row, "CFTC Contract Market Code", "CFTC_Contract_Market_Code") or "").strip()
                        if code not in _COT_CONTRACTS:
                            continue
                        try:
                            lng = int(float(_cot_field(row, "Noncommercial Positions-Long (All)", "NonComm_Positions_Long_All") or 0))
                            sht = int(float(_cot_field(row, "Noncommercial Positions-Short (All)", "NonComm_Positions_Short_All") or 0))
                            oi = int(float(_cot_field(row, "Open Interest (All)", "Open_Interest_All") or 0))
                        except (TypeError, ValueError):
                            continue
                        date = str(_cot_field(row, "As of Date in Form YYYY-MM-DD", "Report_Date_as_YYYY-MM-DD") or "")
                        by_code.setdefault(code, []).append({"date": date, "long": lng, "short": sht, "oi": oi})
            results = []
            for code, (label, sym) in _COT_CONTRACTS.items():
                entries = sorted(by_code.get(code, []), key=lambda x: x["date"], reverse=True)
                if not entries:
                    continue
                cur = entries[0]
                net = cur["long"] - cur["short"]
                prev_net = (entries[1]["long"] - entries[1]["short"]) if len(entries) > 1 else net
                results.append({
                    "name": label, "symbol": sym, "net_noncomm": net, "net_change": net - prev_net,
                    "pct_oi": (net / cur["oi"] * 100) if cur["oi"] else None, "date": cur["date"],
                    "signal": "NET LONG" if net > 0 else ("NET SHORT" if net < 0 else "FLAT"),
                })
            if results:
                return results
        except Exception as e:
            logger.warning("CFTC COT %s failed: %s", yr, e)
    return None


# OECD long-term (10Y) government bond yields on FRED: monthly averages.
_SOVEREIGN_SERIES = [
    ("Germany", "DE", "IRLTLT01DEM156N"), ("France", "FR", "IRLTLT01FRM156N"),
    ("Italy", "IT", "IRLTLT01ITM156N"), ("Spain", "ES", "IRLTLT01ESM156N"),
    ("United Kingdom", "GB", "IRLTLT01GBM156N"), ("Japan", "JP", "IRLTLT01JPM156N"),
    ("Canada", "CA", "IRLTLT01CAM156N"), ("Australia", "AU", "IRLTLT01AUM156N"),
    ("Switzerland", "CH", "IRLTLT01CHM156N"), ("Mexico", "MX", "IRLTLT01MXM156N"),
]


@st.cache_data(ttl=3600, show_spinner=False)
def get_sovereign_10y_yields(fred_key=None):
    """10Y sovereign yields: US daily (^TNX) + OECD monthly averages via FRED."""
    import concurrent.futures
    from sentinel.data.macro import fred_series

    results = []
    try:
        tk = get_yf_ticker("^TNX")
        h = tk.history(period="10d") if tk is not None else None
        if h is not None and len(h) >= 2:
            c = h["Close"].dropna()
            results.append({"country": "United States", "flag": "US", "yield_pct": float(c.iloc[-1]),
                            "change": float(c.iloc[-1] - c.iloc[-2]), "as_of": c.index[-1].strftime("%Y-%m-%d"),
                            "freq": "daily"})
    except Exception as e:
        logger.debug("^TNX: %s", e)

    if fred_key:
        start = (pd.Timestamp.today() - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            fetched = list(pool.map(lambda it: (it, fred_series(it[2], fred_key, start=start)), _SOVEREIGN_SERIES))
        for (country, cc, _sid), df in fetched:
            if df is None or len(df) < 2:
                continue
            results.append({"country": country, "flag": cc, "yield_pct": float(df["value"].iloc[-1]),
                            "change": float(df["value"].iloc[-1] - df["value"].iloc[-2]),
                            "as_of": df["date"].iloc[-1].strftime("%Y-%m"), "freq": "monthly"})
    results.sort(key=lambda x: x["yield_pct"], reverse=True)
    return results
