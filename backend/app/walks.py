from __future__ import annotations

from datetime import date, datetime, timedelta

from .data import CITIES
from .geo import fmt_hm, hm, km, transit_minutes, walk_minutes
from .schemas import DayPlan, Place, Stop, Trip

DAY_START = "10:00"
DAY_END = "19:30"
LUNCH_FROM = 13 * 60
CAT_RU = {
    "museum": "музеи", "architecture": "архитектура", "view": "виды", "park": "парки", "cafe": "кафе",
    "history": "история", "hidden": "необычные места", "shopping": "шопинг", "theatre": "театр", "beach": "пляж",
}


def walk_limit_km(day: DayPlan) -> float:
    return 1.2 if day.less_walking else 2.0


def place_score(pl: Place, interests: list[str]) -> float:
    s = 1.0 + sum(2.0 for c in pl.cats if c in interests)
    if not interests and {"architecture", "history", "view"} & set(pl.cats):
        s += 1.0
    return s


def _leg(trip: Trip, day: DayPlan, a: tuple[float, float], b: Place) -> tuple[str, float, int, int]:
    city = CITIES[trip.params.destination]
    d = km(a[0], a[1], b.lat, b.lon)
    if d <= walk_limit_km(day):
        return "walk", round(d, 2), walk_minutes(d), 0
    return "transit", round(d, 2), transit_minutes(d), city.local_transit_rub * trip.params.travelers


def _usable(pl: Place, day: DayPlan, weekday: int) -> bool:
    if day.indoor_only and not pl.indoor:
        return False
    return weekday not in pl.closed_weekdays


def day_window(trip: Trip, day_no: int, n_days: int) -> tuple[str, str, list[str]]:
    notes: list[str] = []
    start, end = DAY_START, DAY_END
    t, h = trip.transport(), trip.hotel()
    city = CITIES[trip.params.destination]
    if t and h:
        hub = city.station if t.mode == "train" and city.station else city.airport
        transfer = round(8 + km(hub.lat, hub.lon, h.lat, h.lon) * 1.3 / 30 * 60)
        if day_no == 1:
            arrive = datetime.fromisoformat(t.outbound.arrive)
            ready = arrive.hour * 60 + arrive.minute + transfer + (45 if t.mode == "train" else 75)
            start = fmt_hm(max(hm(DAY_START), ready))
            if ready > hm(DAY_START):
                notes.append(f"Начинаем после прибытия в {arrive:%H:%M} и трансфера (~{transfer} мин) — оставляем багаж в отеле")
        if day_no == n_days:
            dep = datetime.fromisoformat(t.inbound.depart)
            buffer = 60 if t.mode == "train" else 150
            latest = dep.hour * 60 + dep.minute - transfer - buffer
            end = fmt_hm(min(hm(DAY_END), latest))
            notes.append(f"Заканчиваем к {end}: отправление в {dep:%H:%M}, трансфер ~{transfer} мин и запас")
    return start, end, notes


def build_days(trip: Trip) -> None:
    p = trip.params
    n_days = (p.nights or 0) + 1
    start_date = date.fromisoformat(p.start_date)
    old = {d.day: d for d in trip.days}
    used: set[str] = set()
    days: list[DayPlan] = []
    for i in range(1, n_days + 1):
        prev = old.get(i)
        day = DayPlan(day=i, date=(start_date + timedelta(days=i - 1)).isoformat(), title="", place_ids=[],
                      less_walking=prev.less_walking if prev else p.walking == "low",
                      indoor_only=prev.indoor_only if prev else False)
        day.start_time, day.end_limit, day.notes = day_window(trip, i, n_days)
        day.place_ids = _select(trip, day, used)
        used.update(day.place_ids)
        days.append(day)
    trip.days = days
    for d in trip.days:
        route_day(trip, d)


def _select(trip: Trip, day: DayPlan, used: set[str], pinned: list[str] | None = None) -> list[str]:
    weekday = date.fromisoformat(day.date).weekday()
    h = trip.hotel()
    pos = (h.lat, h.lon) if h else (CITIES[trip.params.destination].lat, CITIES[trip.params.destination].lon)
    t = hm(day.start_time)
    end = hm(day.end_limit)
    if end - t < 60:
        return []
    chosen: list[str] = list(pinned or [])
    for pid in chosen:
        if pl := trip.place(pid):
            t += _leg(trip, day, pos, pl)[2] + pl.visit_min
            pos = (pl.lat, pl.lon)
    max_stops = 4 if day.less_walking else 6
    has_cafe = any((pl := trip.place(pid)) is not None and "cafe" in pl.cats for pid in chosen)
    interests = trip.params.interests
    while len(chosen) < max_stops:
        best, best_val = None, 0.0
        lunch = not has_cafe and t >= LUNCH_FROM - 30
        for pl in trip.places:
            if pl.id in used or pl.id in chosen or not _usable(pl, day, weekday):
                continue
            is_cafe = "cafe" in pl.cats
            if lunch and not is_cafe:
                continue
            if not lunch and is_cafe and pl.cats == ["cafe"]:
                continue
            mode, dist, leg_min, _ = _leg(trip, day, pos, pl)
            if t + leg_min + pl.visit_min > end:
                continue
            penalty = 2.5 if day.less_walking else 1.0
            val = place_score(pl, interests) / (leg_min * penalty + pl.visit_min * 0.5 + 10)
            if mode == "transit":
                val *= 0.6 if day.less_walking else 0.8
            if val > best_val:
                best, best_val = pl, val
        if best is None:
            if lunch:
                has_cafe = True
                continue
            break
        _, _, leg_min, _ = _leg(trip, day, pos, best)
        t += leg_min + best.visit_min
        pos = (best.lat, best.lon)
        chosen.append(best.id)
        if "cafe" in best.cats:
            has_cafe = True
    return chosen


def optimize_order(trip: Trip, day: DayPlan) -> None:
    h = trip.hotel()
    if not h or not day.place_ids:
        return
    places = [trip.place(pid) for pid in day.place_ids]
    places = [p for p in places if p]
    cafes = [p for p in places if p.cats == ["cafe"]]
    rest = [p for p in places if p not in cafes]
    order: list[Place] = []
    pos = (h.lat, h.lon)
    while rest:
        nxt = min(rest, key=lambda p: km(pos[0], pos[1], p.lat, p.lon))
        order.append(nxt)
        rest.remove(nxt)
        pos = (nxt.lat, nxt.lon)
    for c in cafes:
        t = hm(day.start_time)
        best_i, best_gap = len(order), 10**9
        for i in range(len(order) + 1):
            gap = abs(t - LUNCH_FROM)
            if gap < best_gap:
                best_i, best_gap = i, gap
            if i < len(order):
                t += order[i].visit_min + 15
        order.insert(best_i, c)
    day.place_ids = [p.id for p in order]


def route_day(trip: Trip, day: DayPlan) -> None:
    h = trip.hotel()
    city = CITIES[trip.params.destination]
    pos = (h.lat, h.lon) if h else (city.lat, city.lon)
    weekday = date.fromisoformat(day.date).weekday()
    t = hm(day.start_time)
    stops: list[Stop] = []
    walk_km = 0.0
    transit_min = 0
    cost = 0
    travelers = trip.params.adults + trip.params.children * 0.5
    notes = [n for n in day.notes if not n.startswith(("Внимание:", "Не успеваем"))]
    for i, pid in enumerate(day.place_ids):
        pl = trip.place(pid)
        if not pl:
            continue
        mode, dist, leg_min, leg_cost = _leg(trip, day, pos, pl)
        if i == 0 and mode == "walk" and dist < 0.05:
            mode = "start"
        t += leg_min
        arrive = t
        t += pl.visit_min
        note = None
        if weekday in pl.closed_weekdays:
            note = "Внимание: в этот день обычно выходной — проверьте часы"
            notes.append(f"Внимание: {pl.name} в {['пн','вт','ср','чт','пт','сб','вс'][weekday]} обычно закрыто")
        elif pl.hours_status != "confirmed" and pl.ticket_rub:
            note = "Часы работы не подтверждены — проверьте на сайте"
        stops.append(Stop(place=pl, arrive=fmt_hm(arrive), depart=fmt_hm(t), leg_mode=mode,
                          leg_km=dist, leg_min=leg_min, leg_cost_rub=leg_cost, note=note))
        if mode == "walk":
            walk_km += dist * 1.3
        else:
            transit_min += leg_min
        cost += leg_cost + int(pl.ticket_rub * travelers)
        pos = (pl.lat, pl.lon)
    if stops and t > hm(day.end_limit):
        notes.append(f"Не успеваем: план до {fmt_hm(t)}, а лимит дня {day.end_limit}")
    day.stops = stops
    day.walk_km = round(walk_km, 1)
    day.transit_min = transit_min
    day.cost_rub = cost
    day.notes = notes
    cats = [c for s in stops for c in s.place.cats if c != "cafe"]
    top = max(set(cats), key=cats.count) if cats else None
    flags = (" · меньше ходьбы" if day.less_walking else "") + (" · под крышей" if day.indoor_only else "")
    day.title = (f"День {day.day}: {CAT_RU.get(top, 'прогулка')}" if top else f"День {day.day}: дорога и отдых") + flags


def unused_places(trip: Trip) -> list[Place]:
    used = {pid for d in trip.days for pid in d.place_ids}
    return [p for p in trip.places if p.id not in used]


def reselect_day(trip: Trip, day: DayPlan, keep: list[str] | None = None) -> None:
    used = {pid for d in trip.days if d.day != day.day for pid in d.place_ids}
    day.place_ids = _select(trip, day, used, pinned=keep)
    optimize_order(trip, day)
    route_day(trip, day)
