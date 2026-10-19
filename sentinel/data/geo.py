"""Keyless geo feeds for the globe: military ADS-B, satellites, AIS."""
from __future__ import annotations

import logging
import math
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from sentinel.core.http import (
    _fetch_robust_json,
)
from sentinel.core.formatting import _safe_float
from sentinel.core.secrets import unwrap_secret as _unwrap_secret
from sentinel.core.cache import stale_cached_source

logger = logging.getLogger("sentinel.data")


@stale_cached_source(ttl=300, retry_ttl=30)
def fetch_military_aircraft() -> "pd.DataFrame":
    import pandas as _pd
    try:
        # adsb.lol publishes a keyless ODbL feed.  The former airplanes.live
        # endpoint now rejects this server with HTTP 403.
        data = _fetch_robust_json("https://api.adsb.lol/v2/mil", timeout=12)
        if not data:
            return _pd.DataFrame()
        ac_list = data.get("ac", [])
        rows = []
        for ac in ac_list[:350]:  # hard cap for globe payload / memory
            lat, lon = ac.get("lat"), ac.get("lon")
            if lat is None or lon is None: continue
            lat_f, lon_f = _safe_float(lat, float("nan")), _safe_float(lon, float("nan"))
            if not math.isfinite(lat_f) or not math.isfinite(lon_f):
                continue
            if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                continue
            on_ground = ac.get("alt_baro") == "ground"
            baro_alt = None if on_ground else _safe_float(ac.get("alt_baro"), float("nan"))
            geom_alt = _safe_float(ac.get("alt_geom"), float("nan"))
            # Ported from God's Eye View's MIT-licensed adsb.lol normalizer:
            # prefer barometric altitude, preserve ground state, then use
            # geometric altitude only when barometric altitude is absent.
            display_alt = 0.0 if on_ground else (
                baro_alt if math.isfinite(baro_alt) else geom_alt
            )
            if not math.isfinite(display_alt):
                display_alt = 0.0
            rows.append({
                "hex": str(ac.get("hex", ""))[:16], "lat": lat_f, "lon": lon_f,
                "alt_baro": round(display_alt, 1),
                "alt_geom": round(geom_alt, 1) if math.isfinite(geom_alt) else None,
                "on_ground": on_ground,
                "gs": round(_safe_float(ac.get("gs"), 0), 1),
                "flight": str(ac.get("flight") or ac.get("hex", "UNKN")).strip(),
                "track": _safe_float(ac.get("track"), 0),
                "seen_s": max(0.0, _safe_float(ac.get("seen_pos", ac.get("seen")), 0)),
                "registration": str(ac.get("r") or "")[:24],
                "aircraft_type": str(ac.get("t") or "")[:16],
                "size": 48,
            })
        df = _pd.DataFrame(rows)
        # Skip per-row photo_url — was pure string churn, unused by Cesium globe
        return df
    except Exception as e:
        logger.error("Military Flight Fetch Error: %s", str(e))
        return _pd.DataFrame()


@stale_cached_source(ttl=300, retry_ttl=60)
def fetch_satellite_positions():
    import pandas as _pd
    try:
        from skyfield.api import EarthSatellite, load, wgs84 as _wgs84
        import numpy as _np
    except ImportError:
        logger.error("Satellite Tracker: Missing skyfield")
        return _pd.DataFrame(), []

    try:
        # "active" is many thousands of TLEs and was downloaded only to discard
        # almost all of them. Two small operational groups cover useful targets.
        from concurrent.futures import ThreadPoolExecutor

        def _fetch_tle_group(group):
            r = requests.get(
                f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=tle",
                timeout=12,
                headers={"User-Agent": "SENTINEL/3.0"},
            )
            r.raise_for_status()
            return [line.strip() for line in r.text.splitlines() if line.strip()]

        with ThreadPoolExecutor(max_workers=2) as pool:
            lines = []
            for group_lines in pool.map(_fetch_tle_group, ("stations", "military")):
                lines.extend(group_lines)
    except Exception as e:
        logger.error("Celestrak Error: %s", str(e))
        return _pd.DataFrame(), []

    from datetime import timezone as _tz, timedelta as _td
    ts = load.timescale()
    now_utc = datetime.now(_tz.utc)
    t_now = ts.from_datetime(now_utc)

    sats, i = [], 0
    while i + 2 < len(lines):
        name, tle1, tle2 = lines[i], lines[i + 1], lines[i + 2]
        if tle1.startswith("1 ") and tle2.startswith("2 "):
            try: sats.append(EarthSatellite(tle1, tle2, name, ts))
            except Exception as e:
                logger.debug(f"Error caught: {e}")
            i += 3
        else: i += 1

    # Cap sats + coarser path samples — skyfield loops were a cold-cache stall
    sats = sats[:80]
    rows, path_features = [], []

    for sat in sats:
        try:
            geo = _wgs84.geographic_position_of(sat.at(t_now))
            lat, lon, alt_km = float(geo.latitude.degrees), float(geo.longitude.degrees), float(geo.elevation.km)
            if not all(math.isfinite(v) for v in (lat, lon, alt_km)):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            try: n = sat.model.no_kozai * (1440 / (2 * _np.pi))
            except Exception: n = 15.5
            vel_kms = round(n * 2 * _np.pi * (6371 + alt_km) / 86400, 2)

            rows.append({"name": sat.name, "lat": lat, "lon": lon, "alt_km": round(alt_km, 1), "vel_kms": vel_kms, "size": 32})
            path_coords = []
            for offset in range(0, 91, 15):  # coarser orbit samples
                t_f = ts.from_datetime(now_utc + _td(minutes=offset))
                g = _wgs84.geographic_position_of(sat.at(t_f))
                path_coords.append([float(g.longitude.degrees), float(g.latitude.degrees)])
            path_features.append({"path": path_coords, "name": sat.name, "color": [0, 180, 255, 100]})
        except Exception: continue

    return _pd.DataFrame(rows), path_features


@st.cache_data(ttl=300)
def fetch_military_aircraft_json():
    df = fetch_military_aircraft()
    return [] if df is None or df.empty else df.to_dict("records")


@st.cache_data(ttl=300)
def fetch_satellite_positions_json():
    df, _ = fetch_satellite_positions()
    return [] if df is None or df.empty else df.to_dict("records")


@stale_cached_source(ttl=300, retry_ttl=30)
def fetch_ais_vessels():
    """Fetch genuine public AIS observations; never synthesize vessel positions."""
    vessels = []
    # AISStream is WebSocket-only. The old /v0/ships REST call did not exist
    # and exposed keys in failed request URLs, so it is intentionally absent.
    try:
        mar_key = _unwrap_secret(st.secrets.get("MARINESIA_API_KEY", ""))
    except Exception:
        mar_key = ""
    # Marinesia: parallel chokepoints, no 1s serial sleep (was a major GEO lag source)
    if mar_key:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        _CHOKEPOINT_BOXES = [
            ("suez", 29.0, 30.5, 32.0, 33.5), ("hormuz", 25.5, 27.5, 55.0, 57.0),
            ("mandeb", 12.0, 13.5, 42.5, 44.0), ("malacca", 0.5, 2.5, 103.0, 104.5),
            ("taiwan", 23.5, 25.5, 118.5, 120.5), ("gibraltar", 35.5, 36.5, -6.0, -5.0),
        ]
        def _fetch_box(box):
            name, lat_min, lat_max, lon_min, lon_max = box
            try:
                data = _fetch_robust_json(
                    "https://api.marinesia.com/api/v2/vessel/area",
                    params={
                        "lat_min": lat_min, "lat_max": lat_max,
                        "long_min": lon_min, "long_max": lon_max, "key": mar_key,
                    },
                    timeout=8,
                    headers={"User-Agent": "SENTINEL/3.0"},
                )
                out = []
                if data and not data.get("error") and data.get("data"):
                    for s in data["data"][:25]:
                        lat, lng = s.get("lat"), s.get("lng")
                        if lat is None or lng is None:
                            continue
                        out.append({
                            "mmsi": str(s.get("mmsi", "")),
                            "lat": float(lat), "lon": float(lng),
                            "speed": float(s.get("sog", 0) or 0),
                            "heading": float(s.get("cog", s.get("hdt", 0)) or 0),
                            "name": str(s.get("name", f"MMSI-{s.get('mmsi','')}"))[:30],
                            "type": str(s.get("type", "cargo")).lower(),
                        })
                return out
            except Exception:
                return []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for fut in as_completed([pool.submit(_fetch_box, b) for b in _CHOKEPOINT_BOXES]):
                try:
                    vessels.extend(fut.result() or [])
                except Exception:
                    pass

    try:
        data = _fetch_robust_json("https://meri.digitraffic.fi/api/ais/v1/locations", timeout=12, headers={"User-Agent": "SENTINEL/3.0", "Accept": "application/json"})
        if not data:
            data = {}
        for f in data.get("features", [])[:200]:
            props, coords = f.get("properties", {}), f.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2: continue
            vessels.append({"mmsi": str(props.get("mmsi", "")), "lat": float(coords[1]), "lon": float(coords[0]), "speed": float(props.get("sog", 0) or 0), "heading": float(props.get("cog", props.get("heading", 0)) or 0), "name": f"MMSI-{props.get('mmsi', 'UNKN')}", "type": "cargo"})
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    seen = {}
    for v in vessels:
        mmsi = v.get("mmsi", "")
        lat = _safe_float(v.get("lat"), float("nan"))
        lon = _safe_float(v.get("lon"), float("nan"))
        if not mmsi or not math.isfinite(lat) or not math.isfinite(lon):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        v["lat"], v["lon"] = lat, lon
        v["speed"] = max(0.0, _safe_float(v.get("speed"), 0.0))
        v["heading"] = _safe_float(v.get("heading"), 0.0) % 360
        existing = seen.get(mmsi)
        if existing is None: seen[mmsi] = v
        else:
            new_name, old_name = v.get("name", ""), existing.get("name", "")
            if (old_name.startswith("MMSI-") or old_name == "VESSEL") and not new_name.startswith("MMSI-") and new_name != "VESSEL":
                seen[mmsi] = v

    return list(seen.values())


# GDELT rejects browser (CORS) requests and allows ~1 request / 5 s, so the
# globe's news layers come from ONE server-side query, bucketed by keyword.
_CONFLICT_REGIONS = [
    (("gaza", "israel", "hamas", "hezbollah", "lebanon"), 31.5, 34.6, "Israel / Gaza / Lebanon"),
    (("ukraine", "russia", "kyiv", "kremlin", "donbas"), 48.8, 33.5, "Ukraine / Russia"),
    (("houthi", "red sea", "yemen"), 14.5, 42.5, "Red Sea / Yemen"),
    (("iran", "hormuz", "tehran"), 30.5, 53.5, "Iran / Gulf"),
    (("taiwan", "south china sea", "philippine"), 24.2, 120.8, "Taiwan / South China Sea"),
    (("sudan", "rsf", "darfur", "khartoum"), 15.6, 32.5, "Sudan"),
    (("sahel", "mali", "niger", "burkina"), 14.0, 0.0, "Sahel"),
    (("north korea", "pyongyang"), 39.0, 126.5, "Korean Peninsula"),
    (("congo", "m23", "goma"), -1.6, 29.0, "Eastern DRC"),
    (("syria", "damascus"), 34.8, 38.9, "Syria"),
    (("pakistan", "kashmir", "afghanistan"), 33.7, 70.5, "Pakistan / Afghanistan"),
    (("venezuela", "caribbean"), 8.0, -66.0, "Venezuela / Caribbean"),
]


@stale_cached_source(ttl=900, retry_ttl=120)
def fetch_conflict_feed():
    """{'signals': [...], 'headlines': [...]} from one GDELT query (last 48 h)."""
    data = _fetch_robust_json("https://api.gdeltproject.org/api/v2/doc/doc", params={
        "query": "(war OR attack OR airstrike OR missile OR military OR fighting OR blockade) sourcelang:english",
        "mode": "artlist", "maxrecords": 150, "format": "json", "timespan": "48h", "sort": "datedesc"}, timeout=12)
    arts = (data or {}).get("articles", []) if isinstance(data, dict) else []
    seen, clean = set(), []
    for a in arts:
        t = str(a.get("title", "")).strip()
        k = t.lower()[:60]
        if len(t) < 25 or k in seen:
            continue
        seen.add(k)
        clean.append({"title": t[:160], "url": a.get("url", ""), "domain": str(a.get("domain", "")).replace("www.", "")})
    signals = []
    for kws, lat, lon, label in _CONFLICT_REGIONS:
        hits = [a for a in clean if any(kw in a["title"].lower() for kw in kws)]
        if hits:
            signals.append({"label": f"{label} · {len(hits)}", "lat": lat, "lon": lon, "url": hits[0]["url"],
                            "titles": [h["title"] for h in hits[:4]]})
    if not clean:
        return {}
    return {"signals": signals, "headlines": clean[:6]}
