"""Reverse and forward geocoding services with thread-safe TTL caching."""

import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger("vayumitra.geocode")

GEO_USER_AGENT = "VayuMitra-UrbanAirQualityAssistant/2.0 (Challenge-06)"
GEO_CACHE_TTL_SECONDS = 1800
GEO_CACHE_MAX_ENTRIES = 256

_GEO_CACHE_LOCK = threading.Lock()
_REVERSE_GEO_CACHE: dict[tuple[float, float], tuple[float, dict]] = {}
_FORWARD_GEO_CACHE: dict[str, tuple[float, dict]] = {}


def _cache_get(cache: dict, key):
    now = time.monotonic()
    with _GEO_CACHE_LOCK:
        entry = cache.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if now > expires_at:
            cache.pop(key, None)
            return None
        return dict(value)


def _cache_set(cache: dict, key, value: dict):
    now = time.monotonic()
    with _GEO_CACHE_LOCK:
        if len(cache) >= GEO_CACHE_MAX_ENTRIES:
            expired = [k for k, (exp, _) in cache.items() if now > exp]
            for k in expired:
                cache.pop(k, None)
            if len(cache) >= GEO_CACHE_MAX_ENTRIES:
                oldest_key = next(iter(cache))
                cache.pop(oldest_key, None)
        cache[key] = (now + GEO_CACHE_TTL_SECONDS, dict(value))


def clear_geocode_caches():
    """Clear in-memory geocode caches (primarily for unit tests)."""
    with _GEO_CACHE_LOCK:
        _REVERSE_GEO_CACHE.clear()
        _FORWARD_GEO_CACHE.clear()


def _dedupe_parts(parts: list[str]) -> list[str]:
    seen = set()
    cleaned = []
    for p in parts:
        val = (p or "").strip()
        if not val:
            continue
        key = val.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(val)
    return cleaned


def _clean_district(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"\s+(District|Subdistrict|Taluka|Tehsil)$", "", name.strip(), flags=re.IGNORECASE).strip()


def _format_nominatim_result(data: dict, lat: float, lon: float) -> dict:
    addr = data.get("address") or {}
    road = addr.get("road") or addr.get("pedestrian") or addr.get("residential") or ""
    area = (
        addr.get("neighbourhood")
        or addr.get("suburb")
        or addr.get("quarter")
        or addr.get("residential")
        or addr.get("village")
        or addr.get("hamlet")
        or addr.get("city_district")
        or addr.get("town")
        or ""
    )
    district_city = _clean_district(addr.get("state_district") or "")
    city = (
        addr.get("city")
        or addr.get("municipality")
        or (addr.get("town") if (addr.get("town") or "").lower() != area.lower() else "")
        or district_city
        or _clean_district(addr.get("county") or "")
        or ""
    )
    if city.lower() == area.lower() and district_city and district_city.lower() != area.lower():
        city = district_city
    state = addr.get("state") or ""
    postcode = addr.get("postcode") or ""

    if area and city:
        display_parts = _dedupe_parts([area, city])
    elif road and city:
        display_parts = _dedupe_parts([road, city])
    else:
        display_parts = _dedupe_parts([area, road, city, state])

    display_name = ", ".join(display_parts) or data.get("name") or f"GPS ({lat:.4f}, {lon:.4f})"
    exact_parts = _dedupe_parts([road, area, city, state, postcode])
    exact_address = ", ".join(exact_parts) or data.get("display_name") or display_name

    return {
        "display_name": display_name,
        "exact_address": exact_address,
        "road": road,
        "area": area,
        "city": city,
        "state": state,
        "postcode": postcode,
        "lat": lat,
        "lon": lon,
        "provider": "OpenStreetMap Nominatim",
    }


def reverse_geocode_coordinates(lat: float, lon: float) -> dict:
    """Resolve exact neighborhood/street + city using Google Maps (if configured), Nominatim, Photon, or BigDataCloud."""
    cache_key = (round(lat, 4), round(lon, 4))
    cached = _cache_get(_REVERSE_GEO_CACHE, cache_key)
    if cached:
        cached["lat"] = lat
        cached["lon"] = lon
        cached["cached"] = True
        return cached

    def _store_and_return(res: dict) -> dict:
        if res.get("provider") != "GPS Coordinates":
            _cache_set(_REVERSE_GEO_CACHE, cache_key, res)
        res["cached"] = False
        return res

    google_maps_key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    if google_maps_key:
        try:
            url = (
                "https://maps.googleapis.com/maps/api/geocode/json?"
                + urllib.parse.urlencode({"latlng": f"{lat},{lon}", "key": google_maps_key, "language": "en"})
            )
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": GEO_USER_AGENT,
                    "X-Goog-Maps-Solution-ID": "gmp_git_agentskills_v1",
                },
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                gdata = json.loads(resp.read().decode("utf-8"))
            if gdata.get("status") == "OK" and gdata.get("results"):
                top = gdata["results"][0]
                comps = top.get("address_components") or []
                by_type = {}
                for comp in comps:
                    for t in comp.get("types", []):
                        by_type.setdefault(t, comp.get("long_name", ""))
                area = (
                    by_type.get("sublocality_level_2")
                    or by_type.get("sublocality_level_1")
                    or by_type.get("sublocality")
                    or by_type.get("neighborhood")
                    or by_type.get("route")
                    or ""
                )
                city = by_type.get("locality") or _clean_district(by_type.get("administrative_area_level_2") or "")
                state = by_type.get("administrative_area_level_1") or ""
                postcode = by_type.get("postal_code") or ""
                display_name = ", ".join(_dedupe_parts([area, city])) or top.get("formatted_address", "")
                return _store_and_return({
                    "display_name": display_name,
                    "exact_address": top.get("formatted_address") or display_name,
                    "road": by_type.get("route", ""),
                    "area": area,
                    "city": city,
                    "state": state,
                    "postcode": postcode,
                    "lat": lat,
                    "lon": lon,
                    "provider": "Google Maps Geocoding",
                })
        except Exception as err:
            # Never log raw URLs that may contain API keys
            logger.warning("Google Maps reverse geocode failed (%s)", type(err).__name__)

    # Primary free exact reverse-geocoder: OpenStreetMap Nominatim (zoom=18 street/neighborhood level)
    try:
        url = (
            "https://nominatim.openstreetmap.org/reverse?"
            + urllib.parse.urlencode(
                {"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 18, "addressdetails": 1}
            )
        )
        req = urllib.request.Request(url, headers={"User-Agent": GEO_USER_AGENT, "Accept-Language": "en"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data and not data.get("error"):
            return _store_and_return(_format_nominatim_result(data, lat, lon))
    except Exception as err:
        logger.warning("Nominatim reverse geocode failed (%s)", type(err).__name__)

    # Secondary free OSM reverse-geocoder: Photon by Komoot
    try:
        url = "https://photon.komoot.io/reverse?" + urllib.parse.urlencode({"lat": f"{lat:.6f}", "lon": f"{lon:.6f}"})
        req = urllib.request.Request(url, headers={"User-Agent": GEO_USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as resp:
            pdata = json.loads(resp.read().decode("utf-8"))
        features = pdata.get("features") or []
        if features:
            props = features[0].get("properties") or {}
            road = props.get("street") or ""
            area = props.get("district") or props.get("locality") or props.get("name") or ""
            city = props.get("city") or _clean_district(props.get("county") or "")
            state = props.get("state") or ""
            postcode = props.get("postcode") or ""
            display_name = ", ".join(_dedupe_parts([area, city])) or ", ".join(_dedupe_parts([road, city, state]))
            exact_address = ", ".join(_dedupe_parts([road, area, city, state, postcode])) or display_name
            if display_name:
                return _store_and_return({
                    "display_name": display_name,
                    "exact_address": exact_address,
                    "road": road,
                    "area": area,
                    "city": city,
                    "state": state,
                    "postcode": postcode,
                    "lat": lat,
                    "lon": lon,
                    "provider": "Photon (OpenStreetMap)",
                })
    except Exception as err:
        logger.warning("Photon reverse geocode failed (%s)", type(err).__name__)

    # Last-resort fallback: BigDataCloud
    try:
        url = (
            "https://api.bigdatacloud.net/data/reverse-geocode-client?"
            + urllib.parse.urlencode({"latitude": lat, "longitude": lon, "localityLanguage": "en"})
        )
        req = urllib.request.Request(url, headers={"User-Agent": GEO_USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as resp:
            bdata = json.loads(resp.read().decode("utf-8"))
        area = bdata.get("locality") or ""
        city = bdata.get("city") or bdata.get("principalSubdivision") or ""
        display_name = ", ".join(_dedupe_parts([area, city])) or f"GPS ({lat:.4f}, {lon:.4f})"
        return _store_and_return({
            "display_name": display_name,
            "exact_address": display_name,
            "road": "",
            "area": area,
            "city": city,
            "state": bdata.get("principalSubdivision") or "",
            "postcode": bdata.get("postcode") or "",
            "lat": lat,
            "lon": lon,
            "provider": "BigDataCloud Fallback",
        })
    except Exception as err:
        logger.warning("BigDataCloud fallback failed (%s)", type(err).__name__)

    fallback_name = f"GPS ({lat:.4f}, {lon:.4f})"
    return _store_and_return({
        "display_name": fallback_name,
        "exact_address": fallback_name,
        "road": "",
        "area": "",
        "city": "",
        "state": "",
        "postcode": "",
        "lat": lat,
        "lon": lon,
        "provider": "GPS Coordinates",
    })


def forward_geocode_query(query: str) -> Optional[dict]:
    """Resolve a user-typed locality, pincode, or city into exact coordinates and formatted name."""
    q = (query or "").strip()[:160]
    if not q:
        return None

    cache_key = re.sub(r"\s+", " ", q).lower()
    cached = _cache_get(_FORWARD_GEO_CACHE, cache_key)
    if cached:
        cached["cached"] = True
        return cached

    try:
        url = (
            "https://nominatim.openstreetmap.org/search?"
            + urllib.parse.urlencode({"format": "jsonv2", "q": q, "addressdetails": 1, "limit": 1})
        )
        req = urllib.request.Request(url, headers={"User-Agent": GEO_USER_AGENT, "Accept-Language": "en"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            results = json.loads(resp.read().decode("utf-8"))
        if results:
            top = results[0]
            lat = float(top["lat"])
            lon = float(top["lon"])
            formatted = _format_nominatim_result(top, lat, lon)
            _cache_set(_FORWARD_GEO_CACHE, cache_key, formatted)
            formatted["cached"] = False
            return formatted
    except Exception as err:
        logger.warning("Nominatim forward geocode failed (%s)", type(err).__name__)

    try:
        url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode({"q": q, "limit": 1})
        req = urllib.request.Request(url, headers={"User-Agent": GEO_USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as resp:
            pdata = json.loads(resp.read().decode("utf-8"))
        features = pdata.get("features") or []
        if features:
            coords = features[0].get("geometry", {}).get("coordinates") or []
            props = features[0].get("properties") or {}
            if len(coords) >= 2:
                lon, lat = float(coords[0]), float(coords[1])
                area = props.get("district") or props.get("locality") or props.get("name") or ""
                city = props.get("city") or _clean_district(props.get("county") or "")
                state = props.get("state") or ""
                postcode = props.get("postcode") or ""
                display_name = ", ".join(_dedupe_parts([area, city])) or q
                exact_address = ", ".join(_dedupe_parts([props.get("street", ""), area, city, state, postcode])) or display_name
                formatted = {
                    "display_name": display_name,
                    "exact_address": exact_address,
                    "road": props.get("street") or "",
                    "area": area,
                    "city": city,
                    "state": state,
                    "postcode": postcode,
                    "lat": lat,
                    "lon": lon,
                    "provider": "Photon (OpenStreetMap)",
                }
                _cache_set(_FORWARD_GEO_CACHE, cache_key, formatted)
                formatted["cached"] = False
                return formatted
    except Exception as err:
        logger.warning("Photon forward geocode failed (%s)", type(err).__name__)

    return None
