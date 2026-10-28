from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta

import httpx

log = logging.getLogger("waylo.integrations")

_cache: dict[str, tuple[float, object]] = {}
_status: dict[str, str] = {}
TTL = 3600


def _get(name: str, url: str, params: dict, timeout: float = 8.0) -> dict | list | None:
    key = url + repr(sorted(params.items()))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    if name == "overpass" and any(k.startswith("https://overpass") and v[1] is None and time.time() - v[0] < TTL
                                  for k, v in _cache.items()):
        return None
    try:
        r = httpx.get(url, params=params, timeout=timeout, headers={"User-Agent": "Waylo-hackathon-MVP/0.1"})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        _status[name] = f"ошибка: {type(e).__name__}"
        log.warning("%s failed: %s", name, e)
        _cache[key] = (time.time() - TTL + 300, None)
        return None
    _status[name] = "ok"
    _cache[key] = (time.time(), data)
    return data


def status() -> dict:
    return {
        "anthropic": "ключ задан" if os.getenv("ANTHROPIC_API_KEY") else "нет ключа",
        "gigachat": "ключ задан" if os.getenv("GIGACHAT_CREDENTIALS") else "нет ключа",
        "open_meteo": _status.get("open_meteo", "не вызывался"),
        "travelpayouts": ("токен задан, " + _status.get("travelpayouts", "не вызывался"))
        if os.getenv("TRAVELPAYOUTS_TOKEN") else "нет токена — оценки перелётов",
        "dgis": ("ключ задан, " + _status.get("dgis", "не вызывался")) if os.getenv("DGIS_API_KEY") else "нет ключа",
        "overpass": _status.get("overpass", "не вызывался"),
        "yandex_maps": "ключ задан (карта и геокодер)" if os.getenv("YANDEX_JS_API_KEY") else "нет ключа — карта OpenStreetMap",
    }


# Open-Meteo: прогноз и климат

def forecast(lat: float, lon: float, start: date, end: date) -> list[dict] | None:
    if start > date.today() + timedelta(days=15):
        return None
    data = _get("open_meteo", "https://api.open-meteo.com/v1/forecast", {
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "start_date": start.isoformat(), "end_date": min(end, date.today() + timedelta(days=15)).isoformat(),
    })
    return _daily(data)


def same_dates_last_year(lat: float, lon: float, start: date, end: date) -> list[dict] | None:
    s = start.replace(year=start.year - 1)
    e = end.replace(year=end.year - 1)
    data = _get("open_meteo", "https://archive-api.open-meteo.com/v1/archive", {
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "start_date": s.isoformat(), "end_date": e.isoformat(),
    })
    return _daily(data)


def _month_range(month: int) -> tuple[date, date]:
    today = date.today()
    year = today.year - 1 if month >= today.month else today.year
    if date(year, month, 1) > today - timedelta(days=7):
        year -= 1
    start = date(year, month, 1)
    return start, date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)


def month_climate_many(points: list[tuple[float, float]], month: int) -> list[dict | None]:
    start, end = _month_range(month)
    data = _get("open_meteo", "https://archive-api.open-meteo.com/v1/archive", {
        "latitude": ",".join(str(p[0]) for p in points), "longitude": ",".join(str(p[1]) for p in points),
        "timezone": "auto", "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "start_date": start.isoformat(), "end_date": end.isoformat(),
    }, timeout=12)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or len(data) != len(points):
        return [None] * len(points)
    return [_summarize_month(_daily(d), start) for d in data]


def month_climate(lat: float, lon: float, month: int) -> dict | None:
    return month_climate_many([(lat, lon)], month)[0]


def _summarize_month(days: list[dict] | None, start: date) -> dict | None:
    if not days:
        return None
    year = start.year
    tmax = [d["tmax"] for d in days if d["tmax"] is not None]
    tmin = [d["tmin"] for d in days if d["tmin"] is not None]
    rainy = sum(1 for d in days if (d["precip"] or 0) >= 1)
    return {
        "tmax": round(sum(tmax) / len(tmax), 1) if tmax else None,
        "tmin": round(sum(tmin) / len(tmin), 1) if tmin else None,
        "rainy_days": rainy,
        "days": len(days),
        "year": year,
        "kind": "confirmed",
        "source": f"Open-Meteo, архив за {start:%m.%Y} (климат, не прогноз)",
    }


def _daily(data) -> list[dict] | None:
    if not isinstance(data, dict) or "daily" not in data:
        return None
    d = data["daily"]
    return [
        {"date": t, "tmax": a, "tmin": b, "precip": p}
        for t, a, b, p in zip(d.get("time", []), d.get("temperature_2m_max", []),
                              d.get("temperature_2m_min", []), d.get("precipitation_sum", []))
    ]


# Travelpayouts / Aviasales: цены из кэша поисков

def flight_prices(origin: str, dest: str, depart: date, ret: date) -> list[dict] | None:
    token = os.getenv("TRAVELPAYOUTS_TOKEN")
    if not token:
        return None
    data = _get("travelpayouts", "https://api.travelpayouts.com/aviasales/v3/prices_for_dates", {
        "origin": origin, "destination": dest,
        "departure_at": depart.isoformat(), "return_at": ret.isoformat(),
        "currency": "rub", "sorting": "price", "one_way": "false", "limit": 5, "token": token,
    })
    if not isinstance(data, dict) or not data.get("success"):
        return None
    return data.get("data") or None


# Места: 2ГИС Places API или OSM Overpass

def dgis_places(query: str, lat: float, lon: float, radius_m: int = 2500, limit: int = 8) -> list[dict] | None:
    key = os.getenv("DGIS_API_KEY")
    if not key:
        return None
    data = _get("dgis", "https://catalog.api.2gis.com/3.0/items", {
        "q": query, "point": f"{lon},{lat}", "radius": radius_m, "page_size": limit,
        "fields": "items.point,items.rubrics,items.address_name", "key": key,
    })
    if not isinstance(data, dict):
        return None
    items = (data.get("result") or {}).get("items") or []
    out = []
    for it in items:
        pt = it.get("point")
        if not pt:
            continue
        out.append({"name": it.get("name"), "lat": pt["lat"], "lon": pt["lon"],
                    "address": it.get("address_name"), "source": "2ГИС Places API"})
    return out


def overpass_cafes(lat: float, lon: float, radius_m: int = 1500, limit: int = 8) -> list[dict] | None:
    q = (f'[out:json][timeout:8];node["amenity"="cafe"]["name"](around:{radius_m},{lat},{lon});'
         f'out {limit * 3};')
    data = None
    for url in ("https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter",
                "https://overpass.kumi.systems/api/interpreter"):
        data = _get("overpass", url, {"data": q}, timeout=5)
        if data is not None:
            break
    if not isinstance(data, dict):
        return None
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name:ru") or tags.get("name")
        if not name:
            continue
        out.append({"name": name, "lat": el["lat"], "lon": el["lon"],
                    "address": " ".join(filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")])),
                    "source": "OpenStreetMap (Overpass API)"})
        if len(out) >= limit:
            break
    return out


# Яндекс Геокодер: адрес по координатам

def yandex_address(lat: float, lon: float) -> str | None:
    key = os.getenv("YANDEX_JS_API_KEY")
    if not key:
        return None
    data = _get("yandex_geocoder", "https://geocode-maps.yandex.ru/1.x/", {
        "apikey": key, "geocode": f"{lon},{lat}", "kind": "house", "format": "json", "results": 1, "lang": "ru_RU",
    })
    try:
        member = data["response"]["GeoObjectCollection"]["featureMember"]
        return member[0]["GeoObject"]["name"] if member else None
    except (KeyError, TypeError, IndexError):
        return None
