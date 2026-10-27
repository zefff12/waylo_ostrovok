"""Подбор транспорта туда-обратно. Реальные цены — только из Travelpayouts, остальное помечено."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import integrations
from .data import CITIES, RAIL_HOURS_OVERRIDE, City
from .geo import km
from .schemas import Explanation, Leg, TransportOption, TripParams


def rail_hours(a: City, b: City) -> float | None:
    if not (a.rail and b.rail and a.domestic and b.domestic and a.station and b.station):
        return None
    if (o := RAIL_HOURS_OVERRIDE.get(frozenset({a.id, b.id}))) is not None:
        return o
    d = km(a.lat, a.lon, b.lat, b.lon) * 1.25
    return round(d / 70, 1) if d < 2600 else None


def flight_hours(a: City, b: City) -> float:
    return round(km(a.lat, a.lon, b.lat, b.lon) / 750 + 0.6, 1)


def door_to_door(mode: str, hours: float) -> float:
    # самолёт: дорога в аэропорт, регистрация, получение багажа; поезд: дорога на вокзал
    return round(hours + (3.0 if mode == "plane" else 1.0), 1)


def _dt(d: date, hm: str) -> datetime:
    h, m = map(int, hm.split(":"))
    return datetime(d.year, d.month, d.day, h, m)


def _train_option(o: City, d: City, start: date, end: date, p: TripParams, hours: float, variant: str) -> TransportOption:
    dist = km(o.lat, o.lon, d.lat, d.lon) * 1.25
    night = hours > 7
    if hours <= 4.5:
        name, out_time, back_time, carrier = "Скоростной поезд", ("07:00" if variant == "a" else "09:40"), "19:00", "ФПК / ДОСС"
        per_dir = round((1800 + dist * 3.2) / 100) * 100 if variant == "a" else round((1500 + dist * 2.6) / 100) * 100
    elif night:
        name, out_time, back_time, carrier = ("Ночной поезд, купе" if variant == "a" else "Ночной поезд, плацкарт"), "21:30", "21:00", "ФПК"
        per_dir = round((1500 + dist * (2.4 if variant == "a" else 1.3)) / 100) * 100
    else:
        name, out_time, back_time, carrier = "Дневной поезд", "08:15", "15:30", "ФПК"
        per_dir = round((1200 + dist * 2.0) / 100) * 100
    dur = round(hours * 60)
    # прибытие — в день начала поездки; ночной поезд выезжает накануне
    depart_out = _dt(start - timedelta(days=1) if night else start, out_time)
    arrive_out = depart_out + timedelta(minutes=dur)
    depart_back = _dt(end, back_time)
    arrive_back = depart_back + timedelta(minutes=dur)
    people = p.travelers
    price_pp = per_dir * 2
    expl = Explanation(
        why=[f"{'Ночь в поезде экономит ночь в отеле' if night else 'Из центра в центр, без аэропортов'}",
             f"В пути {hours:g} ч"],
        tradeoffs=(["Купе дороже плацкарта"] if variant == "a" and night else
                   ["Меньше комфорта, чем в купе"] if night else []),
        risks=["Цена и наличие мест — оценка: открытого API РЖД нет, проверьте перед покупкой"],
    )
    return TransportOption(
        id=f"train_{variant}", mode="train", title=f"{name}: {o.name} → {d.name}",
        outbound=Leg(from_name=o.station.name, to_name=d.station.name, depart=depart_out.isoformat(),
                     arrive=arrive_out.isoformat(), duration_min=dur, carrier=carrier),
        inbound=Leg(from_name=d.station.name, to_name=o.station.name, depart=depart_back.isoformat(),
                    arrive=arrive_back.isoformat(), duration_min=dur, carrier=carrier),
        price_per_person=price_pp, price_total=price_pp * people,
        kind="demo", source="Расчёт Waylo по расстоянию (демо-тариф, не РЖД)",
        pets_allowed=True, door_to_door_hours=door_to_door("train", hours), explanation=expl,
    )


def _flight_from_api(o: City, d: City, start: date, end: date, p: TripParams, rows: list[dict]) -> list[TransportOption]:
    out = []
    for i, r in enumerate(rows[:2]):
        try:
            dep = datetime.fromisoformat(r["departure_at"]).replace(tzinfo=None)
            ret = datetime.fromisoformat(r["return_at"]).replace(tzinfo=None)
        except (KeyError, ValueError):
            continue
        dur_to = int(r.get("duration_to") or flight_hours(o, d) * 60)
        dur_back = int(r.get("duration_back") or dur_to)
        price = int(r["price"])
        transfers = int(r.get("transfers") or 0)
        num = f"{r.get('airline', '')}{r.get('flight_number', '')}" or None
        out.append(TransportOption(
            id=f"plane_api_{i}", mode="plane",
            title=f"Перелёт {o.name} → {d.name}" + (" (с пересадкой)" if transfers else " (прямой)"),
            outbound=Leg(from_name=o.airport.name, to_name=d.airport.name, depart=dep.isoformat(),
                         arrive=(dep + timedelta(minutes=dur_to)).isoformat(), duration_min=dur_to,
                         carrier=r.get("airline", "?"), number=num),
            inbound=Leg(from_name=d.airport.name, to_name=o.airport.name, depart=ret.isoformat(),
                        arrive=(ret + timedelta(minutes=dur_back)).isoformat(), duration_min=dur_back,
                        carrier=r.get("airline", "?")),
            price_per_person=price, price_total=price * p.travelers, kind="estimate",
            source="Travelpayouts / Aviasales — цена из кэша поисков, наличие не гарантировано",
            pets_allowed=False, transfers=transfers, door_to_door_hours=door_to_door("plane", dur_to / 60),
            explanation=Explanation(
                why=["Реальная цена из недавних поисков Aviasales", f"В воздухе {dur_to // 60} ч {dur_to % 60} мин"],
                tradeoffs=["Нужно ехать в аэропорт и приезжать заранее"] + (["Есть пересадка"] if transfers else []),
                risks=["Цена из кэша могла измениться", "Животные — по правилам авиакомпании, уточняйте"],
            ),
        ))
    return out


def _flight_estimate(o: City, d: City, start: date, end: date, p: TripParams) -> TransportOption:
    hours = flight_hours(o, d)
    dist = km(o.lat, o.lon, d.lat, d.lon)
    per_dir = round((3500 + dist * 4.2) / 100) * 100
    dur = round(hours * 60)
    dep = _dt(start, "08:30")
    ret = _dt(end, "18:30")
    return TransportOption(
        id="plane_est", mode="plane", title=f"Перелёт {o.name} → {d.name} (оценка)",
        outbound=Leg(from_name=o.airport.name, to_name=d.airport.name, depart=dep.isoformat(),
                     arrive=(dep + timedelta(minutes=dur)).isoformat(), duration_min=dur, carrier="авиакомпания — демо"),
        inbound=Leg(from_name=d.airport.name, to_name=o.airport.name, depart=ret.isoformat(),
                    arrive=(ret + timedelta(minutes=dur)).isoformat(), duration_min=dur, carrier="авиакомпания — демо"),
        price_per_person=per_dir * 2, price_total=per_dir * 2 * p.travelers, kind="demo",
        source="Оценка Waylo по расстоянию (добавьте TRAVELPAYOUTS_TOKEN для реальных цен)",
        pets_allowed=False, door_to_door_hours=door_to_door("plane", hours),
        explanation=Explanation(
            why=[f"Быстро: {hours:g} ч в воздухе"],
            tradeoffs=["Дорога в аэропорт и регистрация добавляют ~3 ч"],
            risks=["Цена и расписание — демо-оценка", "Животные — по правилам авиакомпании"],
        ),
    )


def search_transport(p: TripParams) -> list[TransportOption]:
    o, d = CITIES[p.origin], CITIES[p.destination]  # type: ignore[index]
    start = date.fromisoformat(p.start_date)  # type: ignore[arg-type]
    end = start + timedelta(days=p.nights or 0)
    options: list[TransportOption] = []
    if (rh := rail_hours(o, d)) is not None and rh <= 30:
        options.append(_train_option(o, d, start, end, p, rh, "a"))
        options.append(_train_option(o, d, start, end, p, rh, "b"))
    if (o.has_airport and d.has_airport) or not options:  # без аэропорта самолёт — только если поезда нет совсем
        rows = integrations.flight_prices(o.iata, d.iata, start, end)
        api = _flight_from_api(o, d, start, end, p, rows) if rows else []
        options.extend(api or [_flight_estimate(o, d, start, end, p)])
    return rank_transport(options, p)


def rank_transport(options: list[TransportOption], p: TripParams) -> list[TransportOption]:
    if not options:
        return options
    cheapest = min(o.price_total for o in options)
    fastest = min(o.door_to_door_hours for o in options)
    for o in options:
        price_score = cheapest / o.price_total
        time_score = fastest / o.door_to_door_hours
        w_price = 0.65 if p.priority == "price" or "cheap" in p.wishes else 0.45
        s = w_price * price_score + (1 - w_price) * time_score
        if p.transport_pref != "any" and o.mode != p.transport_pref:
            s -= 0.5
        if p.pets and not o.pets_allowed:
            s -= 0.4
        if p.children and o.door_to_door_hours > 8:
            s -= 0.1
        if p.max_travel_hours and o.door_to_door_hours - (3 if o.mode == "plane" else 1) > p.max_travel_hours:
            s -= 0.3
        o.score = round(s * 100, 1)
    options.sort(key=lambda o: -o.score)
    return options
