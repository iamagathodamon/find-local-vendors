"""City + trade -> local businesses from OpenStreetMap."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


USER_AGENT = "FindLocalVendors/1.0 (https://find-local-vendors.agathodamon.com)"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
NOMINATIM_LOOKUP = "https://nominatim.openstreetmap.org/lookup"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_RADIUS_M = 12000
DEFAULT_MAX_RESULTS = 10
HARD_MAX_RESULTS = 25
SKIP_CLASSES = {"highway", "railway", "waterway", "place", "boundary", "landuse"}

TRADE_PATTERNS = {
    "hvac": r"hvac|heating|air.?conditioning|furnace|climate control",
    "plumber": r"plumb",
    "electrician": r"electric",
    "roofer": r"roof",
    "roofing": r"roof",
    "hvac contractor": r"hvac|heating|air.?conditioning",
    "landscaper": r"landscape|lawn",
    "pest control": r"pest|exterminat",
    "locksmith": r"locksmith",
    "towing": r"tow",
    "auto repair": r"auto repair|mechanic|car repair",
    "cleaning": r"clean|janitor",
    "packer": r"packag",
    "packaging": r"packag",
}


def patterns_for(trade: str) -> str:
    cleaned = re.sub(r"\s+", " ", (trade or "").strip().lower())
    if cleaned in TRADE_PATTERNS:
        return TRADE_PATTERNS[cleaned]
    token = re.escape(cleaned)
    token = token.replace(r"\ ", r".{0,12}")
    return token or r"business"


def clamp_max_results(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = DEFAULT_MAX_RESULTS
    return max(1, min(HARD_MAX_RESULTS, n))


def _get(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _post(url: str, body: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def geocode_city(city: str, fetch=_get) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {"q": city, "format": "jsonv2", "limit": 1, "addressdetails": 1}
    )
    rows = json.loads(fetch(f"{NOMINATIM_SEARCH}?{query}").decode("utf-8"))
    if not rows:
        raise ValueError(f"could not geocode city: {city}")
    hit = rows[0]
    return {
        "lat": float(hit["lat"]),
        "lon": float(hit["lon"]),
        "display_name": hit.get("display_name") or city,
    }


def search_trade(trade: str, city: str, limit: int, fetch=_get) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "q": f"{trade} {city}",
            "format": "jsonv2",
            "limit": max(limit * 2, 10),
            "addressdetails": 1,
            "extratags": 1,
        }
    )
    rows = json.loads(fetch(f"{NOMINATIM_SEARCH}?{query}").decode("utf-8"))
    kept = []
    for row in rows:
        if (row.get("class") or "") in SKIP_CLASSES:
            continue
        if not (row.get("display_name") or row.get("name")):
            continue
        kept.append(row)
        if len(kept) >= limit:
            break
    return kept


def lookup_osm(ids: list[str], fetch=_get) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    query = urllib.parse.urlencode(
        {"osm_ids": ",".join(ids), "format": "json", "addressdetails": 1, "extratags": 1}
    )
    rows = json.loads(fetch(f"{NOMINATIM_LOOKUP}?{query}").decode("utf-8"))
    out = {}
    for row in rows:
        prefix = {"node": "N", "way": "W", "relation": "R"}.get(row.get("osm_type"), "")
        osm_id = row.get("osm_id")
        if prefix and osm_id:
            out[f"{prefix}{osm_id}"] = row
    return out


def _osm_code(row: dict[str, Any]) -> str | None:
    kind = (row.get("osm_type") or "")[:1].upper()
    osm_id = row.get("osm_id")
    if kind in {"N", "W", "R"} and osm_id:
        return f"{kind}{osm_id}"
    return None


def _name(row: dict[str, Any]) -> str:
    named = (row.get("namedetails") or {}).get("name") if isinstance(row.get("namedetails"), dict) else None
    display = row.get("display_name") or ""
    short = display.split(",")[0].strip() if display else ""
    return (row.get("name") or named or short).strip()


def vendor_from_nominatim(row: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
    extra_tags = (extra or row).get("extratags") or row.get("extratags") or {}
    address = (extra or row).get("address") or row.get("address") or {}
    name = _name(extra or row) or _name(row)
    if not name:
        return None
    osm_type = row.get("osm_type")
    osm_id = row.get("osm_id")
    phone = extra_tags.get("phone") or extra_tags.get("contact:phone")
    website = extra_tags.get("website") or extra_tags.get("contact:website") or extra_tags.get("url")
    email = extra_tags.get("email") or extra_tags.get("contact:email")
    line = " ".join(p for p in [address.get("house_number"), address.get("road")] if p)
    city_line = ", ".join(
        p for p in [line, address.get("city") or address.get("town") or address.get("village"), address.get("state"), address.get("postcode")] if p
    )
    return {
        "name": name,
        "phone": phone,
        "website": website,
        "email": email,
        "address": city_line or None,
        "lat": float(row["lat"]) if row.get("lat") else None,
        "lon": float(row["lon"]) if row.get("lon") else None,
        "osm_id": f"{osm_type}/{osm_id}" if osm_type and osm_id else None,
        "source": f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_type and osm_id else None,
    }


def build_overpass_query(lat: float, lon: float, trade: str, radius_m: int = DEFAULT_RADIUS_M) -> str:
    regex = patterns_for(trade)
    return (
        f"[out:json][timeout:25];"
        f"("
        f'nwr(around:{radius_m},{lat},{lon})["name"~"{regex}",i];'
        f'nwr(around:{radius_m},{lat},{lon})["craft"~"{regex}",i];'
        f'nwr(around:{radius_m},{lat},{lon})["shop"~"{regex}",i];'
        f'nwr(around:{radius_m},{lat},{lon})["office"~"{regex}",i];'
        f");"
        f"out center tags 60;"
    )


def _address(tags: dict[str, Any]) -> str:
    parts = [
        " ".join(p for p in [tags.get("addr:housenumber"), tags.get("addr:street")] if p),
        tags.get("addr:city"),
        tags.get("addr:state"),
        tags.get("addr:postcode"),
    ]
    return ", ".join(p for p in parts if p)


def vendor_from_element(element: dict[str, Any]) -> dict[str, Any] | None:
    tags = element.get("tags") or {}
    name = (tags.get("name") or "").strip()
    if not name:
        return None
    lat = element.get("lat") or (element.get("center") or {}).get("lat")
    lon = element.get("lon") or (element.get("center") or {}).get("lon")
    phone = tags.get("phone") or tags.get("contact:phone")
    website = tags.get("website") or tags.get("contact:website")
    email = tags.get("email") or tags.get("contact:email")
    osm_type = element.get("type")
    osm_id = element.get("id")
    source = f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_type and osm_id else None
    return {
        "name": name,
        "phone": phone,
        "website": website,
        "email": email,
        "address": _address(tags) or None,
        "lat": lat,
        "lon": lon,
        "osm_id": f"{osm_type}/{osm_id}" if osm_type and osm_id else None,
        "source": source,
    }


def parse_overpass(payload: dict[str, Any], max_results: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    vendors: list[dict[str, Any]] = []
    for element in payload.get("elements") or []:
        vendor = vendor_from_element(element)
        if not vendor:
            continue
        key = vendor["osm_id"] or vendor["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        vendors.append(vendor)
        if len(vendors) >= max_results:
            break
    return vendors


def find_vendors(
    trade: str,
    city: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    *,
    geocode=geocode_city,
    search=search_trade,
    lookup=lookup_osm,
    overpass_fetch=None,
) -> dict[str, Any]:
    trade = (trade or "").strip()
    city = (city or "").strip()
    if not trade or not city:
        raise ValueError("trade and city are required")
    max_results = clamp_max_results(max_results)
    live = search is search_trade
    place = geocode(city)
    if live:
        time.sleep(1.05)
    hits = search(trade, city, max_results)
    missing = [code for row in hits if not row.get("extratags") for code in [_osm_code(row)] if code]
    if live and missing:
        time.sleep(1.05)
    extras = lookup(missing) if missing else {}
    vendors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in hits:
        code = _osm_code(row)
        vendor = vendor_from_nominatim(row, extras.get(code) if code else None)
        if not vendor:
            continue
        key = vendor["osm_id"] or vendor["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        vendors.append(vendor)
        if len(vendors) >= max_results:
            break
    provider = "openstreetmap-nominatim"
    if len(vendors) < max(1, max_results // 2) and overpass_fetch is not None:
        query = build_overpass_query(place["lat"], place["lon"], trade)
        payload = json.loads(overpass_fetch(query).decode("utf-8"))
        for vendor in parse_overpass(payload, max_results):
            key = vendor["osm_id"] or vendor["name"].lower()
            if key in seen:
                continue
            seen.add(key)
            vendors.append(vendor)
            provider = "openstreetmap-nominatim+overpass"
            if len(vendors) >= max_results:
                break
    return {
        "trade": trade,
        "city": city,
        "geocoded": place["display_name"],
        "count": len(vendors),
        "vendors": vendors[:max_results],
        "provider": provider,
    }
