"""World stock-exchange trading sessions (regular hours, local time).

Pure computation, no network. Exchange holidays are not modelled, so a market
can show "Open" on a local holiday.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

# (code, name, tz, sessions [(open, close)], trading weekdays (Mon=0))
EXCHANGES = [
    ("NYSE", "New York", "America/New_York", [("09:30", "16:00")], range(5)),
    ("TSX", "Toronto", "America/Toronto", [("09:30", "16:00")], range(5)),
    ("B3", "São Paulo", "America/Sao_Paulo", [("10:00", "17:00")], range(5)),
    ("LSE", "London", "Europe/London", [("08:00", "16:30")], range(5)),
    ("XETRA", "Frankfurt", "Europe/Berlin", [("09:00", "17:30")], range(5)),
    ("EPA", "Paris", "Europe/Paris", [("09:00", "17:30")], range(5)),
    ("SIX", "Zurich", "Europe/Zurich", [("09:00", "17:30")], range(5)),
    ("JSE", "Johannesburg", "Africa/Johannesburg", [("09:00", "17:00")], range(5)),
    ("TADAWUL", "Riyadh", "Asia/Riyadh", [("10:00", "15:00")], (6, 0, 1, 2, 3)),
    ("NSE", "Mumbai", "Asia/Kolkata", [("09:15", "15:30")], range(5)),
    ("SSE", "Shanghai", "Asia/Shanghai", [("09:30", "11:30"), ("13:00", "15:00")], range(5)),
    ("HKEX", "Hong Kong", "Asia/Hong_Kong", [("09:30", "12:00"), ("13:00", "16:00")], range(5)),
    ("TSE", "Tokyo", "Asia/Tokyo", [("09:00", "11:30"), ("12:30", "15:30")], range(5)),
    ("KRX", "Seoul", "Asia/Seoul", [("09:00", "15:30")], range(5)),
    ("ASX", "Sydney", "Australia/Sydney", [("10:00", "16:00")], range(5)),
]


def _t(s):
    h, m = map(int, s.split(":"))
    return time(h, m)


def _fmt_delta(td: timedelta) -> str:
    mins = max(0, int(td.total_seconds() // 60))
    d, rem = divmod(mins, 1440)
    h, m = divmod(rem, 60)
    if d:
        return f"{d}d {h}h"
    return f"{h}h {m:02d}m" if h else f"{m}m"


def exchange_status(now_utc: datetime | None = None) -> list[dict]:
    """Status per exchange: OPEN / LUNCH / CLOSED, local clock and time to next change."""
    now_utc = now_utc or datetime.now(ZoneInfo("UTC"))
    out = []
    for code, city, tz, sessions, days in EXCHANGES:
        z = ZoneInfo(tz)
        now = now_utc.astimezone(z)
        status, change_at = "CLOSED", None
        # Search today and the next 7 days for the current/next session boundary.
        for offset in range(8):
            day = (now + timedelta(days=offset)).date()
            if day.weekday() not in days:
                continue
            for i, (o, c) in enumerate(sessions):
                start = datetime.combine(day, _t(o), z)
                end = datetime.combine(day, _t(c), z)
                if start <= now < end:
                    status, change_at = "OPEN", end
                    break
                if now < start:
                    status = "LUNCH" if offset == 0 and i > 0 and now >= datetime.combine(day, _t(sessions[i - 1][1]), z) \
                        else "CLOSED"
                    change_at = start
                    break
            if change_at:
                break
        out.append({
            "code": code, "city": city, "status": status, "local": now.strftime("%H:%M"),
            "verb": "closes" if status == "OPEN" else "opens",
            "in": _fmt_delta(change_at - now) if change_at else "—",
        })
    return out
