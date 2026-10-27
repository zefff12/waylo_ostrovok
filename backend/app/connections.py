"""Проверка состыковок: прибытие, заселение, трансфер, выезд и отправление."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .data import CITIES
from .geo import hm, km, taxi_minutes
from .schemas import ConnectionCheck, Trip


def check(trip: Trip) -> list[ConnectionCheck]:
    out: list[ConnectionCheck] = []
    p = trip.params
    t, h = trip.transport(), trip.hotel()
    if not (t and h and p.start_date and p.nights is not None):
        return out
    city = CITIES[p.destination]  # type: ignore[index]
    hub = city.station if t.mode == "train" and city.station else city.airport
    transfer = taxi_minutes(km(hub.lat, hub.lon, h.lat, h.lon))
    start = date.fromisoformat(p.start_date)
    end = start + timedelta(days=p.nights)

    arrive = datetime.fromisoformat(t.outbound.arrive)
    at_hotel = arrive + timedelta(minutes=transfer)
    checkin = datetime(arrive.year, arrive.month, arrive.day, *map(int, h.checkin.split(":")))
    if arrive.date() != start:
        out.append(ConnectionCheck(level="critical", code="dates_out",
                                   text=f"Прибытие {arrive:%d.%m}, а заселение в отель {start:%d.%m}",
                                   fix="Сдвиньте даты отеля или выберите другой рейс/поезд"))
    if at_hotel < checkin - timedelta(hours=1):
        wait = checkin - at_hotel
        out.append(ConnectionCheck(
            level="warning", code="early_arrival",
            text=f"В отеле будете около {at_hotel:%H:%M}, заселение с {h.checkin} — ждать ~{wait.seconds // 3600} ч {wait.seconds % 3600 // 60} мин",
            fix=f"Ранний заезд ~{h.early_checkin_price:,} ₽ (демо) или оставить багаж и сразу гулять".replace(",", " ")))
    else:
        out.append(ConnectionCheck(level="ok", code="arrival",
                                   text=f"Прибытие {arrive:%H:%M} → отель ~{at_hotel:%H:%M}, заселение с {h.checkin}"))
    if arrive.hour >= 23 or arrive.hour < 5:
        out.append(ConnectionCheck(level="warning", code="night_arrival",
                                   text=f"Прибытие ночью ({arrive:%H:%M}) — общественный транспорт может не работать",
                                   fix="Заложено такси; предупредите отель о позднем заезде"))

    dep = datetime.fromisoformat(t.inbound.depart)
    if dep.date() != end:
        out.append(ConnectionCheck(level="critical", code="dates_back",
                                   text=f"Отъезд {dep:%d.%m}, а выезд из отеля {end:%d.%m}",
                                   fix="Сдвиньте обратный билет или число ночей"))
    buffer = 60 if t.mode == "train" else 150
    leave_by = dep - timedelta(minutes=transfer + buffer)
    checkout = datetime(dep.year, dep.month, dep.day, *map(int, h.checkout.split(":")))
    if leave_by > checkout + timedelta(hours=2):
        out.append(ConnectionCheck(level="warning", code="late_departure",
                                   text=f"Выезд из отеля в {h.checkout}, а выходить на {'вокзал' if t.mode == 'train' else 'рейс'} в {leave_by:%H:%M}",
                                   fix="Оставьте багаж в отеле — последний день прогулки уже заканчивается вовремя"))
    else:
        out.append(ConnectionCheck(level="ok", code="departure",
                                   text=f"Выезд {h.checkout}, выход в {leave_by:%H:%M}, отправление {dep:%H:%M} (трансфер ~{transfer} мин, запас {buffer} мин)"))

    if p.pets:
        if not t.pets_allowed:
            out.append(ConnectionCheck(level="critical", code="pets_transport", text="Выбранный транспорт не гарантирует провоз животного",
                                       fix="Выберите поезд (провоз по правилам перевозчика) или уточните у авиакомпании"))
        if not h.pets_allowed:
            out.append(ConnectionCheck(level="critical", code="pets_hotel", text="В выбранном отеле нельзя с животными",
                                       fix="Выберите отель с отметкой «можно с животными»"))

    for d in trip.days:
        if d.day == 1 and d.stops and hm(d.stops[0].arrive) < hm(d.start_time):
            out.append(ConnectionCheck(level="critical", code="day1_too_early",
                                       text="Первая прогулка начинается раньше, чем вы доберётесь до отеля"))
        if any(n.startswith("Не успеваем") for n in d.notes):
            out.append(ConnectionCheck(level="warning", code=f"day{d.day}_overflow", text=f"День {d.day}: программа не помещается в окно дня",
                                       fix="Скажите «меньше мест на день N» или уберите точку"))
        for s in d.stops:
            if s.note and s.note.startswith("Внимание:"):
                out.append(ConnectionCheck(level="warning", code=f"closed_{s.place.id}",
                                           text=f"День {d.day}: «{s.place.name}» в этот день обычно закрыт",
                                           fix="Попросите заменить точку — подберу альтернативу"))
    return out


def has_critical(trip: Trip) -> bool:
    return any(c.level == "critical" for c in trip.connections)
