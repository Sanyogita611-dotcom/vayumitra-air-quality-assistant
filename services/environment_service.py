"""Real-time hyper-local Air Quality & Weather aggregation service.

Uses Google Maps Platform Air Quality API (when GOOGLE_MAPS_API_KEY is configured)
combined with Open-Meteo Air Quality (24h hourly forecast + zero-key fallback)
and Open-Meteo live Weather (temperature, humidity, wind speed) via server-side proxy.
"""

import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger("vayumitra.environment")

USER_AGENT = "VayuMitra-UrbanAirQualityAssistant/2.0 (Challenge-06)"
GMP_SOLUTION_ID = "gmp_git_agentskills_v1"
ENV_CACHE_TTL_SECONDS = 300  # 5-minute ephemeral cache for live sensor readings
ENV_CACHE_MAX_ENTRIES = 256

_ENV_CACHE_LOCK = threading.Lock()
_ENV_CACHE: dict[tuple[float, float], tuple[float, dict]] = {}


def clear_environment_cache():
    """Clear in-memory environment cache (primarily for unit tests)."""
    with _ENV_CACHE_LOCK:
        _ENV_CACHE.clear()


def _cache_get(key: tuple[float, float]) -> Optional[dict]:
    now = time.monotonic()
    with _ENV_CACHE_LOCK:
        entry = _ENV_CACHE.get(key)
        if not entry:
            return None
        exp, val = entry
        if now > exp:
            _ENV_CACHE.pop(key, None)
            return None
        return dict(val)


def _cache_set(key: tuple[float, float], value: dict):
    now = time.monotonic()
    with _ENV_CACHE_LOCK:
        if len(_ENV_CACHE) >= ENV_CACHE_MAX_ENTRIES:
            oldest = next(iter(_ENV_CACHE))
            _ENV_CACHE.pop(oldest, None)
        _ENV_CACHE[key] = (now + ENV_CACHE_TTL_SECONDS, dict(value))


def fetch_google_air_quality(lat: float, lon: float, api_key: str) -> Optional[dict]:
    """Query Google Maps Platform Air Quality API currentConditions:lookup server-side."""
    url = "https://airquality.googleapis.com/v1/currentConditions:lookup"
    body = {
        "universalAqi": True,
        "location": {"latitude": lat, "longitude": lon},
        "extraComputations": [
            "LOCAL_AQI",
            "POLLUTANT_CONCENTRATION",
            "DOMINANT_POLLUTANT_CONCENTRATION",
            "HEALTH_RECOMMENDATIONS",
        ],
        "languageCode": "en",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-Maps-Solution-ID": GMP_SOLUTION_ID,
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return parse_google_air_quality(data)
    except Exception as err:
        logger.warning("Google Air Quality API unavailable (%s); using Open-Meteo", type(err).__name__)
        return None


def parse_google_air_quality(data: dict) -> Optional[dict]:
    """Extract normalized AQI, local CPCB index, pollutants, and dominant pollutant from GMP response."""
    if not isinstance(data, dict):
        return None
    indexes = data.get("indexes") or []
    if not indexes:
        return None

    local_idx = next((i for i in indexes if i.get("code") != "uaqi"), None)
    uaqi_idx = next((i for i in indexes if i.get("code") == "uaqi"), None)
    primary = local_idx or uaqi_idx or indexes[0]

    pollutants_map = {}
    for p in data.get("pollutants") or []:
        code = (p.get("code") or "").lower()
        val = (p.get("concentration") or {}).get("value")
        if code and val is not None:
            try:
                pollutants_map[code] = round(float(val), 1)
            except (TypeError, ValueError):
                pass

    return {
        "aqi": int(round(float(primary.get("aqi", 100)))),
        "aqi_scale": primary.get("displayName") or primary.get("code") or "Local AQI",
        "category": primary.get("category") or "",
        "dominant_pollutant": (primary.get("dominantPollutant") or "pm25").upper(),
        "pm25": pollutants_map.get("pm25"),
        "pm10": pollutants_map.get("pm10"),
        "no2": pollutants_map.get("no2"),
        "o3": pollutants_map.get("o3"),
        "provider": "Google Maps Air Quality API",
    }


def fetch_open_meteo_air_quality(lat: float, lon: float) -> Optional[dict]:
    """Fetch live + 24-hour hourly AQI and pollutants from free Open-Meteo Air Quality API."""
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality?"
        + urllib.parse.urlencode({
            "latitude": f"{lat:.5f}",
            "longitude": f"{lon:.5f}",
            "current": "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone",
            "hourly": "us_aqi,pm2_5",
            "forecast_days": 1,
            "timezone": "auto",
        })
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        current = data.get("current") or {}
        hourly_raw = data.get("hourly") or {}
        times = hourly_raw.get("time") or []
        aqis = hourly_raw.get("us_aqi") or []
        pm25s = hourly_raw.get("pm2_5") or []
        hourly = []
        for idx, ts in enumerate(times):
            hour = idx
            if isinstance(ts, str) and "T" in ts:
                try:
                    hour = int(ts.split("T", 1)[1].split(":", 1)[0])
                except ValueError:
                    hour = idx
            hourly.append({
                "hour": hour,
                "aqi": aqis[idx] if idx < len(aqis) else None,
                "pm25": pm25s[idx] if idx < len(pm25s) else None,
            })

        return {
            "aqi": int(round(float(current.get("us_aqi", 100)))) if current.get("us_aqi") is not None else None,
            "aqi_scale": "US AQI",
            "pm25": round(float(current["pm2_5"]), 1) if current.get("pm2_5") is not None else None,
            "pm10": round(float(current["pm10"]), 1) if current.get("pm10") is not None else None,
            "no2": round(float(current["nitrogen_dioxide"]), 1) if current.get("nitrogen_dioxide") is not None else None,
            "o3": round(float(current["ozone"]), 1) if current.get("ozone") is not None else None,
            "dominant_pollutant": "PM2.5",
            "hourly": hourly,
            "provider": "Open-Meteo Air Quality",
        }
    except Exception as err:
        logger.warning("Open-Meteo Air Quality fetch failed (%s)", type(err).__name__)
        return None


def fetch_open_meteo_weather(lat: float, lon: float) -> Optional[dict]:
    """Fetch live temperature, humidity, and wind speed (explains smog stagnation/dispersion)."""
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode({
            "latitude": f"{lat:.5f}",
            "longitude": f"{lon:.5f}",
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            "timezone": "auto",
        })
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cur = data.get("current") or {}
        return {
            "temp_c": round(float(cur["temperature_2m"]), 1) if cur.get("temperature_2m") is not None else None,
            "humidity_pct": int(round(float(cur["relative_humidity_2m"]))) if cur.get("relative_humidity_2m") is not None else None,
            "wind_kmh": round(float(cur["wind_speed_10m"]), 1) if cur.get("wind_speed_10m") is not None else None,
        }
    except Exception as err:
        logger.warning("Open-Meteo Weather fetch failed (%s)", type(err).__name__)
        return None


def get_live_environment(lat: float, lon: float) -> dict:
    """Return unified real-time air quality + 24h hourly forecast + live weather for exact coordinates."""
    cache_key = (round(lat, 3), round(lon, 3))
    cached = _cache_get(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    google_key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    google_aq = fetch_google_air_quality(lat, lon, google_key) if google_key else None
    om_aq = fetch_open_meteo_air_quality(lat, lon)
    weather = fetch_open_meteo_weather(lat, lon) or {}

    if google_aq:
        result = {
            "aqi": google_aq["aqi"],
            "aqi_scale": google_aq["aqi_scale"],
            "category": google_aq.get("category", ""),
            "dominant_pollutant": google_aq.get("dominant_pollutant", "PM2.5"),
            "pm25": google_aq["pm25"] if google_aq["pm25"] is not None else (om_aq.get("pm25") if om_aq else 50.0),
            "pm10": google_aq["pm10"] if google_aq["pm10"] is not None else (om_aq.get("pm10") if om_aq else None),
            "no2": google_aq.get("no2"),
            "o3": google_aq.get("o3"),
            "hourly": om_aq.get("hourly", []) if om_aq else [],
            "weather": weather,
            "provider": google_aq["provider"],
            "is_live": True,
            "cached": False,
        }
        _cache_set(cache_key, result)
        return result

    if om_aq and om_aq.get("aqi") is not None:
        result = {
            "aqi": om_aq["aqi"],
            "aqi_scale": om_aq["aqi_scale"],
            "category": "",
            "dominant_pollutant": om_aq.get("dominant_pollutant", "PM2.5"),
            "pm25": om_aq["pm25"] if om_aq["pm25"] is not None else 45.0,
            "pm10": om_aq.get("pm10"),
            "no2": om_aq.get("no2"),
            "o3": om_aq.get("o3"),
            "hourly": om_aq.get("hourly", []),
            "weather": weather,
            "provider": om_aq["provider"],
            "is_live": True,
            "cached": False,
        }
        _cache_set(cache_key, result)
        return result

    return {
        "aqi": 155,
        "aqi_scale": "Estimated AQI",
        "category": "",
        "dominant_pollutant": "PM2.5",
        "pm25": 68.0,
        "pm10": None,
        "no2": None,
        "o3": None,
        "hourly": [],
        "weather": weather,
        "provider": "Offline Estimate",
        "is_live": False,
        "cached": False,
    }
