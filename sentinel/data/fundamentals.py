"""Company fundamentals, earnings, insiders, short interest."""
from __future__ import annotations

import logging
import math
from datetime import datetime

import pandas as pd
import streamlit as st

from sentinel.core.http import (
    _fetch_robust_json, get_yf_ticker, yf,
)
from sentinel.core.formatting import _safe_float, _safe_int
from sentinel.core.secrets import unwrap_secret as _unwrap_secret

logger = logging.getLogger("sentinel.data")


@st.cache_data(ttl=21600, show_spinner=False)
def get_finra_short_volume(ticker):
    """Short interest snapshot from Yahoo (exchange-reported, ~bi-monthly).

    Returns short % of float, shares short, days to cover — any may be None.
    """
    try:
        t = get_yf_ticker(ticker)
        info = (t.info or {}) if t is not None else {}
    except Exception as e:
        logger.debug("short interest %s: %s", ticker, e)
        return None
    pct = _safe_float(info.get("shortPercentOfFloat"), None)
    shares = _safe_float(info.get("sharesShort"), None)
    dtc = _safe_float(info.get("shortRatio"), None)
    if pct is None and shares is None:
        return None
    return {
        "short_pct_float": round(pct * 100, 2) if pct is not None else None,
        "short_shares": int(shares) if shares is not None else None,
        "days_to_cover": round(dtc, 1) if dtc is not None else None,
    }


@st.cache_data(ttl=600)
def finnhub_insider(ticker, key):
    key = _unwrap_secret(key)
    if not key:
        return []
    try:
        data = _fetch_robust_json("https://finnhub.io/api/v1/stock/insider-transactions",
            params={"symbol": ticker, "token": key}, timeout=10)
        if not data:
            return []
        return (data.get("data", []) or [])[:15]
    except Exception as exc:
        logger.debug(f"finnhub_insider {ticker}: {exc}")
        return []


@st.cache_data(ttl=600)
def smart_money_conviction_buys(insider_data, officer_roles=None):
    """Filter insider transactions to surface high-conviction open market purchases.
    
    Algorithmic filter:
    1. Filter OUT TransactionCode == 'M' (Options exercises) and 'F' (Tax withholding)
       as well as 'G' (Gift), 'A' (Award), 'X' (Exercise), 'D' (Disposal)
    2. Isolate TransactionCode == 'P' (Open market purchases) — the strongest signal
    3. Score each purchase based on: dollar value, role seniority, and cluster timing
    4. Aggregate by company to create a "Conviction Buy" ranking
    
    Returns list of dicts sorted by conviction_score descending.
    """
    if not insider_data:
        return []
    
    if officer_roles is None:
        officer_roles = {}
    
    _CSUITE_KEYWORDS = [
        "CEO", "CFO", "COO", "CTO", "CIO", "CHIEF", "PRESIDENT",
        "CHAIRMAN", "VICE CHAIR", "DIRECTOR", "EVP", "SVP",
        "GENERAL COUNSEL", "TREASURER", "CONTROLLER",
    ]
    
    def _is_csuite(name, role_map):
        """Check if insider is a C-suite or senior executive."""
        name_upper = str(name).upper().strip()
        role = role_map.get(name_upper, "")
        if not role:
            parts = name_upper.replace(",", "").replace(".", "").split()
            if len(parts) >= 2:
                role = role_map.get(" ".join(parts[:2]), "")
                if not role:
                    role = role_map.get(parts[-1] + " " + parts[0], "")
                if not role:
                    for k, v in role_map.items():
                        if len(parts) >= 2 and parts[0] in k and parts[-1] in k:
                            role = v
                            break
        role_upper = str(role).upper()
        return any(kw in role_upper for kw in _CSUITE_KEYWORDS), role
    
    purchases = []
    for tx in insider_data:
        code = str(tx.get("transactionCode", "") or "").upper()
        if code != "P":
            continue
        
        change = _safe_int(tx.get("change", 0))
        if change <= 0:
            continue
        
        name = str(tx.get("name", "Unknown"))
        date_str = str(tx.get("transactionDate", ""))[:10]
        price = _safe_float(tx.get("transactionPrice", 0))
        shares_owned = _safe_int(tx.get("share", 0))
        
        dollar_value = change * price if price > 0 else 0
        
        is_senior, role = _is_csuite(name, officer_roles)
        
        score = 0
        if dollar_value >= 1_000_000:
            score += 5
        elif dollar_value >= 500_000:
            score += 4
        elif dollar_value >= 100_000:
            score += 3
        elif dollar_value >= 50_000:
            score += 2
        elif dollar_value >= 10_000:
            score += 1
        
        if is_senior:
            score += 3
        
        purchases.append({
            "name": name,
            "role": role if role else "Insider",
            "is_csuite": is_senior,
            "date": date_str,
            "shares": change,
            "price": price,
            "dollar_value": dollar_value,
            "shares_owned": shares_owned,
            "score": score,
            "ticker": str(tx.get("symbol", "")).upper(),
        })
    
    purchases.sort(key=lambda x: (x["score"], x["dollar_value"]), reverse=True)
    
    return purchases


@st.cache_data(ttl=1800)
def finnhub_officers(ticker, key):
    role_map = {}
    key = _unwrap_secret(key)
    if key:
        try:
            data = _fetch_robust_json("https://finnhub.io/api/v1/stock/executive",
                params={"symbol": ticker, "token": key}, timeout=10)
            if not data:
                data = {}
            for o in data.get("executive", []) or []:
                name = str(o.get("name", "")).strip()
                title = str(o.get("position", "") or o.get("title", "") or "")
                if not name or not title: continue
                name_upper = name.upper()
                role_map[name_upper] = title
                parts = name.split()
                if len(parts) >= 2:
                    last_first = (parts[-1] + " " + " ".join(parts[:-1])).upper()
                    role_map[last_first] = title
                    role_map[(parts[-1] + " " + parts[0]).upper()] = title
        except Exception as exc:
            logger.debug(f"finnhub_officers API: {exc}")

    try:
        tk = get_yf_ticker(ticker)
        if tk:
            try:
                idf = tk.insider_transactions if hasattr(tk, "insider_transactions") else None
                if idf is None and hasattr(tk, "get_insider_transactions"):
                    idf = tk.get_insider_transactions()
                if idf is not None and not idf.empty:
                    if 'Insider' in idf.columns and 'Position' in idf.columns:
                        for _, row in idf.iterrows():
                            ins_name = str(row['Insider']).strip().upper()
                            pos = str(row['Position']).strip()
                            if ins_name and pos and ins_name not in role_map:
                                role_map[ins_name] = pos
                rh = tk.get_insider_roster_holders() if hasattr(tk, "get_insider_roster_holders") else None
                if rh is not None and not rh.empty and 'Name' in rh.columns and 'Position' in rh.columns:
                    for _, row in rh.iterrows():
                        ins_name = str(row['Name']).strip().upper()
                        pos = str(row['Position']).strip()
                        if ins_name and pos and ins_name not in role_map:
                            role_map[ins_name] = pos
            except Exception as exc:
                logger.debug(f"finnhub_officers yf insider_transactions: {exc}")

            _generic = {"Officer", "Director", "officer", "director", ""}
            officers = tk.info.get("companyOfficers", [])
            for o in officers:
                name = str(o.get("name", "")).strip()
                title = str(o.get("title", "")).strip()
                if not name or not title: continue
                clean_name = name.upper().replace(".", "").replace(",", "")
                for pfx in ["MR ", "MS ", "MRS ", "DR ", "PROF "]:
                    if clean_name.startswith(pfx):
                        clean_name = clean_name[len(pfx):].strip()
                if clean_name not in role_map or role_map.get(clean_name) in _generic:
                    role_map[clean_name] = title
                parts = clean_name.split()
                if len(parts) >= 2:
                    last_first_all = parts[-1] + " " + " ".join(parts[:-1])
                    last_first = parts[-1] + " " + parts[0]
                    for variant in (last_first_all, last_first):
                        if variant not in role_map or role_map.get(variant) in _generic:
                            role_map[variant] = title
    except Exception as exc:
        logger.debug(f"finnhub_officers yf info: {exc}")

    return role_map


EARNINGS_UNIVERSE = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "GOOGL": "Alphabet", "AMZN": "Amazon",
    "META": "Meta Platforms", "TSLA": "Tesla", "AVGO": "Broadcom", "JPM": "JPMorgan Chase",
    "GS": "Goldman Sachs", "BAC": "Bank of America", "NFLX": "Netflix", "AMD": "AMD", "INTC": "Intel",
    "CRM": "Salesforce", "ORCL": "Oracle", "V": "Visa", "MA": "Mastercard", "WMT": "Walmart",
    "COST": "Costco", "XOM": "Exxon Mobil", "CVX": "Chevron", "UNH": "UnitedHealth", "JNJ": "Johnson & Johnson",
    "PFE": "Pfizer", "ABBV": "AbbVie", "LLY": "Eli Lilly", "BRK-B": "Berkshire Hathaway", "HD": "Home Depot",
    "DIS": "Disney", "PLTR": "Palantir", "SNOW": "Snowflake", "ADBE": "Adobe", "QCOM": "Qualcomm",
}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_earnings_calendar(today_str=None, extra=()):
    """Next earnings date + EPS estimate for large caps (and *extra* tickers)."""
    import concurrent.futures
    names = dict(EARNINGS_UNIVERSE)
    for t in extra or ():
        names.setdefault(str(t).upper(), str(t).upper())

    def _fetch_single(tkr):
        try:
            t = get_yf_ticker(tkr)
            cal = t.calendar if t is not None else None
        except Exception as exc:
            logger.debug("earnings calendar %s: %s", tkr, exc)
            return None
        ed = eps = None
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            ed = ed[0] if isinstance(ed, (list, tuple)) and ed else (None if isinstance(ed, (list, tuple)) else ed)
            eps = cal.get("Earnings Average", cal.get("EPS Estimate"))
        elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
            ed = cal.loc["Earnings Date"].iloc[0]
            eps = cal.loc["EPS Estimate"].iloc[0] if "EPS Estimate" in cal.index else None
        if ed is None:
            return None
        try:
            d = pd.to_datetime(ed).date()
        except Exception:
            return None
        return {"Ticker": tkr, "Company": names.get(tkr, tkr), "EarningsDate": d,
                "EPS Est": _safe_float(eps, None)}

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for r in pool.map(_fetch_single, list(names)):
            if r:
                rows.append(r)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["EarningsDate", "Ticker"]).reset_index(drop=True)


@st.cache_data(ttl=1800)
def get_full_financials(ticker):
    if yf is None: return {}
    try:
        t = get_yf_ticker(ticker)
        if t is None: return {}
        
        income, cashflow, balance = None, None, None
        for attr in ["quarterly_financials", "quarterly_income_stmt"]:
            try:
                val = getattr(t, attr, None)
                if val is not None and not val.empty:
                    income = val; break
            except Exception: pass
        for attr in ["quarterly_cashflow", "quarterly_cash_flow"]:
            try:
                val = getattr(t, attr, None)
                if val is not None and not val.empty:
                    cashflow = val; break
            except Exception: pass
        for attr in ["quarterly_balance_sheet", "quarterly_balancesheet"]:
            try:
                val = getattr(t, attr, None)
                if val is not None and not val.empty:
                    balance = val; break
            except Exception: pass

        if income is None or income.empty: return {}

        quarters = list(income.columns[:4])
        results = {}

        for q in quarters:
            q_str = str(q)[:10]
            row = {}

            def _get(df, *keys):
                for k in keys:
                    if df is not None and not df.empty and k in df.index and q in df.columns:
                        v = df.loc[k, q]
                        if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))): return float(v)
                return None

            row["revenue"]    = _get(income, "Total Revenue", "Revenue")
            row["gross_profit"]= _get(income, "Gross Profit")
            row["op_income"]  = _get(income, "Operating Income", "EBIT", "Operating Income Or Loss")
            row["net_income"] = _get(income, "Net Income", "Net Income Common Stockholders")
            row["ebitda"]     = _get(income, "EBITDA", "Normalized EBITDA", "Reconciled Ebitda")
            row["eps"]        = _get(income, "Diluted EPS", "Basic EPS", "Basic Continuous Operations")
            row["int_expense"]= _get(income, "Interest Expense", "Interest Expense Non Operating")
            row["free_cashflow"] = _get(cashflow, "Free Cash Flow")
            row["op_cashflow"]   = _get(cashflow, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
            row["capex"]         = _get(cashflow, "Capital Expenditure", "Purchase Of Ppe")
            row["total_debt"]    = _get(balance, "Total Debt", "Long Term Debt And Capital Lease Obligation")
            row["cash"]          = _get(balance, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash And Short Term Investments")

            if row["revenue"] and row["revenue"] > 0:
                if row["gross_profit"] is not None: row["gross_margin"] = row["gross_profit"] / row["revenue"] * 100
                if row["op_income"] is not None: row["op_margin"] = row["op_income"] / row["revenue"] * 100
                if row["net_income"] is not None: row["net_margin"] = row["net_income"] / row["revenue"] * 100

            results[q_str] = row
        return results
    except Exception as e:
        logger.debug(f"get_full_financials error: {e}")
        return {}


@st.cache_data(ttl=1800)
def get_earnings_matrix(ticker):
    """Build Bloomberg-style Earnings Matrix data for a ticker.

    Pulls from multiple yfinance sources for maximum data coverage:
      1) t.earnings_dates  — reported EPS actual + estimate for 12+ quarters
      2) t.quarterly_financials — Diluted EPS from income statement
      3) t.earnings  — annual/quarterly dicts (legacy API, older history)

    Returns dict with:
        - quarterly: {year: {q_label: eps_value}}
        - estimates: {year: {q_label: eps_estimate}}
        - surprise_pct: {year: {q_label: surprise_%}}
        - beats: {year: {q_label: True/False/None}}
        - revenue_q: {year: {q_label: revenue_value}}
        - annual: {year: total_eps}
        - annual_revenue: {year: total_revenue}
        - yoy_growth: {year: {q_label: pct_growth}}
        - annual_growth: {year: pct_growth}
        - rev_growth: {year: {q_label: pct_growth}}
        - annual_rev_growth: {year: pct_growth}
        - valuations: {metric: {period: value}}
        - fiscal_end_month: int (1-12)
        - currency: str
        - years: sorted list of years
        - q_labels: ordered list of quarter labels
        - streak: int (consecutive beats, negative = misses)
        - beat_rate: float (% of quarters that beat)
    """
    if yf is None:
        return None
    try:
        t = get_yf_ticker(ticker)
        if t is None:
            return None
        info = t.info or {}

        fiscal_end_month = info.get("fiscalYearEnd") or info.get("lastFiscalYearEnd")
        if isinstance(fiscal_end_month, str):
            _month_map = {"january": 1, "february": 2, "march": 3, "april": 4,
                          "may": 5, "june": 6, "july": 7, "august": 8,
                          "september": 9, "october": 10, "november": 11, "december": 12}
            fiscal_end_month = _month_map.get(fiscal_end_month.lower(), 12)
        elif isinstance(fiscal_end_month, (int, float)):
            v = int(fiscal_end_month)
            if 1 <= v <= 12:
                fiscal_end_month = v
            elif 101 <= v <= 1231:
                m = v // 100
                fiscal_end_month = m if 1 <= m <= 12 else 12
            elif v > 1_000_000_000:
                try:
                    fiscal_end_month = datetime.utcfromtimestamp(v).month
                except (OverflowError, OSError, ValueError):
                    fiscal_end_month = 12
            else:
                fiscal_end_month = 12
        elif hasattr(fiscal_end_month, "month"):
            fiscal_end_month = int(fiscal_end_month.month)
        else:
            fiscal_end_month = 12

        import calendar
        _q_month_labels = {}
        for qi in range(4):
            m = ((fiscal_end_month - 3 * (3 - qi)) % 12) or 12
            _q_month_labels[m] = f"Q{qi+1} {calendar.month_abbr[m]}"
        q_labels = [f"Q{qi+1} {calendar.month_abbr[((fiscal_end_month - 3*(3-qi)) % 12) or 12]}" for qi in range(4)]

        def _month_to_qlabel(month):
            """Map a calendar month to the nearest fiscal quarter label."""
            if month in _q_month_labels:
                return _q_month_labels[month]
            best_m = min(_q_month_labels.keys(), key=lambda m: min(abs(m - month), 12 - abs(m - month)))
            return _q_month_labels[best_m]

        def _fiscal_year(month, year):
            """Determine fiscal year from calendar month/year."""
            return year if month <= fiscal_end_month else year + 1

        def _report_period(dt):
            """(month, year) of the fiscal quarter a report date covers.

            Earnings are reported weeks after the quarter closes, so a late-January
            report belongs to the December quarter of the prior year — mapping the
            report month directly put it in the wrong quarter and fiscal year.
            """
            cutoff = (dt - pd.Timedelta(days=7)).normalize()
            y, m = cutoff.year, cutoff.month
            for _ in range(13):
                if m in _q_month_labels:
                    qe = pd.Timestamp(year=y, month=m, day=calendar.monthrange(y, m)[1])
                    if qe.tz_localize(None) <= cutoff.tz_localize(None):
                        return m, y
                m -= 1
                if m == 0:
                    m, y = 12, y - 1
            return dt.month, dt.year

        quarterly = {}
        estimates = {}
        surprise_pct = {}
        beats = {}
        revenue_q = {}

        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                for idx, row in ed.iterrows():
                    dt = pd.to_datetime(idx)
                    if dt.tzinfo is not None:
                        dt = dt.tz_convert(None)
                    month, year = _report_period(dt)
                    ql = _month_to_qlabel(month)
                    fy = _fiscal_year(month, year)

                    actual = row.get("Reported EPS")
                    if actual is not None and not (isinstance(actual, float) and math.isnan(actual)):
                        actual = round(float(actual), 2)
                        if fy not in quarterly:
                            quarterly[fy] = {}
                        quarterly[fy][ql] = actual

                    est = row.get("EPS Estimate")
                    if est is not None and not (isinstance(est, float) and math.isnan(est)):
                        est = round(float(est), 2)
                        if fy not in estimates:
                            estimates[fy] = {}
                        estimates[fy][ql] = est

                    surp = row.get("Surprise(%)")
                    if surp is not None and not (isinstance(surp, float) and math.isnan(surp)):
                        if fy not in surprise_pct:
                            surprise_pct[fy] = {}
                        surprise_pct[fy][ql] = round(float(surp), 1)

                    if actual is not None and est is not None:
                        if fy not in beats:
                            beats[fy] = {}
                        beats[fy][ql] = actual >= est
        except Exception as e:
            logger.debug(f"Error caught: {e}")
        _income_sources = []
        try:
            _qf = t.quarterly_financials
            if _qf is not None and not _qf.empty:
                _income_sources.append(_qf)
        except Exception:
            pass
        try:
            _qi = t.quarterly_income_stmt
            if _qi is not None and not _qi.empty:
                _income_sources.append(_qi)
        except Exception:
            pass

        for income in _income_sources:
            try:
                for col in income.columns:
                    dt = pd.to_datetime(col)
                    month, year = dt.month, dt.year
                    ql = _month_to_qlabel(month)
                    fy = _fiscal_year(month, year)

                    if fy not in quarterly or ql not in quarterly.get(fy, {}):
                        for key in ["Diluted EPS", "Basic EPS", "Basic Continuous Operations"]:
                            if key in income.index:
                                v = income.loc[key, col]
                                if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                                    if fy not in quarterly:
                                        quarterly[fy] = {}
                                    quarterly[fy][ql] = round(float(v), 2)
                                    break

                    if fy not in revenue_q or ql not in revenue_q.get(fy, {}):
                        for key in ["Total Revenue", "Revenue", "Operating Revenue", "Net Revenue"]:
                            if key in income.index:
                                v = income.loc[key, col]
                                if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                                    if fy not in revenue_q:
                                        revenue_q[fy] = {}
                                    revenue_q[fy][ql] = float(v)
                                    break
            except Exception as e:
                logger.debug(f"Error caught: {e}")
        try:
            earnings_obj = t.earnings
            if isinstance(earnings_obj, dict):
                for qe in earnings_obj.get("quarterly", []):
                    try:
                        dt = pd.to_datetime(qe.get("date"))
                        month, year = dt.month, dt.year
                        ql = _month_to_qlabel(month)
                        fy = _fiscal_year(month, year)
                        actual = qe.get("actual")
                        if actual is not None and not math.isnan(float(actual)):
                            if fy not in quarterly:
                                quarterly[fy] = {}
                            if ql not in quarterly[fy]:
                                quarterly[fy][ql] = round(float(actual), 2)
                        est = qe.get("estimate")
                        if est is not None and not math.isnan(float(est)):
                            if fy not in estimates:
                                estimates[fy] = {}
                            if ql not in estimates[fy]:
                                estimates[fy][ql] = round(float(est), 2)
                        if actual is not None and est is not None:
                            a_, e_ = float(actual), float(est)
                            if not math.isnan(a_) and not math.isnan(e_):
                                if fy not in beats:
                                    beats[fy] = {}
                                if ql not in beats[fy]:
                                    beats[fy][ql] = a_ >= e_
                                if fy not in surprise_pct:
                                    surprise_pct[fy] = {}
                                if ql not in surprise_pct[fy] and e_ != 0:
                                    surprise_pct[fy][ql] = round((a_ - e_) / abs(e_) * 100, 1)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Error caught: {e}")
        try:
            qe_df = t.quarterly_earnings
            if qe_df is not None and not qe_df.empty:
                for idx, row in qe_df.iterrows():
                    dt = pd.to_datetime(idx)
                    month, year = dt.month, dt.year
                    ql = _month_to_qlabel(month)
                    fy = _fiscal_year(month, year)
                    rev = row.get("Revenue")
                    if rev is not None and not (isinstance(rev, float) and math.isnan(rev)):
                        if fy not in revenue_q:
                            revenue_q[fy] = {}
                        if ql not in revenue_q[fy]:
                            revenue_q[fy][ql] = float(rev)
                    eps = row.get("Earnings")
                    if eps is not None and not (isinstance(eps, float) and math.isnan(eps)):
                        if fy not in quarterly:
                            quarterly[fy] = {}
                        if ql not in quarterly[fy]:
                            quarterly[fy][ql] = round(float(eps), 2)
        except Exception as e:
            logger.debug(f"Error caught: {e}")
        if not quarterly:
            return None

        years = sorted(quarterly.keys())

        annual = {}
        annual_revenue = {}
        for yr in years:
            vals = [v for v in quarterly.get(yr, {}).values() if v is not None]
            if vals:
                annual[yr] = round(sum(vals), 2)
            rev_vals = [v for v in revenue_q.get(yr, {}).values() if v is not None]
            if rev_vals:
                annual_revenue[yr] = sum(rev_vals)

        yoy_growth = {}
        annual_growth = {}
        for yr in years:
            yoy_growth[yr] = {}
            for ql in q_labels:
                cur = quarterly.get(yr, {}).get(ql)
                prev = quarterly.get(yr - 1, {}).get(ql)
                if cur is not None and prev is not None and prev != 0:
                    yoy_growth[yr][ql] = round((cur - prev) / abs(prev) * 100, 1)
            cur_ann = annual.get(yr)
            prev_ann = annual.get(yr - 1)
            if cur_ann is not None and prev_ann is not None and prev_ann != 0:
                annual_growth[yr] = round((cur_ann - prev_ann) / abs(prev_ann) * 100, 1)

        rev_growth = {}
        annual_rev_growth = {}
        for yr in years:
            rev_growth[yr] = {}
            for ql in q_labels:
                cur = revenue_q.get(yr, {}).get(ql)
                prev = revenue_q.get(yr - 1, {}).get(ql)
                if cur is not None and prev is not None and prev != 0:
                    rev_growth[yr][ql] = round((cur - prev) / abs(prev) * 100, 1)
            cur_rev = annual_revenue.get(yr)
            prev_rev = annual_revenue.get(yr - 1)
            if cur_rev is not None and prev_rev is not None and prev_rev != 0:
                annual_rev_growth[yr] = round((cur_rev - prev_rev) / abs(prev_rev) * 100, 1)

        beat_list = []
        for yr in sorted(quarterly.keys()):
            for ql in q_labels:
                b = beats.get(yr, {}).get(ql)
                if b is not None:
                    beat_list.append(b)
        streak = 0
        if beat_list:
            direction = beat_list[-1]
            for b in reversed(beat_list):
                if b == direction:
                    streak += 1 if direction else -1
                else:
                    break
            if not direction:
                streak = -abs(streak)
        beat_rate = round(sum(1 for b in beat_list if b) / len(beat_list) * 100, 0) if beat_list else 0

        for yr in years:
            for ql in q_labels:
                act = quarterly.get(yr, {}).get(ql)
                est = estimates.get(yr, {}).get(ql)
                if act is not None and est is not None and est != 0:
                    if yr not in surprise_pct:
                        surprise_pct[yr] = {}
                    if ql not in surprise_pct[yr]:
                        surprise_pct[yr][ql] = round((act - est) / abs(est) * 100, 1)
                    if yr not in beats:
                        beats[yr] = {}
                    if ql not in beats[yr]:
                        beats[yr][ql] = act >= est

        valuations = {}
        price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"), 0)
        if price > 0:
            trailing_pe = _safe_float(info.get("trailingPE"), 0)
            forward_pe = _safe_float(info.get("forwardPE"), 0)
            trailing_ps = _safe_float(info.get("priceToSalesTrailing12Months"), 0)
            pb = _safe_float(info.get("priceToBook"), 0)
            opcf = _safe_float(info.get("operatingCashflow"), 0)
            shares = _safe_float(info.get("sharesOutstanding"), 0)
            pcf = round(price / (opcf / shares), 1) if opcf > 0 and shares > 0 else 0
            ev_ebitda = _safe_float(info.get("enterpriseToEbitda"), 0)
            forward_eps = _safe_float(info.get("forwardEps"), 0)
            fwd_pe_calc = round(price / forward_eps, 1) if forward_eps > 0 else 0

            valuations = {
                "P/E": {
                    "Last 4Q": f"{trailing_pe:.1f}x" if trailing_pe > 0 else "—",
                    "Forward": f"{fwd_pe_calc:.1f}x" if fwd_pe_calc > 0 else (f"{forward_pe:.1f}x" if forward_pe > 0 else "—"),
                },
                "EV/EBITDA": {
                    "Last 4Q": f"{ev_ebitda:.1f}x" if ev_ebitda > 0 else "—",
                    "Forward": "—",
                },
                "P/S": {
                    "Last 4Q": f"{trailing_ps:.1f}x" if trailing_ps > 0 else "—",
                    "Forward": "—",
                },
                "P/B": {
                    "Last 4Q": f"{pb:.1f}x" if pb > 0 else "—",
                    "Forward": "—",
                },
                "P/CF": {
                    "Last 4Q": f"{pcf:.1f}x" if pcf > 0 else "—",
                    "Forward": "—",
                },
            }

        currency = info.get("currency", "USD")

        analyst_targets = []
        try:
            ud = t.upgrades_downgrades
            if ud is not None and not ud.empty:
                ud = ud.reset_index().sort_values("GradeDate", ascending=False)
                ud = ud.drop_duplicates(subset=["Firm"])
                ud = ud[ud["currentPriceTarget"].notna() & (ud["currentPriceTarget"] > 0)]
                
                track_record_firms = ["B of A Securities", "Bank of America", "Needham", "TD Cowen", "Cowen & Co.", "RBC Capital", "Oppenheimer"]
                best_targets = []
                other_targets = []
                
                for _, row in ud.iterrows():
                    firm = row["Firm"]
                    pt = float(row["currentPriceTarget"])
                    action = row.get("ToGrade", "") or row.get("Action", "")
                    if pd.isna(action): action = ""
                    else: action = str(action)
                    
                    obj = {"firm": firm, "target": pt, "action": action[:20]}
                    if firm in track_record_firms:
                        best_targets.append(obj)
                    else:
                        other_targets.append(obj)
                        
                analyst_targets = (best_targets + other_targets)[:5]
        except Exception as e:
            logger.debug(f"Error caught: {e}")

        analyst_ratings = {}
        try:
            rec_key = info.get("recommendationKey", "") or ""
            num_analysts = _safe_int(info.get("numberOfAnalystOpinions"), 0)
            target_mean   = _safe_float(info.get("targetMeanPrice"), 0)
            target_median = _safe_float(info.get("targetMedianPrice"), 0)
            target_low    = _safe_float(info.get("targetLowPrice"), 0)
            target_high   = _safe_float(info.get("targetHighPrice"), 0)

            strong_buy = buy = hold = sell = strong_sell = 0
            try:
                rs = t.recommendations_summary
                if rs is not None and not rs.empty:
                    latest = rs.iloc[0]
                    strong_buy  = int(latest.get("strongBuy",  0) or 0)
                    buy         = int(latest.get("buy",        0) or 0)
                    hold        = int(latest.get("hold",       0) or 0)
                    sell        = int(latest.get("sell",       0) or 0)
                    strong_sell = int(latest.get("strongSell", 0) or 0)
            except Exception:
                pass

            if (strong_buy + buy + hold + sell + strong_sell) == 0:
                try:
                    ud2 = t.upgrades_downgrades
                    if ud2 is not None and not ud2.empty:
                        ud2 = ud2.reset_index()
                        cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
                        ud2 = ud2[pd.to_datetime(ud2["GradeDate"]) >= cutoff]
                        grade_map = {
                            "Strong Buy": "strong_buy", "Buy": "buy", "Outperform": "buy",
                            "Overweight": "buy", "Positive": "buy",
                            "Hold": "hold", "Neutral": "hold", "Market Perform": "hold",
                            "Equal-Weight": "hold", "In-Line": "hold",
                            "Underperform": "sell", "Underweight": "sell",
                            "Negative": "sell", "Sell": "sell",
                            "Strong Sell": "strong_sell",
                        }
                        for _, row in ud2.iterrows():
                            g = str(row.get("ToGrade", "") or "")
                            bucket = grade_map.get(g)
                            if bucket == "strong_buy":  strong_buy  += 1
                            elif bucket == "buy":       buy         += 1
                            elif bucket == "hold":      hold        += 1
                            elif bucket == "sell":      sell        += 1
                            elif bucket == "strong_sell": strong_sell += 1
                except Exception:
                    pass

            total_rated = strong_buy + buy + hold + sell + strong_sell
            if total_rated == 0 and num_analysts > 0:
                pass

            _consensus_label = rec_key.replace("_", " ").title() if rec_key else ""
            if not _consensus_label:
                bullish = strong_buy + buy
                bearish = sell + strong_sell
                if total_rated > 0:
                    if bullish / total_rated >= 0.60:   _consensus_label = "Buy"
                    elif bearish / total_rated >= 0.40: _consensus_label = "Sell"
                    else:                               _consensus_label = "Hold"

            analyst_ratings = {
                "consensus":     _consensus_label or "—",
                "num_analysts":  num_analysts or total_rated,
                "strong_buy":    strong_buy,
                "buy":           buy,
                "hold":          hold,
                "sell":          sell,
                "strong_sell":   strong_sell,
                "total_rated":   total_rated,
                "target_mean":   target_mean,
                "target_median": target_median,
                "target_low":    target_low,
                "target_high":   target_high,
            }
        except Exception as e:
            logger.debug(f"Analyst ratings error: {e}")

        return {
            "quarterly": quarterly,
            "estimates": estimates,
            "surprise_pct": surprise_pct,
            "beats": beats,
            "revenue_q": revenue_q,
            "annual": annual,
            "annual_revenue": annual_revenue,
            "yoy_growth": yoy_growth,
            "annual_growth": annual_growth,
            "rev_growth": rev_growth,
            "annual_rev_growth": annual_rev_growth,
            "valuations": valuations,
            "fiscal_end_month": fiscal_end_month,
            "currency": currency,
            "years": years,
            "q_labels": q_labels,
            "price": price,
            "company": info.get("shortName", ticker),
            "streak": streak,
            "beat_rate": beat_rate,
            "forward_eps": _safe_float(info.get("forwardEps"), 0),
            "trailing_eps": _safe_float(info.get("trailingEps"), 0),
            "market_cap": _safe_float(info.get("marketCap"), 0),
            "analyst_targets": analyst_targets,
            "analyst_ratings": analyst_ratings,
        }
    except Exception as e:
        logger.error("Earnings Matrix Error: %s", e)
        return None


@st.cache_data(ttl=600)
def get_profitability_metrics(ticker):
    """Fetch profitability ratios: gross margin, operating margin, EBITDA margin, net margin, ROA, ROE."""
    try:
        tk = get_yf_ticker(ticker)
        if tk is None:
            return None
        info = {}
        try:
            info = tk.info
            if not isinstance(info, dict):
                info = {}
        except Exception:
            pass

        gross_margin = info.get("grossMargins")
        op_margin = info.get("operatingMargins")
        ebitda_margin = info.get("ebitdaMargins")
        net_margin = info.get("profitMargins")
        roa = info.get("returnOnAssets")
        roe = info.get("returnOnEquity")

        if gross_margin is None or op_margin is None:
            try:
                inc = None
                for attr in ["quarterly_income_stmt", "quarterly_financials"]:
                    val = getattr(tk, attr, None)
                    if val is not None and not val.empty:
                        inc = val
                        break
                if inc is not None and not inc.empty:
                    q = inc.columns[0]
                    rev = None
                    for k in ["Total Revenue", "Revenue"]:
                        if k in inc.index:
                            rev = float(inc.loc[k, q])
                            break
                    if rev and rev > 0:
                        if gross_margin is None:
                            for k in ["Gross Profit"]:
                                if k in inc.index:
                                    v = float(inc.loc[k, q])
                                    gross_margin = v / rev
                                    break
                        if op_margin is None:
                            for k in ["Operating Income", "EBIT"]:
                                if k in inc.index:
                                    v = float(inc.loc[k, q])
                                    op_margin = v / rev
                                    break
                        if ebitda_margin is None:
                            for k in ["EBITDA", "Normalized EBITDA", "Reconciled Ebitda"]:
                                if k in inc.index:
                                    v = float(inc.loc[k, q])
                                    ebitda_margin = v / rev
                                    break
                        if net_margin is None:
                            for k in ["Net Income", "Net Income Common Stockholders"]:
                                if k in inc.index:
                                    v = float(inc.loc[k, q])
                                    net_margin = v / rev
                                    break
            except Exception:
                pass

        if roa is None or roe is None:
            try:
                bs = None
                for attr in ["quarterly_balance_sheet", "quarterly_balancesheet"]:
                    val = getattr(tk, attr, None)
                    if val is not None and not val.empty:
                        bs = val
                        break
                inc2 = None
                for attr in ["quarterly_income_stmt", "quarterly_financials"]:
                    val = getattr(tk, attr, None)
                    if val is not None and not val.empty:
                        inc2 = val
                        break
                if bs is not None and inc2 is not None:
                    q = bs.columns[0]
                    net_inc = None
                    for k in ["Net Income", "Net Income Common Stockholders"]:
                        if k in inc2.index and q in inc2.columns:
                            net_inc = float(inc2.loc[k, q])
                            break
                    if net_inc is not None:
                        if roa is None:
                            for k in ["Total Assets"]:
                                if k in bs.index:
                                    ta = float(bs.loc[k, q])
                                    if ta > 0:
                                        roa = (net_inc * 4) / ta
                                    break
                        if roe is None:
                            for k in ["Total Stockholders Equity", "Stockholders Equity", "Total Equity Gross Minority Interest"]:
                                if k in bs.index:
                                    eq = float(bs.loc[k, q])
                                    if eq > 0:
                                        roe = (net_inc * 4) / eq
                                    break
            except Exception:
                pass

        return {
            "gross_margin": gross_margin,
            "op_margin": op_margin,
            "ebitda_margin": ebitda_margin,
            "net_margin": net_margin,
            "roa": roa,
            "roe": roe,
        }
    except Exception as e:
        logger.debug(f"get_profitability_metrics error: {e}")
        return None


@st.cache_data(ttl=600)
def get_balance_sheet_metrics(ticker):
    """Fetch balance sheet metrics: total cash, total debt, net cash/debt, D/E, current ratio, quick ratio."""
    try:
        tk = get_yf_ticker(ticker)
        if tk is None:
            return None
        info = {}
        try:
            info = tk.info
            if not isinstance(info, dict):
                info = {}
        except Exception:
            pass

        total_cash = info.get("totalCash")
        total_debt = info.get("totalDebt")
        de_ratio = info.get("debtToEquity")
        current_ratio = info.get("currentRatio")
        quick_ratio = info.get("quickRatio")

        if total_cash is None or total_debt is None:
            try:
                bs = None
                for attr in ["quarterly_balance_sheet", "quarterly_balancesheet"]:
                    val = getattr(tk, attr, None)
                    if val is not None and not val.empty:
                        bs = val
                        break
                if bs is not None and not bs.empty:
                    q = bs.columns[0]
                    if total_cash is None:
                        for k in ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash And Short Term Investments"]:
                            if k in bs.index:
                                total_cash = float(bs.loc[k, q])
                                break
                    if total_debt is None:
                        for k in ["Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"]:
                            if k in bs.index:
                                total_debt = float(bs.loc[k, q])
                                break
                    if de_ratio is None:
                        equity = None
                        for k in ["Total Stockholders Equity", "Stockholders Equity"]:
                            if k in bs.index:
                                equity = float(bs.loc[k, q])
                                break
                        if equity and equity > 0 and total_debt:
                            de_ratio = round(total_debt / equity * 100, 2)
                    if current_ratio is None:
                        ca, cl = None, None
                        for k in ["Current Assets"]:
                            if k in bs.index:
                                ca = float(bs.loc[k, q])
                                break
                        for k in ["Current Liabilities"]:
                            if k in bs.index:
                                cl = float(bs.loc[k, q])
                                break
                        if ca and cl and cl > 0:
                            current_ratio = round(ca / cl, 2)
                    if quick_ratio is None and current_ratio is not None:
                        inv = None
                        for k in ["Inventory"]:
                            if k in bs.index:
                                inv = float(bs.loc[k, q])
                                break
                        if inv is not None and ca and cl and cl > 0:
                            quick_ratio = round((ca - inv) / cl, 2)
            except Exception:
                pass

        net_cash_debt = None
        if total_cash is not None and total_debt is not None:
            net_cash_debt = total_cash - total_debt

        return {
            "total_cash": total_cash,
            "total_debt": total_debt,
            "net_cash_debt": net_cash_debt,
            "de_ratio": de_ratio,
            "current_ratio": current_ratio,
            "quick_ratio": quick_ratio,
        }
    except Exception as e:
        logger.debug(f"get_balance_sheet_metrics error: {e}")
        return None


_NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}
_TIME_SLOTS = {"time-pre-market": "bmo", "time-after-hours": "amc"}


def _money(v):
    """'$1,807,009,840,000' / '($0.12)' / 'N/A' → float or None."""
    s = str(v or "").replace("$", "").replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def nasdaq_earnings_day(day: str) -> list[dict]:
    """US earnings reports scheduled for *day* (YYYY-MM-DD) from Nasdaq's public calendar."""
    data = _fetch_robust_json("https://api.nasdaq.com/api/calendar/earnings", params={"date": day},
                              headers=_NASDAQ_HEADERS, timeout=12)
    rows = (((data or {}).get("data") or {}).get("rows")) or []
    out = []
    for r in rows:
        sym = str(r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        out.append({
            "date": day, "symbol": sym, "name": str(r.get("name") or sym).strip(),
            "slot": _TIME_SLOTS.get(r.get("time"), "tbd"),
            "market_cap": _money(r.get("marketCap")),
            "eps_est": _money(r.get("epsForecast")),
            "n_est": _safe_int(r.get("noOfEsts"), 0) or None,
            "last_eps": _money(r.get("lastYearEPS")),
            "last_date": str(r.get("lastYearRptDt") or ""),
            "fiscal_q": str(r.get("fiscalQuarterEnding") or ""),
            # Present once the company has reported (Nasdaq then drops the time-of-day).
            "eps_actual": _money(r.get("eps")),
            "surprise": _safe_float(str(r.get("surprise") or "").replace("%", ""), None),
        })
    return out


def earnings_week(monday) -> list[dict]:
    """All reports Monday–Friday of the week starting *monday* (a date), fetched in parallel."""
    import concurrent.futures
    from datetime import timedelta as _td
    days = [(monday + _td(days=i)).isoformat() for i in range(5)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(nasdaq_earnings_day, days))
    return [r for day in results for r in day]
