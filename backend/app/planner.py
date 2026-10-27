"""Операции над поездкой. Их вызывают и Claude (как инструменты), и офлайн-агент.

Каждая операция меняет только зависимые части плана и пишет в журнал, что изменилось.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from . import budget as budget_mod
from . import connections, destinations, hotels, integrations, transport, walks
from .data import CITIES, city_places
from .schemas import ChangeEntry, DayWeather, Place, ToolEvent, Trip, TripParams

_pool = ThreadPoolExecutor(max_workers=2)
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def rub(n: int) -> str:
    return f"{n:,} ₽".replace(",", " ")


def log_tool(trip: Trip, tool: str, summary: str, ok: bool = True) -> None:
    trip.tool_log.append(ToolEvent(tool=tool, summary=summary, ok=ok))
    trip.tool_log = trip.tool_log[-40:]


def _snapshot(trip: Trip) -> dict:
    return {
        "total": trip.budget.total,
        "hotel": trip.hotel().name if trip.hotel() else None,
        "transport": trip.transport().title if trip.transport() else None,
        "days": {d.day: (d.walk_km, [s.place.name for s in d.stops], d.stops[-1].depart if d.stops else None) for d in trip.days},
        "dates": (trip.params.start_date, trip.params.nights),
    }


def _diff(before: dict, after: dict) -> list[str]:
    out: list[str] = []
    if before["dates"] != after["dates"] and after["dates"][0]:
        s = date.fromisoformat(after["dates"][0])
        out.append(f"Даты: {s:%d.%m} – {s + timedelta(days=after['dates'][1] or 0):%d.%m}")
    if before["transport"] != after["transport"] and after["transport"]:
        out.append(f"Транспорт: {after['transport']}")
    if before["hotel"] != after["hotel"] and after["hotel"]:
        out.append(f"Отель: {after['hotel']}")
    for day, (km_after, names_after, end_after) in after["days"].items():
        b = before["days"].get(day)
        if not b:
            continue
        km_before, names_before, end_before = b
        added = [n for n in names_after if n not in names_before]
        removed = [n for n in names_before if n not in names_after]
        if added or removed or abs(km_before - km_after) >= 0.3:
            parts = []
            if removed:
                parts.append("убрали " + ", ".join(removed))
            if added:
                parts.append("добавили " + ", ".join(added))
            if abs(km_before - km_after) >= 0.3:
                parts.append(f"пешком {km_before} → {km_after} км")
            if end_before != end_after and end_after:
                parts.append(f"конец дня {end_before} → {end_after}")
            out.append(f"День {day}: " + "; ".join(parts))
    if before["total"] != after["total"]:
        delta = after["total"] - before["total"]
        out.append(f"Бюджет: {rub(before['total'])} → {rub(after['total'])} ({'+' if delta > 0 else '−'}{rub(abs(delta))})")
    return out


def _record(trip: Trip, before: dict, summary: str) -> ChangeEntry:
    entry = ChangeEntry(at=datetime.now().strftime("%H:%M"), summary=summary, details=_diff(before, _snapshot(trip)))
    trip.changes.append(entry)
    return entry


def recompute(trip: Trip) -> None:
    """Пересчитать зависимые от выбора вещи: маршруты дня, бюджет, состыковки."""
    for d in trip.days:
        walks.route_day(trip, d)
    trip.budget = budget_mod.calc(trip)
    trip.connections = connections.check(trip)


# ---------- параметры ----------

def default_start(p: TripParams) -> str:
    today = date.today()
    if p.month:
        year = today.year + (p.month < today.month)
        d = date(year, p.month, 1)
        if d < today + timedelta(days=5):
            d = today + timedelta(days=5)
    else:
        d = today + timedelta(days=14)
    while d.weekday() != 4:  # ближайшая пятница
        d += timedelta(days=1)
    return d.isoformat()


def missing(p: TripParams) -> list[str]:
    out = []
    if not p.destination:
        out.append("destination")
    return out


def clarify(trip: Trip) -> list[str]:
    """Вопросы о том, чего пользователь не назвал. Задаём один раз: после ответа берём допущения."""
    p = trip.params
    if p.clarified or not p.destination:
        return []
    qs = []
    if "start_date" not in p.known:
        qs.append("С какого числа планируете поездку?" if "nights" in p.known else "С какого по какое число планируете поездку?")
    elif "nights" not in p.known:
        qs.append("На сколько дней едете?")
    if "origin" not in p.known:
        qs.append("Из какого города поедете?")
    if "adults" not in p.known and "children" not in p.known:
        qs.append("Сколько едет взрослых и будут ли дети?")
    if qs and p.budget_rub is None:  # бюджет сам по себе не повод переспрашивать, но раз уж спрашиваем
        qs.append("Есть ли бюджет на поездку?")
    return qs


def clarify_text(trip: Trip) -> str:
    qs = clarify(trip)
    trip.params.clarified = True
    trip.status = "need_info"
    name = CITIES[trip.params.destination].name if trip.params.destination else "поездку"  # type: ignore[index]
    lines = [f"Соберу поездку: **{name}**. Чтобы не гадать, уточните:"]
    lines += [f"{i}. {q}" for i, q in enumerate(qs, 1)]
    lines.append("Можно ответить одним сообщением, например: «с 12 по 15 декабря, из Казани, двое взрослых». "
                 "Если неважно — напишите «на ваше усмотрение», и я возьму ближайшие выходные.")
    return "\n".join(lines)


def apply_params(trip: Trip, upd: dict, known: list[str] | None = None) -> list[str]:
    """Обновить параметры; вернуть список сделанных допущений.

    known — поля, которые пользователь назвал сам (по умолчанию все ключи upd).
    """
    p = trip.params
    named = [k for k in (upd if known is None else known) if upd.get(k) not in (None, [], "")]
    p.known = list(dict.fromkeys([*p.known, *named]))
    stale = {"start_date": "Точные даты", "nights": "Длительность", "adults": "Путешественники", "children": "Путешественники"}
    p.assumptions = [a for a in p.assumptions if not any(a.startswith(stale[k]) for k in named if k in stale)]
    for k, v in upd.items():
        if v is None or not hasattr(p, k):
            continue
        if k == "interests":
            v = list(dict.fromkeys([*p.interests, *v]))
        if k == "wishes":
            v = list(dict.fromkeys([*p.wishes, *v]))
        setattr(p, k, v)
    if p.destination and p.destination not in CITIES:
        p.destination = None
    if p.origin not in CITIES:
        p.origin = "moscow"
    if p.destination == p.origin:
        p.origin = "spb" if p.destination == "moscow" else "moscow"
    assumptions = []
    if p.nights is None:
        p.nights = 2
        assumptions.append("Длительность не указана — взяли 3 дня (2 ночи)")
    if not p.start_date:
        p.start_date = default_start(p)
        s = date.fromisoformat(p.start_date)
        assumptions.append(f"Точные даты не указаны — взяли {s:%d.%m} (ближайшая пятница{' ' + MONTHS[p.month - 1][:-1] + 'я' if p.month else ''})")
    if "adults" not in upd and not any(a.startswith("Путешественники") for a in p.assumptions):
        assumptions.append(f"Путешественники: {p.adults} взрослых" + (f" и {p.children} реб." if p.children else ""))
    p.assumptions = list(dict.fromkeys([*p.assumptions, *assumptions]))
    return assumptions


# ---------- инструменты ----------

def suggest_destinations(trip: Trip) -> list[dict]:
    opts = destinations.suggest(trip.params)
    trip.destination_options = opts
    trip.status = "choose_destination"
    real = any(o.climate for o in opts)
    log_tool(trip, "suggest_destinations",
             f"{len(opts)} направления: " + ", ".join(o.name for o in opts) + ("" if real else " (климат недоступен)"))
    return [{"city_id": o.city_id, "name": o.name, "est_total_rub": o.est_total_rub, "travel_hours": o.travel_hours,
             "mode": o.travel_mode, "climate": o.climate, **o.explanation.model_dump()} for o in opts]


def _load_places(trip: Trip) -> None:
    city = CITIES[trip.params.destination]  # type: ignore[index]
    places = city_places(city)
    fut = _pool.submit(lambda: integrations.dgis_places("кафе", city.lat, city.lon) or integrations.overpass_cafes(city.lat, city.lon))
    try:
        extra = fut.result(timeout=4)
    except TimeoutError:
        extra = None
    if extra:
        known = {p.name.lower() for p in places}
        for i, e in enumerate(extra[:6]):
            if e["name"].lower() in known:
                continue
            places.append(Place(id=f"ext_cafe_{i}", name=e["name"], cats=["cafe"], lat=e["lat"], lon=e["lon"], indoor=True,
                                visit_min=50, ticket_rub=0, hours_status="unknown",
                                description=e.get("address") or "Кафе рядом с центром", source=e["source"]))
        log_tool(trip, "search_places", f"{len(places)} мест: демо-набор + {len(extra)} кафе из {extra[0]['source']}")
    else:
        log_tool(trip, "search_places", f"{len(places)} мест из демо-набора (внешние карты недоступны)", ok=bool(places))
    trip.places = places


def _weather(trip: Trip) -> None:
    p = trip.params
    city = CITIES[p.destination]  # type: ignore[index]
    start = date.fromisoformat(p.start_date)  # type: ignore[arg-type]
    end = start + timedelta(days=p.nights or 0)
    rows = integrations.forecast(city.lat, city.lon, start, end)
    kind, source = "confirmed", "Open-Meteo, прогноз"
    if not rows:
        rows = integrations.same_dates_last_year(city.lat, city.lon, start, end)
        kind, source = "estimate", "Open-Meteo: те же даты прошлого года (не прогноз)"
    by_idx = {i: r for i, r in enumerate(rows or [])}
    for d in trip.days:
        r = by_idx.get(d.day - 1)
        if not r or r["tmax"] is None or r["tmin"] is None:
            d.weather = DayWeather(label="Погода недоступна", kind="demo", source="нет данных")
            continue
        rain = (r["precip"] or 0) >= 2
        label = f"{r['tmin']:+.0f}…{r['tmax']:+.0f}°C" + (f", осадки {r['precip']:.0f} мм" if rain else "")
        d.weather = DayWeather(tmax=r["tmax"], tmin=r["tmin"], precip_mm=r["precip"], label=label, kind=kind, source=source)
        if rain and kind == "confirmed" and not d.indoor_only:
            d.notes.append("По прогнозу дождь — скажите «дождь на день N», переставлю на крытые места")
    log_tool(trip, "get_weather", f"{source}" if rows else "Open-Meteo недоступен — погода не показана", ok=bool(rows))


def plan_trip(trip: Trip) -> dict:
    """Собрать поездку целиком: транспорт, отель, места, прогулки, бюджет, состыковки."""
    p = trip.params
    if not p.destination:
        return {"error": "Не задано направление. Спросите пользователя или вызовите suggest_destinations."}
    city = CITIES[p.destination]
    before = _snapshot(trip) if trip.days else None
    trip.transport_options = transport.search_transport(p)
    t0 = trip.transport_options[0]
    log_tool(trip, "search_transport", f"{len(trip.transport_options)} вариантов, лучший: {t0.title} — {rub(t0.price_total)} ({t0.kind})")
    trip.selected_transport_id = t0.id
    _load_places(trip)
    focus = _focus(trip)
    trip.hotel_options = hotels.rank(hotels.generate(city, p, focus), p, focus)
    trip.selected_hotel_id = trip.hotel_options[0].id
    h0 = trip.hotel_options[0]
    log_tool(trip, "search_hotels", f"{len(trip.hotel_options)} отелей ({'OpenStreetMap, цена — оценка' if h0.kind == 'estimate' else 'демо'}), лучший: {h0.name} — {rub(h0.total)}")
    walks.build_days(trip)
    log_tool(trip, "build_walks", f"{len(trip.days)} дн., {sum(len(d.stops) for d in trip.days)} точек")
    _weather(trip)
    recompute(trip)
    fit_budget(trip)
    log_tool(trip, "calc_budget", f"Итого {rub(trip.budget.total)}" + (f", превышение {rub(trip.budget.over_by)}" if trip.budget.over_by else ""))
    log_tool(trip, "check_connections", _conn_summary(trip))
    trip.status = "ready"
    if before:
        _record(trip, before, "План пересобран")
    return summary(trip)


def _focus(trip: Trip) -> tuple[float, float]:
    """Центр тяжести интересных мест — к нему тянем отель."""
    pts = [pl for pl in trip.places if walks.place_score(pl, trip.params.interests) > 1.5 and pl.cats != ["cafe"]] or trip.places
    return (sum(p.lat for p in pts) / len(pts), sum(p.lon for p in pts) / len(pts))


def _conn_summary(trip: Trip) -> str:
    w = sum(c.level == "warning" for c in trip.connections)
    c = sum(c.level == "critical" for c in trip.connections)
    return "Состыковки в порядке" if not (w or c) else f"Предупреждений: {w}, критичных: {c}"


def summary(trip: Trip) -> dict:
    t, h = trip.transport(), trip.hotel()
    return {
        "destination": CITIES[trip.params.destination].name if trip.params.destination else None,
        "dates": [trip.params.start_date, trip.params.nights],
        "travelers": trip.params.travelers,
        "transport": t and {"id": t.id, "title": t.title, "price_total": t.price_total, "kind": t.kind,
                            "arrive": t.outbound.arrive, "depart_back": t.inbound.depart, **t.explanation.model_dump()},
        "transport_alternatives": [{"id": o.id, "title": o.title, "price_total": o.price_total, "door_to_door_h": o.door_to_door_hours,
                                    "pets_allowed": o.pets_allowed, "kind": o.kind} for o in trip.transport_options],
        "hotel": h and {"id": h.id, "name": h.name, "total": h.total, "distance_km": h.distance_center_km,
                        "cancellation": h.cancellation_text, "meals": h.meals, **h.explanation.model_dump()},
        "hotel_alternatives": [{"id": x.id, "name": x.name, "total": x.total, "score": x.score, "distance_km": x.distance_center_km,
                                "cancellation": x.cancellation, "meals": x.meals, "pets": x.pets_allowed}
                               for x in trip.hotel_options[:5]],
        "days": [{"day": d.day, "date": d.date, "title": d.title, "walk_km": d.walk_km, "cost": d.cost_rub,
                  "weather": d.weather.label if d.weather else None,
                  "stops": [f"{s.arrive} {s.place.name}" for s in d.stops]} for d in trip.days],
        "budget": {"total": trip.budget.total, "limit": trip.budget.limit, "over_by": trip.budget.over_by,
                   "savings": trip.budget.savings},
        "connections": [c.model_dump() for c in trip.connections if c.level != "ok"],
        "assumptions": trip.params.assumptions,
    }


def select_transport(trip: Trip, option_id: str) -> dict:
    if not any(o.id == option_id for o in trip.transport_options):
        return {"error": f"Нет варианта {option_id}"}
    before = _snapshot(trip)
    trip.selected_transport_id = option_id
    _rewindow(trip)
    recompute(trip)
    e = _record(trip, before, f"Выбран транспорт: {trip.transport().title}")  # type: ignore[union-attr]
    log_tool(trip, "select_transport", e.summary)
    return {"changes": e.details, **summary(trip)}


def select_hotel(trip: Trip, hotel_id: str) -> dict:
    if not any(h.id == hotel_id for h in trip.hotel_options):
        return {"error": f"Нет отеля {hotel_id}"}
    before = _snapshot(trip)
    trip.selected_hotel_id = hotel_id
    _rewindow(trip)
    for d in trip.days:  # места дня сохраняем, меняется старт и порядок
        walks.optimize_order(trip, d)
    recompute(trip)
    e = _record(trip, before, f"Выбран отель: {trip.hotel().name}")  # type: ignore[union-attr]
    log_tool(trip, "select_hotel", e.summary + " — маршруты пересчитаны от нового отеля")
    return {"changes": e.details, **summary(trip)}


def _rewindow(trip: Trip) -> None:
    n = len(trip.days)
    for d in trip.days:
        start, end, notes = walks.day_window(trip, d.day, n)
        kept = [x for x in d.notes if not x.startswith(("Начинаем", "Заканчиваем"))]
        d.start_time, d.end_limit, d.notes = start, end, notes + kept
        if d.day in (1, n):
            walks.reselect_day(trip, d, keep=None)


def modify_day(trip: Trip, day: int, action: str, category: str | None = None, place_id: str | None = None) -> dict:
    """action: less_walking | rain | replace_with_cafe | add_category | remove_place | more_walking"""
    d = next((x for x in trip.days if x.day == day), None)
    if not d:
        return {"error": f"Нет дня {day}"}
    before = _snapshot(trip)
    text = ""
    if action == "less_walking":
        d.less_walking = True
        walks.reselect_day(trip, d, keep=_compact_core(trip, d))
        text = f"День {day}: меньше ходьбы"
    elif action == "more_walking":
        d.less_walking = False
        walks.reselect_day(trip, d, keep=list(d.place_ids))
        text = f"День {day}: обычный темп"
    elif action == "rain":
        d.indoor_only = True
        d.less_walking = True
        keep = [pid for pid in d.place_ids if (pl := trip.place(pid)) and pl.indoor]
        walks.reselect_day(trip, d, keep=keep)
        text = f"День {day}: дождь — только крытые места и короткие переходы"
    elif action == "replace_with_cafe":
        target = place_id or _least_valuable_sight(trip, d)
        # кафе можно повторить в другой день — в отличие от музея, это нормально
        cafes = [p for p in walks.unused_places(trip) if "cafe" in p.cats] or [
            p for p in trip.places if "cafe" in p.cats and p.id not in d.place_ids]
        if not target or not cafes:
            return {"error": "Нечего заменить или нет свободных кафе рядом"}
        old = trip.place(target)
        new = min(cafes, key=lambda c: _dist(old, c))  # type: ignore[arg-type]
        d.place_ids = [new.id if pid == target else pid for pid in d.place_ids]
        walks.route_day(trip, d)
        text = f"День {day}: «{old.name}» → кафе «{new.name}»"  # type: ignore[union-attr]
    elif action == "add_category":
        cat = category or "museum"
        pool = walks.unused_places(trip)
        if cat == "cafe":
            pool = pool + [p for p in trip.places if "cafe" in p.cats and p.id not in d.place_ids and p not in pool]
        cands = [p for p in pool if cat in p.cats
                 and date.fromisoformat(d.date).weekday() not in p.closed_weekdays and (p.indoor or not d.indoor_only)]
        if not cands:
            return {"error": f"Свободных мест категории {cat} нет"}
        center = _day_center(trip, d)
        best = min(cands, key=lambda c: _dist_pt(center, c))
        d.place_ids.append(best.id)
        walks.optimize_order(trip, d)
        walks.route_day(trip, d)
        while any(n.startswith("Не успеваем") for n in d.notes) and len(d.place_ids) > 1:
            drop = _least_valuable_sight(trip, d, exclude=best.id)
            if not drop:
                break
            d.place_ids.remove(drop)
            walks.route_day(trip, d)
        text = f"День {day}: добавлен «{best.name}»"
    elif action == "remove_place":
        if place_id not in d.place_ids:
            return {"error": "Такой точки в дне нет"}
        d.place_ids.remove(place_id)  # type: ignore[arg-type]
        walks.route_day(trip, d)
        text = f"День {day}: точка убрана"
    else:
        return {"error": f"Неизвестное действие {action}"}
    recompute(trip)
    e = _record(trip, before, text)
    log_tool(trip, "modify_day", text)
    return {"changes": e.details, "day": summary(trip)["days"][day - 1], "budget_total": trip.budget.total}


def _compact_core(trip: Trip, d) -> list[str]:
    """Самое ценное место дня и соседи в радиусе ~1 км — ядро дня без длинных переходов."""
    places = [p for pid in d.place_ids if (p := trip.place(pid))]
    if not places:
        return []
    anchor = max(places, key=lambda p: walks.place_score(p, trip.params.interests))
    near = sorted((p for p in places if _dist(anchor, p) <= 1.0), key=lambda p: _dist(anchor, p))
    return [p.id for p in near[:3]]


def _dist(a: Place, b: Place) -> float:
    from .geo import km
    return km(a.lat, a.lon, b.lat, b.lon)


def _dist_pt(c: tuple[float, float], b: Place) -> float:
    from .geo import km
    return km(c[0], c[1], b.lat, b.lon)


def _day_center(trip: Trip, d) -> tuple[float, float]:
    pts = [trip.place(pid) for pid in d.place_ids if trip.place(pid)]
    if not pts:
        h = trip.hotel()
        return (h.lat, h.lon) if h else (0.0, 0.0)
    return (sum(p.lat for p in pts) / len(pts), sum(p.lon for p in pts) / len(pts))  # type: ignore[union-attr]


def _least_valuable_sight(trip: Trip, d, exclude: str | None = None) -> str | None:
    sights = [pid for pid in d.place_ids if pid != exclude and (pl := trip.place(pid)) and "cafe" not in pl.cats]
    if not sights:
        return None
    return min(sights, key=lambda pid: walks.place_score(trip.place(pid), trip.params.interests))  # type: ignore[arg-type]


def shift_dates(trip: Trip, days: int) -> dict:
    """Сдвиг поездки: транспорт ищем заново на новые даты, отель и места сохраняем."""
    before = _snapshot(trip)
    s = date.fromisoformat(trip.params.start_date) + timedelta(days=days)  # type: ignore[arg-type]
    trip.params.start_date = s.isoformat()
    keep_mode = trip.transport().mode if trip.transport() else None
    trip.transport_options = transport.search_transport(trip.params)
    same = next((o for o in trip.transport_options if o.mode == keep_mode), trip.transport_options[0])
    trip.selected_transport_id = same.id
    for d in trip.days:
        d.date = (s + timedelta(days=d.day - 1)).isoformat()
    _rewindow(trip)
    for d in trip.days:  # из-за выходных дней музеев день мог стать невалидным
        if any(trip.place(pid) and date.fromisoformat(d.date).weekday() in trip.place(pid).closed_weekdays for pid in d.place_ids):  # type: ignore[union-attr]
            walks.reselect_day(trip, d, keep=[pid for pid in d.place_ids
                                              if date.fromisoformat(d.date).weekday() not in trip.place(pid).closed_weekdays])  # type: ignore[union-attr]
    _weather(trip)
    recompute(trip)
    e = _record(trip, before, f"Поездка сдвинута на {days:+d} дн.")
    log_tool(trip, "shift_dates", e.summary)
    return {"changes": e.details, **summary(trip)}


def set_constraints(trip: Trip, pets: bool | None = None, children: int | None = None, budget_rub: int | None = None,
                    adults: int | None = None, priority: str | None = None, walking: str | None = None,
                    nights: int | None = None) -> dict:
    """Новые жёсткие ограничения: пересобираем только то, что они затрагивают."""
    before = _snapshot(trip)
    p = trip.params
    changed = []
    if pets is not None and pets != p.pets:
        p.pets = pets
        changed.append("питомец")
    if children is not None and children != p.children:
        p.children = children
        changed.append("дети")
    if adults is not None and adults != p.adults:
        p.adults = adults
        changed.append("число гостей")
    if budget_rub is not None:
        p.budget_rub = budget_rub
        changed.append("бюджет")
    if priority:
        p.priority = priority  # type: ignore[assignment]
        changed.append("приоритет")
    if walking:
        p.walking = walking  # type: ignore[assignment]
        changed.append("темп")
    if nights is not None and nights != p.nights:
        p.nights = nights
        changed.append("длительность")
    if not trip.days:
        return {"ok": True, "changed": changed}
    if {"число гостей", "длительность"} & set(changed):
        return plan_trip(trip) | {"changed": changed}
    if {"питомец", "дети", "приоритет", "число гостей"} & set(changed):
        city = CITIES[p.destination]  # type: ignore[index]
        trip.hotel_options = hotels.rank(hotels.generate(city, p, _focus(trip)), p, _focus(trip))
        cur = trip.hotel()
        if not cur or cur.id != trip.hotel_options[0].id:
            trip.selected_hotel_id = trip.hotel_options[0].id
        trip.transport_options = transport.rank_transport(trip.transport_options, p)
        t = trip.transport()
        if p.pets and t and not t.pets_allowed:
            ok = [o for o in trip.transport_options if o.pets_allowed]
            if ok:
                trip.selected_transport_id = ok[0].id
        _rewindow(trip)
        for d in trip.days:
            walks.optimize_order(trip, d)
    if "темп" in changed:
        for d in trip.days:
            d.less_walking = p.walking == "low"
            walks.reselect_day(trip, d, keep=list(d.place_ids)[:3] if d.less_walking else list(d.place_ids))
    recompute(trip)
    if "бюджет" in changed:
        fit_budget(trip)
    e = _record(trip, before, "Изменены условия: " + ", ".join(changed))
    if "питомец" in changed and p.pets and not any(x.startswith(("Отель", "Транспорт")) for x in e.details):
        h, t = trip.hotel(), trip.transport()
        e.details.append(f"Проверил: в «{h.name if h else '—'}» можно с животными, "
                         f"{'поезд допускает провоз' if t and t.pets_allowed else 'транспорт — уточните правила перевозчика'}")
    if "бюджет" in changed and p.budget_rub:
        e.details.append(f"Лимит {rub(p.budget_rub)}: " + (f"превышение {rub(trip.budget.over_by)}" if trip.budget.over_by else "укладываемся"))
    log_tool(trip, "set_constraints", e.summary)
    return {"changes": e.details, **summary(trip)}


def fit_budget(trip: Trip) -> bool:
    """Уложиться в бюджет пользователя: лучшая по рейтингу пара транспорт + отель, которая в него влезает.

    Если даже самый дешёвый вариант дороже, бесплатные места заменяют платные; не помогло — честно
    помечаем критичную проблему, и оформление блокируется, пока пользователь не решит, что менять.
    """
    p = trip.params
    if not p.budget_rub or trip.budget.total <= p.budget_rub:
        return True
    cur_t, cur_h = trip.selected_transport_id, trip.selected_hotel_id
    trans = [o for o in trip.transport_options if o.pets_allowed or not p.pets]
    combos = []
    for ti, t in enumerate(trans):
        for hi, h in enumerate(trip.hotel_options):
            trip.selected_transport_id, trip.selected_hotel_id = t.id, h.id
            total = budget_mod.calc(trip).total
            fits = total <= p.budget_rub
            # влезающие — лучший по рейтингу (при равенстве дешевле); если не влезает ничего — самый дешёвый
            combos.append((fits, -(ti + hi) if fits else -total, -total, t.id, h.id))
    _, _, _, t_id, h_id = max(combos)
    trip.selected_transport_id, trip.selected_hotel_id = t_id, h_id
    if (t_id, h_id) != (cur_t, cur_h):
        _rewindow(trip)
        for d in trip.days:
            walks.optimize_order(trip, d)
    recompute(trip)
    if trip.budget.total > p.budget_rub:
        _swap_paid_places(trip)
        recompute(trip)
    ok = trip.budget.total <= p.budget_rub
    log_tool(trip, "fit_budget", f"Лимит {rub(p.budget_rub)}: " + (f"уложились, {rub(trip.budget.total)}" if ok
             else f"минимум {rub(trip.budget.total)}, не хватает {rub(trip.budget.over_by)}"), ok=ok)
    return ok


def _swap_paid_places(trip: Trip) -> None:
    for d in trip.days:  # самое дорогое платное место дня → бесплатная альтернатива рядом
        paid = [pid for pid in d.place_ids if (pl := trip.place(pid)) and pl.ticket_rub >= 600]
        free = [x for x in walks.unused_places(trip) if x.ticket_rub == 0 and "cafe" not in x.cats]
        if paid and free:
            worst = max(paid, key=lambda pid: trip.place(pid).ticket_rub)  # type: ignore[union-attr]
            alt = min(free, key=lambda x: _dist(trip.place(worst), x))  # type: ignore[arg-type]
            d.place_ids = [alt.id if pid == worst else pid for pid in d.place_ids]
        walks.optimize_order(trip, d)


def make_cheaper(trip: Trip) -> dict:
    before = _snapshot(trip)
    p = trip.params
    p.priority = "price"
    trip.transport_options = transport.rank_transport(trip.transport_options, p)
    ok_t = [o for o in trip.transport_options if o.pets_allowed or not p.pets]
    trip.selected_transport_id = min(ok_t, key=lambda o: o.price_total).id
    city = CITIES[p.destination]  # type: ignore[index]
    trip.hotel_options = hotels.rank(hotels.generate(city, p, _focus(trip)), p, _focus(trip))
    cur = trip.hotel()
    cand = [h for h in trip.hotel_options if h.distance_center_km <= 3.5] or trip.hotel_options
    cheapest = min(cand, key=lambda h: h.total)
    if not cur or cheapest.total < cur.total:
        trip.selected_hotel_id = cheapest.id
    _rewindow(trip)
    _swap_paid_places(trip)
    recompute(trip)
    e = _record(trip, before, "Сделали дешевле")
    log_tool(trip, "make_cheaper", f"{rub(before['total'])} → {rub(trip.budget.total)}")
    saved = before["total"] - trip.budget.total
    out = {"changes": e.details, "total_before": before["total"], "saved_rub": saved, **summary(trip)}
    if saved <= 0:  # без явной пометки модель склонна сообщать об экономии, которой не было
        out["note"] = ("Дешевле не получилось: уже выбраны самые дешёвые транспорт и отель, бесплатных замен рядом нет. "
                       "Скажи об этом честно и предложи сократить число ночей или сдвинуть даты.")
    return out


EXTRA_ITEM = {"early_checkin": "early_checkin", "transfer": "transfer_booking"}


def extra_offers(trip: Trip) -> list:
    """Что можно докупить после покупки: цена считается заранее и показывается до оплаты."""
    from .schemas import ExtraOffer

    t, h = trip.transport(), trip.hotel()
    paid = {i.id for i in trip.budget.items if i.category == "extras"}
    out = []
    if h and h.early_checkin_price:
        arrive = t.outbound.arrive[11:16] if t else ""
        out.append(ExtraOffer(kind="early_checkin", title=f"Ранний заезд в {h.name}", amount=h.early_checkin_price,
                              note=f"Номер готов к прибытию{' в ' + arrive if arrive else ''}, а не с {h.checkin}. Тариф — оценка (50% ночи)",
                              paid="early_checkin" in paid))
    tr, dist = budget_mod.transfer_cost(trip)
    if tr and t:
        hub = "вокзала" if t.mode == "train" else "аэропорта"
        out.append(ExtraOffer(kind="transfer", title=f"Трансфер от {hub} до отеля", amount=_transfer_price(tr),
                              note=f"Встреча с табличкой, {dist:.0f} км, фиксированная цена за машину. Такси в смете заменится на эту поездку",
                              paid="transfer_booking" in paid))
    return out


def _transfer_price(taxi_one_way: int) -> int:
    return int(round(taxi_one_way * 1.3 / 100) * 100)  # заказной трансфер с встречей дороже такси примерно на треть


def add_extra(trip: Trip, kind: str) -> dict:
    """После покупки (демо): ранний заезд или трансфер — отдельная оплата на свою сумму."""
    from .schemas import BudgetItem

    offer = next((o for o in extra_offers(trip) if o.kind == kind), None)
    if not offer:
        return {"error": "Эта услуга недоступна для выбранного отеля и транспорта"}
    if offer.paid:
        return {"error": "Уже оформлено"}
    item = BudgetItem(id=EXTRA_ITEM[kind], category="extras", title=offer.title, amount=offer.amount, kind="estimate",
                      source="Оценка Waylo, оплата демо")
    trip.budget.items = [i for i in trip.budget.items if i.id != item.id] + [item]
    recompute(trip)
    log_tool(trip, "post_purchase", f"{item.title} — {rub(item.amount)}")
    return {"added": item.title, "amount": item.amount}
