"""City + trade -> local businesses from OpenStreetMap."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


USER_AGENT = "FindLocalVendors/1.0 (https://find-local-vendors.agathodamon.com)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_RADIUS_M = 25000
DEFAULT_MAX_RESULTS = 10
HARD_MAX_RESULTS = 25

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
    rows = json.loads(fetch(f"{NOMINATIM_URL}?{query}").decode("utf-8"))
    if not rows:
        raise ValueError(f"could not geocode city: {city}")
    hit = rows[0]
    return {
        "lat": float(hit["lat"]),
        "lon": float(hit["lon"]),
        "display_name": hit.get("display_name") or city,
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
    overpass_fetch=None,
) -> dict[str, Any]:
    trade = (trade or "").strip()
    city = (city or "").strip()
    if not trade or not city:
        raise ValueError("trade and city are required")
    max_results = clamp_max_results(max_results)
    place = geocode(city)
    query = build_overpass_query(place["lat"], place["lon"], trade)
    fetch = overpass_fetch or (lambda q: _post(OVERPASS_URL, "data=" + urllib.parse.quote(q)))
    payload = json.loads(fetch(query).decode("utf-8"))
    vendors = parse_overpass(payload, max_results)
    return {
        "trade": trade,
        "city": city,
        "geocoded": place["display_name"],
        "count": len(vendors),
        "vendors": vendors,
        "provider": "openstreetmap",
    }
