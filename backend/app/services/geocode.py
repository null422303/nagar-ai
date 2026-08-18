"""Geocoding + POI lookup (Chennai). Uses Nominatim + Overpass, cached in SQLite."""
import asyncio
import time
from typing import Optional

import httpx
from app.core.config import settings
from app.models import store


_NOISE_SUFFIXES = [" near school", " school kitta", " near hospital", " near bus stop",
                   " opposite", " side", " road", " street", " street corner", " junction",
                   " near market", " near temple", " in front of"]

_NUM_WORDS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th",
    "sixth": "6th", "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th",
    "one": "1st", "two": "2nd", "three": "3rd", "four": "4th", "five": "5th",
    "six": "6th", "seven": "7th", "eight": "8th", "nine": "9th", "ten": "10th",
}


def _clean_query(text: str) -> str:
    t = text.strip().lower()
    for suf in sorted(_NOISE_SUFFIXES, key=len, reverse=True):
        t = t.replace(suf, "")
    for suf in sorted(_NOISE_SUFFIXES, key=len, reverse=True):
        t = t.replace(suf.strip(), "")
    words = t.split()
    t = " ".join(_NUM_WORDS.get(w, w) for w in words)
    t = " ".join(t.split())
    if not t:
        t = text
    if "chennai" not in t:
        t = f"{t}, Chennai"
    return t


async def _try_queries(queries: list) -> Optional[dict]:
    for attempt, q in enumerate(queries):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get("https://nominatim.openstreetmap.org/search", params={
                    "q": q, "format": "json", "limit": 1, "countrycodes": "in",
                    "viewbox": "79.9,13.4,80.5,12.8", "bounded": 1,
                }, headers={"User-Agent": "NagarAI-hackathon/1.0 (hackathon)"})
                if r.status_code == 200 and r.json():
                    item = r.json()[0]
                    return {"lat": float(item["lat"]), "lng": float(item["lon"]), "name": item["display_name"]}
                if r.status_code in (429, 403, 302):
                    await asyncio.sleep(1.5 * (attempt + 1))
        except Exception:
            await asyncio.sleep(1.0 * (attempt + 1))
    return None


async def geocode_text(text: str) -> Optional[dict]:
    """Text mention -> {lat, lng, name}. Nominatim with Chennai bias + variant fallback."""
    base = _clean_query(text)
    queries = [base]
    # fallback: drop street-level qualifiers that break resolution
    stripped = base
    for token in (" avenue", " road", " street", " lane", " main road"):
        alt = stripped.replace(token, "")
        if alt != stripped and alt.strip():
            queries.append(alt.strip())
    queries = list(dict.fromkeys(queries))[:4]
    return await _try_queries(queries)


async def nearby_schools_hospitals(lat: float, lng: float, radius_m: float = 100.0) -> list:
    """Overpass: schools/hospitals within radius. Cached per rounded (lat,lng)."""
    cached = store.get_pois(lat, lng)
    if cached:
        return cached
    # no cache row -> fetch (rounded to grid so nearby complaints share cache)
    rlat, rlng = round(lat, 4), round(lng, 4)
    bbox = (rlng - 0.002, rlat - 0.002, rlng + 0.002, rlat + 0.002)
    query = f"""
    [out:json][timeout:10];
    (
      node["amenity"~"^(school|hospital)$"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
      way["amenity"~"^(school|hospital)$"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
    );
    out center;
    """
    pois = []
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.post("https://overpass-api.de/api/interpreter",
                                  data={"data": query}, headers={"User-Agent": "NagarAI-hackathon"})
            if r.status_code == 200:
                from app.engines.dedup import haversine_m
                for el in r.json().get("elements", []):
                    clat = el.get("lat") or el.get("center", {}).get("lat")
                    clng = el.get("lon") or el.get("center", {}).get("lon")
                    if clat and clng and haversine_m(lat, lng, clat, clng) <= radius_m:
                        tags = el.get("tags", {})
                        kind = "school" if "school" in tags.get("amenity", "") else "hospital"
                        pois.append({"name": tags.get("name") or kind, "kind": kind})
    except Exception:
        pass
    store.put_pois(lat, lng, pois)
    return pois
