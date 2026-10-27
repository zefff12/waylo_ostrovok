"""Бюджет считается только кодом из структурированных позиций."""
from __future__ import annotations

from .data import CITIES
from .geo import km, taxi_rub
from .schemas import Budget, BudgetItem, Trip

MEAL_DISCOUNT = {"none": 0.0, "breakfast": 0.2, "half_board": 0.55}


def transfer_cost(trip: Trip) -> tuple[int, float]:
    t, h = trip.transport(), trip.hotel()
    city = CITIES[trip.params.destination]  # type: ignore[index]
    if not (t and h):
        return 0, 0
    hub = city.station if t.mode == "train" and city.station else city.airport
    d = km(hub.lat, hub.lon, h.lat, h.lon)
    cars = 1 if trip.params.travelers <= 4 else 2
    return taxi_rub(d) * cars, d


def calc(trip: Trip) -> Budget:
    p = trip.params
    city = CITIES[p.destination]  # type: ignore[index]
    items: list[BudgetItem] = []
    t, h = trip.transport(), trip.hotel()
    days = (p.nights or 0) + 1
    if t:
        items.append(BudgetItem(id="transport", category="transport", title=t.title + " (туда и обратно)",
                                amount=t.price_total, kind=t.kind, source=t.source,
                                note=f"{t.price_per_person:,} ₽ × {p.travelers} чел.".replace(",", " ")))
    if h:
        items.append(BudgetItem(id="hotel", category="hotel", title=f"{h.name}, {h.nights} ноч.", amount=h.total,
                                kind=h.kind, source=h.source,
                                note=f"{h.price_per_night:,} ₽ × {h.nights} ноч.".replace(",", " ")))
    tr, dist = transfer_cost(trip)
    extras = [e for e in trip.budget.items if e.category == "extras"]
    booked = any(e.id == "transfer_booking" for e in extras)  # трансфер до отеля оплачен — такси остаётся только обратно
    if tr:
        items.append(BudgetItem(id="transfer", category="transfer",
                                title=f"Трансфер {'обратно' if booked else 'туда и обратно'} (такси, {dist:.0f} км)",
                                amount=tr if booked else tr * 2, kind="estimate", source="Оценка Waylo: посадка + ₽/км по городу"))
    meal = MEAL_DISCOUNT[h.meals] if h else 0
    food = int(round(city.food_per_person_day * (p.adults + p.children * 0.6) * days * (1 - meal) / 100) * 100)
    items.append(BudgetItem(id="food", category="food", title=f"Питание, {days} дн.", amount=food, kind="estimate",
                            source="Средний чек по городу — оценка Waylo",
                            note="С учётом питания в отеле" if meal else None))
    tickets = sum(int(s.place.ticket_rub * (p.adults + p.children * 0.5)) for d in trip.days for s in d.stops)
    if tickets:
        items.append(BudgetItem(id="tickets", category="tickets", title="Билеты в музеи и на смотровые", amount=tickets,
                                kind="estimate", source="Ориентировочные цены билетов — проверьте на сайтах"))
    local = sum(s.leg_cost_rub for d in trip.days for s in d.stops)
    if local:
        items.append(BudgetItem(id="local", category="local_transport", title="Транспорт по городу между точками",
                                amount=local, kind="estimate", source="Цена поездки × число поездок"))
    items.extend(extras)
    total = sum(i.amount for i in items)
    planned = total - sum(e.amount for e in extras)  # доп. услуги после покупки покупаются сознательно сверх плана
    b = Budget(items=items, total=total, limit=p.budget_rub,
               assumptions=["Питание и транспорт по городу — оценки", "Отели реальные (OpenStreetMap), цена проживания — оценка"])
    if p.budget_rub and planned > p.budget_rub:
        b.over_by = planned - p.budget_rub
        b.savings = savings(trip, total)
    return b


def savings(trip: Trip, total: int) -> list[str]:
    tips: list[str] = []
    t, h = trip.transport(), trip.hotel()
    if t:
        cheaper = [o for o in trip.transport_options if o.price_total < t.price_total and (o.pets_allowed or not trip.params.pets)]
        if cheaper:
            c = min(cheaper, key=lambda o: o.price_total)
            tips.append(f"{c.title}: −{t.price_total - c.price_total:,} ₽".replace(",", " "))
    if h:
        cheaper_h = [x for x in trip.hotel_options if x.total < h.total]
        if cheaper_h:
            c = min(cheaper_h, key=lambda x: x.total)
            tips.append(f"{c.name} ({c.distance_center_km} км до главных мест): −{h.total - c.total:,} ₽".replace(",", " "))
    paid = [s for d in trip.days for s in d.stops if s.place.ticket_rub >= 500]
    if paid:
        top = max(paid, key=lambda s: s.place.ticket_rub)
        tips.append(f"Заменить «{top.place.name}» на бесплатное место: −{int(top.place.ticket_rub * trip.params.travelers):,} ₽".replace(",", " "))
    tips.append("Питание в столовых и фудкортах вместо кафе: около −30% на еде")
    return tips
