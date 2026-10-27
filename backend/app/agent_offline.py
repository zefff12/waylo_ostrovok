"""Офлайн-агент: правила вместо LLM. Работает без ключа и подхватывает, если Claude недоступен.

Вызывает те же инструменты, что и Claude, поэтому план и расчёты одинаковые — отличаются только тексты.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import planner
from .data import CITIES
from .parser import is_vague, parse_command, parse_request
from .planner import rub
from .schemas import Trip
from .walks import CAT_RU

QUESTION = ("Куда хотите поехать? Назовите город — или опишите поездку («к морю в ноябре, недорого, с ребёнком»), "
            "и я предложу направления.")


def handle(trip: Trip, text: str, profile: dict | None = None) -> str:
    text = text.strip()
    if not text:
        return QUESTION
    if trip.status == "choose_destination" and (chosen := _pick_destination(trip, text)):
        planner.apply_params(trip, {"destination": chosen})
        if planner.clarify(trip):
            return planner.clarify_text(trip)
        planner.plan_trip(trip)
        return describe_plan(trip, intro=f"Отлично, {CITIES[chosen].name}. Собрал поездку:")

    parsed = parse_request(text)
    new_city = parsed.get("destination")
    if trip.days and (not new_city or new_city == trip.params.destination):
        cmds = parse_command(text)
        if cmds:
            return _run_commands(trip, cmds)
        if not _has_trip_signal(parsed):
            return ("Не понял, что поменять. Можно так: «сделай дешевле», «на второй день меньше ходить», "
                    "«добавь музей», «замени место на кафе», «начался дождь», «на два дня позже», «с нами едет собака».")

    if trip.days and new_city and new_city != trip.params.destination:
        fresh = Trip(id=trip.id, user_id=trip.user_id)
        trip.__dict__.update(fresh.__dict__)

    upd = {k: v for k, v in parsed.items() if v not in (None, [], "")}
    remembered = []
    if profile:
        if not upd.get("interests") and profile.get("interests"):
            upd["interests"] = profile["interests"]
            remembered.append("интересы: " + ", ".join(CAT_RU.get(i, i) for i in profile["interests"][:4]))
        if profile.get("pets") and "pets" not in upd:
            remembered.append("в прошлый раз вы ездили с питомцем — скажите «с нами едет собака», если снова")
    if (not upd.get("destination") and not trip.params.destination and not is_vague(text, parsed)
            and not upd.get("month") and not trip.params.wishes):
        trip.status = "need_info"
        if m := re.search(r"\b(?:в|во|на)\s+([А-ЯЁ][а-яё\-]+)", text):
            names = ", ".join(c.name for c in CITIES.values())
            return (f"«{m.group(1)}» пока нет в демо-каталоге Waylo. Доступны: {names}. "
                    "Выберите город или опишите, какую поездку хотите, — подберу похожее направление.")
        return QUESTION
    planner.apply_params(trip, upd)
    mem = ("\n\n**Учёл из прошлых поездок:** " + "; ".join(remembered)) if remembered else ""
    if not trip.params.destination:
        opts = planner.suggest_destinations(trip)
        lines = ["Город не указан — вот направления под ваш запрос:"]
        for i, o in enumerate(opts, 1):
            cl = o["climate"]
            t = f", днём ~{cl['tmax']:+.0f}°C" if cl and cl.get("tmax") is not None else ""
            lines.append(f"{i}. **{o['name']}** — ~{rub(o['est_total_rub'])}, {o['travel_hours']:g} ч ({o['mode']}){t}")
            if o["tradeoffs"]:
                lines.append(f"   ↳ минус: {o['tradeoffs'][0]}")
        lines.append("Выберите карточку или напишите название города.")
        return "\n".join(lines) + mem
    if planner.clarify(trip):
        return planner.clarify_text(trip) + mem
    planner.plan_trip(trip)
    return describe_plan(trip, intro="Собрал поездку целиком:") + mem


def _has_trip_signal(parsed: dict) -> bool:
    return any(parsed.get(k) for k in ("destination", "nights", "budget_rub", "start_date", "month"))


def _pick_destination(trip: Trip, text: str) -> str | None:
    low = text.lower()
    for i, o in enumerate(trip.destination_options, 1):
        if o.name.lower()[:5] in low or re.fullmatch(rf"\s*{i}\s*", low) or o.city_id == low.strip():
            return o.city_id
    c = parse_request(text).get("destination")
    return c


def _run_commands(trip: Trip, cmds: list[tuple[str, dict]]) -> str:
    out: list[str] = []
    for name, args in cmds:
        if name == "shift_dates":
            r = planner.shift_dates(trip, args["days"])
        elif name == "set_constraints":
            r = planner.set_constraints(trip, **args)
        elif name == "make_cheaper":
            r = planner.make_cheaper(trip)
        elif name == "modify_day":
            if args.get("day") == -1:
                args["day"] = len(trip.days)
            r = planner.modify_day(trip, **args)
        elif name == "change_hotel":
            r = _change_hotel(trip, args["mode"])
        elif name == "switch_transport":
            opts = [o for o in trip.transport_options if o.mode == args["mode"]]
            r = planner.select_transport(trip, opts[0].id) if opts else {"error": "Такого транспорта для этого маршрута нет"}
        elif name == "rebuild":
            r = planner.plan_trip(trip)
        elif name == "checkout_hint":
            crit = [c for c in trip.connections if c.level == "critical"]
            out.append("Откройте вкладку «Оформление»: там итоговая сводка и демо-оплата." +
                       (f" Сначала нужно исправить: {crit[0].text}." if crit else ""))
            continue
        else:
            continue
        if "error" in r:
            out.append(f"**Не получилось:** {r['error']}")
        else:
            entry = trip.changes[-1] if trip.changes else None
            if entry:
                out.append(f"**{entry.summary}**")
                out.extend(f"• {d}" for d in entry.details[:6])
    out.append(_budget_line(trip))
    crit = [c for c in trip.connections if c.level == "critical"]
    if crit:
        out.append(f"**Критично:** {crit[0].text}. {crit[0].fix or ''}")
    out.append("_Офлайн-агент без LLM: правила + те же инструменты расчёта._")
    return "\n".join(out)


def _change_hotel(trip: Trip, mode: str) -> dict:
    cur = trip.hotel()
    others = [h for h in trip.hotel_options if h.id != (cur.id if cur else None)]
    if not others:
        return {"error": "Других подходящих отелей нет"}
    if mode == "cheaper":
        pick = min(others, key=lambda h: h.total)
    elif mode == "closer":
        pick = min(others, key=lambda h: h.distance_center_km)
    else:
        pick = others[0]
    return planner.select_hotel(trip, pick.id)


def _budget_line(trip: Trip) -> str:
    b = trip.budget
    if b.limit:
        if b.over_by:
            return f"**Бюджет:** {rub(b.total)} — **выше бюджета на {rub(b.over_by)}**. Можно: " + "; ".join(b.savings[:3])
        return f"**Бюджет:** {rub(b.total)} из {rub(b.limit)} — укладываемся, запас {rub(b.limit - b.total)}"
    return f"**Бюджет:** {rub(b.total)} (лимит не задан)"


def describe_plan(trip: Trip, intro: str) -> str:
    p = trip.params
    city = CITIES[p.destination]  # type: ignore[index]
    s = date.fromisoformat(p.start_date)  # type: ignore[arg-type]
    e = s + timedelta(days=p.nights or 0)
    t, h = trip.transport(), trip.hotel()
    lines = [intro, f"**{city.name}**, {s:%d.%m} – {e:%d.%m} ({p.nights} ноч.), {p.adults} взр." + (f" + {p.children} реб." if p.children else "") + (" + питомец" if p.pets else "")]
    if t:
        lines.append(f"**Дорога:** {t.title} — {rub(t.price_total)} ({'демо-тариф' if t.kind == 'demo' else 'цена из кэша Aviasales'}). "
                     f"Почему: {t.explanation.why[0].lower() if t.explanation.why else '—'}")
    if h:
        why = "; ".join(h.explanation.why[:2]) or "лучший баланс"
        trade = h.explanation.tradeoffs[0] if h.explanation.tradeoffs else None
        lines.append(f"**Отель:** {h.name}, {h.distance_center_km} км до главных мест — {rub(h.total)} (цена — оценка). {why}." + (f" Жертвуем: {trade.lower()}." if trade else ""))
    for d in trip.days:
        names = ", ".join(s.place.name for s in d.stops[:4]) + ("…" if len(d.stops) > 4 else "")
        lines.append(f"**День {d.day}:** {d.title.split(': ', 1)[-1]} — {names or 'свободный день'} ({d.walk_km} км пешком)")
    lines.append(_budget_line(trip))
    warn = [c for c in trip.connections if c.level != "ok"]
    if warn:
        lines.append(f"**{'Критично' if warn[0].level == 'critical' else 'Обратите внимание'}:** {warn[0].text}" + (f" → {warn[0].fix}" if warn[0].fix else ""))
    if p.assumptions:
        lines.append("Допущения: " + "; ".join(a.rstrip(".") for a in p.assumptions[:3]) + ". Поправьте, если не так.")
    lines.append("_Офлайн-агент без LLM: правила + те же инструменты расчёта. Отели реальные (OpenStreetMap), их цены и часть других цен — оценка._")
    return "\n".join(lines)
