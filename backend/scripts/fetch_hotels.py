from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import integrations
from app.data import CITIES
from app.geo import km

MIRRORS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
RADIUS_M = 5000
PER_CITY = 60
OUT = Path(__file__).resolve().parent.parent / "app" / "hotels_osm.json"


def query(lat: float, lon: float) -> list[dict]:
    q = (f'[out:json][timeout:60];nwr["tourism"~"^(hotel|hostel|guest_house|apartment)$"]["name"]'
         f'(around:{RADIUS_M},{lat},{lon});out center tags 1500;')
    for url in MIRRORS:
        try:
            r = httpx.post(url, data={"data": q}, timeout=90, headers={"User-Agent": "Waylo-hackathon-MVP/0.1"})
            r.raise_for_status()
            return r.json()["elements"]
        except (httpx.HTTPError, ValueError, KeyError) as e:
            print(f"  {url}: {type(e).__name__}")
    return []


def convert(el: dict, city_lat: float, city_lon: float) -> dict | None:
    t = el.get("tags", {})
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    name = t.get("name:ru") or t.get("name")
    if lat is None or not name:
        return None
    stars = t.get("stars", "")
    pets = t.get("pets") or t.get("dog")
    return {
        "osm": f"{el['type']}/{el['id']}",
        "name": name.strip(),
        "type": t["tourism"],
        "lat": round(lat, 6), "lon": round(lon, 6),
        "stars": int(stars[0]) if stars[:1].isdigit() and 1 <= int(stars[0]) <= 5 else None,
        "website": t.get("website") or t.get("contact:website"),
        "address": " ".join(filter(None, [t.get("addr:street"), t.get("addr:housenumber")])) or None,
        "pets": {"yes": True, "no": False}.get(pets or ""),
        "rooms": int(t["rooms"]) if t.get("rooms", "").isdigit() else None,
        "center_km": round(km(lat, lon, city_lat, city_lon), 2),
    }


def geocode() -> None:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    data = json.loads(OUT.read_text(encoding="utf-8"))
    done = failed = 0
    for hs in data["cities"].values():
        for h in hs:
            if h["address"]:
                continue
            if addr := integrations.yandex_address(h["lat"], h["lon"]):
                h["address"], h["address_source"] = addr, "Яндекс Геокодер"
                done += 1
            else:
                failed += 1
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"адресов добавлено: {done}, не найдено: {failed}")


def main() -> None:
    if sys.argv[1:] == ["--geocode"]:
        return geocode()
    only = set(sys.argv[1:])
    out: dict = {"fetched": date.today().isoformat(), "source": "OpenStreetMap (Overpass API)", "cities": {}}
    if only and OUT.exists():
        out["cities"] = json.loads(OUT.read_text(encoding="utf-8"))["cities"]
    for c in CITIES.values():
        if only and c.id not in only:
            continue
        print(c.id, end=" ", flush=True)
        items = [h for el in query(c.lat, c.lon) if (h := convert(el, c.lat, c.lon))]
        seen, uniq = set(), []
        for h in items:
            if h["name"].lower() not in seen:
                seen.add(h["name"].lower())
                uniq.append(h)
        uniq.sort(key=lambda h: (-(bool(h["website"]) + bool(h["stars"]) + bool(h["address"])), h["center_km"]))
        if not uniq and out["cities"].get(c.id):
            print("пусто, оставляем прошлую выгрузку")
            continue
        out["cities"][c.id] = uniq[:PER_CITY]
        print(len(items), "→", len(out["cities"][c.id]))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", OUT)


if __name__ == "__main__":
    main()
