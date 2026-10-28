from __future__ import annotations

import json
import math
import random
import re
from functools import lru_cache
from pathlib import Path

from .data import City
from .geo import km
from .schemas import Explanation, Hotel, TripParams

PREFIXES = ["Отель", "Апарт-отель", "Бутик-отель", "Мини-отель", "Хостел", "Гостиница"]
NAMES = ["Северная звезда", "Тихий двор", "Набережная", "Старый город", "Лофт 12", "Панорама", "Сад", "Маяк", "Квартал"]
CANCEL_TEXT = {
    "free": "Бесплатная отмена за 24 ч до заезда",
    "partial": "При отмене удерживается стоимость первой ночи",
    "non_refundable": "Невозвратный тариф",
}
MEALS_TEXT = {"none": "без питания", "breakfast": "завтрак включён", "half_board": "завтрак и ужин"}
TYPE_RU = {"hotel": "Отель", "hostel": "Хостел", "guest_house": "Гостевой дом", "apartment": "Апартаменты"}
LUXURY = re.compile(r"hilton|marriott|hyatt|ritz|four seasons|kempinski|waldorf|corinthia|radisson collection|"
                    r"intercontinental|st\. regis|mandarin|rixos|jumeirah|националь|астория|metropol|метрополь", re.I)
STAR_K = {1: 0.3, 2: 0.45, 3: 0.85, 4: 1.3, 5: 2.3}
OSM_FILE = Path(__file__).with_name("hotels_osm.json")
MIN_REAL = 5


@lru_cache(maxsize=1)
def _snapshot() -> dict:
    try:
        return json.loads(OSM_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"cities": {}}


def _readable(name: str) -> bool:
    return bool(re.search(r"[a-zA-Zа-яА-ЯёЁ]", name))


def _pick(items: list[dict], focus: tuple[float, float]) -> list[dict]:
    for h in items:
        h["_d"] = km(h["lat"], h["lon"], *focus)
    by_d = sorted(items, key=lambda h: h["_d"])
    groups = [
        by_d[:6],
        [h for h in by_d if h["type"] == "hostel"][:2],
        [h for h in by_d if h["type"] in ("guest_house", "apartment")][:2],
        [h for h in by_d if 2 <= h["_d"] <= 6 and h["type"] == "hotel"][:2],
    ]
    out, seen = [], set()
    for g in groups:
        for h in g:
            if h["osm"] not in seen:
                seen.add(h["osm"])
                out.append(h)
    return out[:12]


def _price(city: City, p: TripParams, stars: int, kind: str, dist: float, meals: str, cancel: str,
           rnd: random.Random) -> int:
    k = 0.35 if kind == "hostel" else STAR_K[stars] * (0.9 if kind in ("apartment", "guest_house") else 1)
    base = city.hotel_level * k
    base *= 1.25 - min(dist, 4) * 0.08
    base *= {"none": 1.0, "breakfast": 1.12, "half_board": 1.3}[meals]
    base *= {"free": 1.08, "partial": 1.0, "non_refundable": 0.88}[cancel]
    if "sea" in city.tags and p.month:
        base *= 1.3 if 6 <= p.month <= 9 else 0.85 if p.month in (11, 12, 1, 2, 3) else 1.0
    if p.travelers > 2:
        base *= 1 + 0.35 * (p.travelers - 2)
    base *= rnd.uniform(0.9, 1.1)
    return int(round(base / 100) * 100)


def generate(city: City, p: TripParams, focus: tuple[float, float] | None = None) -> list[Hotel]:
    focus = focus or (city.lat, city.lon)
    snap = _snapshot()
    real = [dict(h) for h in snap["cities"].get(city.id, []) if _readable(h["name"])]
    hotels = [_from_osm(city, p, h, snap.get("fetched", "")) for h in _pick(real, focus)]
    if len(hotels) < MIN_REAL:
        hotels += _demo(city, p, 9 - len(hotels))
    return hotels


def _from_osm(city: City, p: TripParams, h: dict, fetched: str) -> Hotel:
    rnd = random.Random(f"waylo-{h['osm']}")
    kind = h["type"]
    stars = h["stars"] or (5 if LUXURY.search(h["name"]) else {"hostel": 2, "guest_house": 3, "apartment": 3}.get(kind, 3))
    meals = rnd.choice(["none", "breakfast", "breakfast", "half_board"] if stars >= 4 else ["none", "none", "breakfast"])
    if kind in ("hostel", "apartment"):
        meals = "none"
    cancel = rnd.choice(["free", "free", "partial", "non_refundable"])
    price = _price(city, p, stars, kind, h["_d"], meals, cancel, rnd)
    name = h["name"]
    if kind != "hotel" and not re.match(r"(?i)(отель|хостел|гостиниц|гостев|апарт|мини|hotel|hostel|otel)", name):
        name = f"{TYPE_RU[kind]} «{name}»"
    nights = p.nights or 1
    return Hotel(
        id="osm_" + h["osm"].replace("/", "_"), name=name, lat=h["lat"], lon=h["lon"],
        district=h["address"] or f"{h['center_km']:.1f} км от центра", stars=stars,
        rating=round(rnd.uniform(7.6, 9.5) if stars >= 3 else rnd.uniform(7.0, 8.8), 1),
        price_per_night=price, nights=nights, total=price * nights,
        cancellation=cancel, cancellation_text=CANCEL_TEXT[cancel], meals=meals,
        pets_allowed=h["pets"] if h["pets"] is not None else rnd.random() < 0.4,
        kids_friendly=kind != "hostel" and rnd.random() < 0.8,
        checkin="14:00" if kind != "hostel" else "13:00", checkout="12:00",
        early_checkin_price=int(round(price * 0.5 / 100) * 100),
        distance_center_km=round(h["_d"], 1), kind="estimate",
        source=f"OpenStreetMap ({fetched}): название, адрес, координаты; цена — оценка Waylo",
        website=h["website"] if re.match(r"https?://", h["website"] or "") else None, osm_url=f"https://www.openstreetmap.org/{h['osm']}",
        facts={"name": "confirmed", "location": "confirmed",
               "stars": "confirmed" if h["stars"] else "estimate",
               "price": "estimate", "cancellation": "demo", "meals": "demo", "rating": "demo",
               "pets": "confirmed" if h["pets"] is not None else "demo", "kids": "demo"},
    )


def _demo(city: City, p: TripParams, count: int) -> list[Hotel]:
    rnd = random.Random(f"waylo-{city.id}")
    hotels: list[Hotel] = []
    nights = p.nights or 1
    for i in range(count):
        prefix = PREFIXES[i % len(PREFIXES)]
        stars = {"Хостел": 2, "Мини-отель": 3, "Гостиница": 3, "Апарт-отель": 3, "Отель": 4, "Бутик-отель": 4}[prefix]
        dist = round(rnd.uniform(0.3, 4.5) if i % 3 else rnd.uniform(0.2, 1.4), 1)
        ang = rnd.uniform(0, 6.283)
        dlat = dist / 111 * 0.8 * math.sin(ang)
        dlon = dist / (111 * 0.55) * 0.8 * math.cos(ang)
        meals = rnd.choice(["none", "breakfast", "breakfast", "half_board"] if stars >= 4 else ["none", "none", "breakfast"])
        cancel = rnd.choice(["free", "free", "partial", "non_refundable"])
        price = _price(city, p, stars, "hostel" if prefix == "Хостел" else "hotel", dist, meals, cancel, rnd)
        hotels.append(Hotel(
            id=f"h{i}", name=f"{prefix} «{NAMES[i % len(NAMES)]}»",
            lat=round(city.lat + dlat, 5), lon=round(city.lon + dlon, 5),
            district=city.districts[i % len(city.districts)], stars=stars,
            rating=round(rnd.uniform(7.6, 9.6) if stars >= 3 else rnd.uniform(7.0, 8.8), 1),
            price_per_night=price, nights=nights, total=price * nights,
            cancellation=cancel, cancellation_text=CANCEL_TEXT[cancel], meals=meals,
            pets_allowed=rnd.random() < 0.4, kids_friendly=stars >= 3 and rnd.random() < 0.75,
            checkin="14:00" if prefix != "Хостел" else "13:00", checkout="12:00",
            early_checkin_price=int(round(price * 0.5 / 100) * 100),
            distance_center_km=dist,
        ))
    return hotels


def rank(hotels: list[Hotel], p: TripParams, focus: tuple[float, float]) -> list[Hotel]:
    pool = [h for h in hotels if (not p.pets or h.pets_allowed) and (not p.children or h.kids_friendly)]
    if not pool:
        pool = hotels
    w = {"price": 0.35, "location": 0.3, "cancel": 0.15, "rating": 0.15, "meals": 0.05}
    if p.priority == "price" or "cheap" in p.wishes:
        w.update(price=0.5, location=0.2, cancel=0.1, rating=0.15)
    if p.priority == "location" or "center" in p.wishes or p.walking == "low":
        w.update(price=0.25, location=0.45)
    if p.priority == "cancellation":
        w.update(cancel=0.35, price=0.25, location=0.2)
    nightly_budget = None
    if p.budget_rub and p.nights:
        nightly_budget = p.budget_rub * 0.45 / p.nights
    cheapest = min(h.total for h in pool)
    for h in pool:
        d_focus = km(h.lat, h.lon, *focus)
        h.distance_center_km = round(d_focus, 1)
        s_price = cheapest / h.total
        s_loc = max(0.0, 1 - d_focus / 5)
        s_cancel = {"free": 1, "partial": 0.5, "non_refundable": 0}[h.cancellation]
        s_rating = (h.rating - 6.5) / 3.5
        s_meals = {"none": 0.3, "breakfast": 1, "half_board": 0.8}[h.meals]
        score = (w["price"] * s_price + w["location"] * s_loc + w["cancel"] * s_cancel
                 + w["rating"] * s_rating + w["meals"] * s_meals)
        if nightly_budget and h.price_per_night > nightly_budget * 1.3:
            score -= 0.15
        if h.stars <= 2 and p.priority != "price" and "cheap" not in p.wishes:
            score -= 0.12
        h.score = round(score * 100, 1)
        h.explanation = _explain(h, p, d_focus, pool, nightly_budget)
    pool.sort(key=lambda h: -h.score)
    return pool


def _explain(h: Hotel, p: TripParams, d_focus: float, pool: list[Hotel], nightly_budget: float | None) -> Explanation:
    why, trade, risks = [], [], []
    walk = round(d_focus * 1.3 / 4.5 * 60)
    if d_focus <= 1.2:
        why.append(f"До главных мест ~{walk} мин пешком")
    elif d_focus <= 3:
        trade.append(f"До главных мест {walk} мин пешком или ~15 мин на транспорте")
    else:
        trade.append(f"Далеко от главных мест: {d_focus:.1f} км, понадобится транспорт каждый день")
    if h.total == min(x.total for x in pool):
        why.append("Самый дешёвый вариант из подходящих")
    if h.cancellation == "free":
        why.append("Бесплатная отмена — можно передумать")
    elif h.cancellation == "non_refundable":
        trade.append("Невозвратный тариф — дешевле, но деньги не вернуть")
        risks.append("При смене планов теряется вся сумма")
    else:
        risks.append("При отмене удержат первую ночь")
    if h.meals != "none":
        why.append(MEALS_TEXT[h.meals].capitalize())
    else:
        trade.append("Питание не включено")
    if h.rating >= 9:
        why.append(f"Высокий рейтинг {h.rating} (демо)")
    if p.pets:
        (why if h.pets_allowed else risks).append("Можно с животными" if h.pets_allowed else "Животные не разрешены")
        if h.facts.get("pets") == "demo":
            risks.append("Правила для животных в открытых данных не указаны — уточните в отеле")
    if p.children and h.kids_friendly:
        why.append("Подходит для детей")
    if nightly_budget and h.price_per_night > nightly_budget * 1.3:
        risks.append("Дороже ориентира по бюджету на жильё")
    if h.kind == "estimate":
        risks.append("Отель реальный, но цена — оценка: наличие номеров и тариф не проверены")
    else:
        risks.append("Отель вымышленный, цены и наличие синтетические (демо)")
    return Explanation(why=why, tradeoffs=trade, risks=risks)
