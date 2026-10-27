"""Вдохновение: 2–3 направления с климатом, ценой и временем в пути, когда город не задан."""
from __future__ import annotations

from . import integrations
from .data import CITIES
from .schemas import DestinationOption, Explanation, TripParams
from .transport import flight_hours, rail_hours
from .geo import km

# интерес пользователя → тег направления и как это объяснить
INTEREST_TAGS = {
    "park": ("nature", "природа рядом"),
    "history": ("history", "история"),
    "architecture": ("architecture", "архитектура"),
    "cafe": ("food", "местная кухня"),
    "view": ("view", "красивые виды"),
}

MONTHS_PREP = ["январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]


def suggest(p: TripParams, limit: int = 3) -> list[DestinationOption]:
    origin = CITIES[p.origin]
    month = p.month or 11
    candidates = [c for c in CITIES.values() if c.id != origin.id]
    climates = dict(zip([c.id for c in candidates],
                        integrations.month_climate_many([(c.lat, c.lon) for c in candidates], month)))
    nights = p.nights or 4
    opts: list[DestinationOption] = []
    for c in candidates:
        rh = rail_hours(origin, c)
        fh = flight_hours(origin, c)
        if rh is not None and rh <= 9:
            mode, hours = "поезд", rh
            per_person = round((1500 + km(origin.lat, origin.lon, c.lat, c.lon) * 2.4) / 100) * 200
        else:
            mode, hours = "самолёт", fh
            per_person = round((3500 + km(origin.lat, origin.lon, c.lat, c.lon) * 4.2) / 100) * 200
        total = per_person * p.travelers + c.hotel_level * nights + c.food_per_person_day * p.travelers * (nights + 1)
        cl = climates.get(c.id)
        warm = cl["tmax"] if cl and cl.get("tmax") is not None else None
        why, trade, risks = [], [], []
        s = 0.0
        if "sea" in p.wishes:
            if "sea" in c.tags:
                s += 3
                why.append("Есть море")
            else:
                s -= 3
        if "warm" in p.wishes:
            if warm is not None:
                s += max(-3, min(3, (warm - 16) / 3))
                (why if warm >= 20 else trade).append(f"Днём около {warm:+.0f}°C в {MONTHS_PREP[month - 1]} (по архиву)")
            elif {"warm"} & set(c.tags):
                s += 1
        elif warm is not None:
            why.append(f"Днём около {warm:+.0f}°C в {MONTHS_PREP[month - 1]}")
        if "beach" in p.wishes and "beach" in c.tags:
            s += 1.5
        if "culture" in p.wishes and {"culture", "architecture"} & set(c.tags):
            s += 2
            why.append("Музеи и архитектура")
        hits = [label for cat, (tag, label) in INTEREST_TAGS.items() if cat in p.interests and tag in c.tags]
        if hits:
            s += min(2.0, 1.0 * len(hits))
            why.append(", ".join(hits).capitalize())
        if p.children and "kids" in c.tags:
            s += 1
            why.append("Удобно с детьми")
        limit_h = p.max_travel_hours or (5 if p.children else None)
        if limit_h and hours > limit_h:
            s -= 2.5
            trade.append(f"Дорога {hours:g} ч — дольше, чем хотелось")
        else:
            why.append(f"В пути {hours:g} ч ({mode})")
            if not limit_h and hours > 10:  # дальний перелёт без пересадок редко то, что имели в виду
                s -= 1.5
                trade.append(f"Долгая дорога: {hours:g} ч")
        if p.budget_rub and total > p.budget_rub:
            trade.append(f"Оценка {total:,} ₽ выше бюджета".replace(",", " "))
        if cl and cl.get("rainy_days", 0) >= 10:
            risks.append(f"Дождливых дней в прошлом году: {cl['rainy_days']}")
        if not c.domestic:
            risks.append("Зарубежная поездка: проверьте въездные требования и оплату картами")
        risks.append("Стоимость — оценка Waylo: транспорт по расстоянию, цены отелей — оценка")
        opts.append(DestinationOption(
            city_id=c.id, name=c.name, country=c.country, travel_hours=hours, travel_mode=mode,
            est_total_rub=int(round(total / 1000) * 1000), climate=cl,
            explanation=Explanation(why=why, tradeoffs=trade, risks=risks), score=round(s, 2),
        ))
    if ("cheap" in p.wishes or p.budget_rub) and opts:
        # цена относительно самого дешёвого кандидата: иначе все дальние направления одинаково «дорогие»
        cheapest = min(o.est_total_rub for o in opts)
        for o in opts:
            o.score = round(o.score + 4 * cheapest / o.est_total_rub - 2, 2)
            if p.budget_rub:
                o.score = round(o.score + max(-2, min(1, (p.budget_rub - o.est_total_rub) / p.budget_rub * 3)), 2)
    opts.sort(key=lambda o: -o.score)
    picked: list[DestinationOption] = []
    for o in opts:  # не больше двух направлений из одной страны — пользователю нужен выбор
        if sum(x.country == o.country for x in picked) < (2 if o.country == "Россия" else 1):
            picked.append(o)
        if len(picked) == limit:
            break
    return picked

