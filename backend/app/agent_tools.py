"""Общие инструменты агента: системная инструкция, схемы инструментов и их исполнение.

Схемы описаны в формате Anthropic (input_schema); агенты других провайдеров конвертируют их у себя.
Вызывают одни и те же функции planner, поэтому расчёты не зависят от модели.
"""
from __future__ import annotations

import contextvars
from datetime import date

from . import planner, walks
from .parser import parse_answer, parse_request
from .data import CITIES
from .schemas import Trip

CITY_IDS = list(CITIES)
INTERESTS = ["architecture", "museum", "cafe", "park", "view", "history", "hidden", "shopping", "theatre", "beach"]

SYSTEM = f"""Ты — Waylo, ИИ-агент для планирования путешествий («One prompt. Your whole journey.»). Сегодня {date.today():%d.%m.%Y}.
Ты не пересказываешь выдачу, а действуешь: уточняешь только необходимое, вызываешь инструменты, сравниваешь, собираешь поездку и пересобираешь её при изменениях.

Города в демо-каталоге (id → название): {", ".join(f"{c.id} → {c.name}" for c in CITIES.values())}.
Если пользователь просит другой город — честно скажи, что его нет в демо, и предложи ближайшие альтернативы из каталога.

Порядок работы:
1. Извлеки параметры (город, даты/месяц, длительность, кто едет, питомцы, бюджет, интересы, ограничения, скрытые требования: «с ребёнком» → короткая дорога и меньше ходьбы, «с собакой» → pets) и вызови update_trip_params.
2. Город не назван, но есть пожелания («к морю», «тепло», «куда-нибудь») → suggest_destinations и предложи 2–3 варианта с причинами. Не задавай анкету.
3. Город известен → plan_trip. Если пользователь не назвал даты, город отправления или состав (взрослые и дети), plan_trip вернёт need_clarification — задай эти вопросы одним сообщением нумерованным списком и жди ответа. Если ответ неполный, plan_trip снова вернёт need_clarification — спроси только то, что осталось. Не собирай поездку, пока не узнаешь всё или пользователь не скажет «на ваше усмотрение».
4. Пользователь меняет условия → используй точечные инструменты (modify_day, shift_dates, set_constraints, make_cheaper, select_hotel, select_transport), а не plan_trip заново.
5. Других вопросов не задавай: всё остальное решай сам и объясняй выбор.

Правила:
- Цены, наличие, погоду и часы работы бери только из результатов инструментов. Ничего не выдумывай.
- Поле kind: confirmed — данные внешнего API, estimate — расчёт или кэш, demo — синтетика. Отели всегда демо — так и говори.
- Для каждой рекомендации коротко: почему подходит, чем пожертвовали, какой риск.
- Бюджет пользователя — жёсткий лимит. Инструменты сами подбирают варианты в его пределах; не выбирай отель или транспорт, из-за которых он превышается. Если уложиться нельзя даже в самом дешёвом варианте — прямо скажи, сколько не хватает, и предложи: сократить ночи, сдвинуть даты или увеличить бюджет.
- Критичные проблемы состыковки — обязательно скажи о них и предложи решение.
- Реальных покупок и бронирований нет: оформление — демо во вкладке «Оформление».
- Интерфейс уже показывает карточки, карту и бюджет. В чате пиши кратко: 4–8 строк, по-русски, можно **жирный** и списки. Без таблиц. Никаких эмодзи и пиктограмм: вместо них — короткие подписи жирным («**Отель:** …»).
"""

TOOLS = [
    {
        "name": "update_trip_params",
        "description": "Сохранить параметры поездки, извлечённые из запроса. Передавай только то, что известно. "
                       "Списки interests и wishes дополняются, а не заменяются.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "enum": CITY_IDS},
                "origin": {"type": "string", "enum": CITY_IDS, "description": "Откуда едут, по умолчанию moscow"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD, день прибытия"},
                "month": {"type": "integer", "minimum": 1, "maximum": 12},
                "nights": {"type": "integer", "minimum": 1, "maximum": 14, "description": "Число ночей: «5 дней» → 4 ночи"},
                "adults": {"type": "integer", "minimum": 1, "maximum": 8},
                "children": {"type": "integer", "minimum": 0, "maximum": 6},
                "pets": {"type": "boolean"},
                "budget_rub": {"type": "integer", "description": "Общий бюджет на всех, ₽"},
                "interests": {"type": "array", "items": {"type": "string", "enum": INTERESTS}},
                "wishes": {"type": "array", "items": {"type": "string", "enum": ["sea", "warm", "cheap", "center", "culture", "beach"]}},
                "max_travel_hours": {"type": "number"},
                "walking": {"type": "string", "enum": ["normal", "low"]},
                "priority": {"type": "string", "enum": ["balanced", "price", "location", "cancellation"]},
                "transport_pref": {"type": "string", "enum": ["any", "train", "plane"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "suggest_destinations",
        "description": "Подобрать 2–3 направления под пожелания, когда город не задан. Возвращает климат (Open-Meteo), "
                       "оценку стоимости, время в пути, плюсы, минусы и риски.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "plan_trip",
        "description": "Собрать поездку целиком: транспорт, отели (сравнение), места, прогулки по дням, погода, бюджет, "
                       "проверка состыковок. Вызывать после update_trip_params с destination.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_trip_summary",
        "description": "Текущее состояние поездки: выбранные варианты, альтернативы, дни, бюджет, проблемы.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_day_places",
        "description": "Точки дня с id, категориями и ценой — нужно, чтобы убрать или заменить конкретное место.",
        "input_schema": {"type": "object", "properties": {"day": {"type": "integer"}}, "required": ["day"],
                         "additionalProperties": False},
    },
    {
        "name": "select_transport",
        "description": "Выбрать вариант транспорта по id. Пересчитывает окна первого/последнего дня, бюджет и состыковки.",
        "input_schema": {"type": "object", "properties": {"option_id": {"type": "string"}}, "required": ["option_id"],
                         "additionalProperties": False},
    },
    {
        "name": "select_hotel",
        "description": "Выбрать отель по id. Маршруты всех дней перестраиваются от нового отеля, бюджет пересчитывается.",
        "input_schema": {"type": "object", "properties": {"hotel_id": {"type": "string"}}, "required": ["hotel_id"],
                         "additionalProperties": False},
    },
    {
        "name": "modify_day",
        "description": "Изменить один день, остальные не трогать. action: less_walking (устали, меньше ходьбы), "
                       "rain (только крытые места), replace_with_cafe (заменить достопримечательность на кафе; place_id — какую, "
                       "иначе наименее важную), add_category (добавить место категории category), remove_place (убрать place_id), "
                       "more_walking (вернуть обычный темп).",
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {"type": "integer", "minimum": 1},
                "action": {"type": "string", "enum": ["less_walking", "rain", "replace_with_cafe", "add_category", "remove_place", "more_walking"]},
                "category": {"type": "string", "enum": INTERESTS},
                "place_id": {"type": "string"},
            },
            "required": ["day", "action"],
            "additionalProperties": False,
        },
    },
    {
        "name": "shift_dates",
        "description": "Сдвинуть всю поездку на N дней (+ позже, − раньше). Транспорт ищется заново, места сохраняются.",
        "input_schema": {"type": "object", "properties": {"days": {"type": "integer"}}, "required": ["days"],
                         "additionalProperties": False},
    },
    {
        "name": "set_constraints",
        "description": "Изменить ограничения уже собранной поездки (питомец, дети, бюджет, число взрослых, приоритет, темп, ночи). "
                       "Перестраивает только зависимые части.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pets": {"type": "boolean"}, "children": {"type": "integer"}, "budget_rub": {"type": "integer"},
                "clear_budget": {"type": "boolean", "description": "true — пользователь снял ограничение бюджета"},
                "adults": {"type": "integer"}, "nights": {"type": "integer"},
                "priority": {"type": "string", "enum": ["balanced", "price", "location", "cancellation"]},
                "walking": {"type": "string", "enum": ["normal", "low"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "make_cheaper",
        "description": "Удешевить поездку: дешевле транспорт и отель в разумной удалённости, дорогие билеты → бесплатные места.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


# Факты, которые парсер надёжно извлёк из текущего сообщения. Модель иногда путает дни с ночами
# или теряет бюджет, поэтому для этих полей значение парсера важнее аргумента модели.
ANCHORED = ("destination", "origin", "nights", "start_date", "month", "budget_rub", "adults", "children", "pets",
            "budget_none", "delegate")
# пожелания («море», «тепло», «недорого») и интересы модель тоже теряет — их объединяем с её аргументами
LISTS = ("wishes", "interests")
_turn_facts: contextvars.ContextVar[dict] = contextvars.ContextVar("turn_facts", default={})


def begin_turn(trip: Trip, text: str) -> tuple[str | None, str]:
    """Подготовка хода до вызова модели. Возвращает (готовый ответ без модели, пометку для модели).

    Пока агент уточняет детали, вопросы задаёт планировщик: модель на этом этапе путала ответы
    («Нижний Новгород» принимала за новое направление) и уходила в бесконечный цикл инструментов.
    Смена бюджета в готовом плане тоже применяется сразу, не дожидаясь, вызовет ли модель инструмент.
    """
    facts = {k: v for k, v in parse_answer(text, trip).items() if k in ANCHORED or (k in LISTS and v)}
    _turn_facts.set(facts)
    p = trip.params
    if trip.days:
        note = ""
        if facts.get("budget_none") and p.budget_rub:
            planner.set_constraints(trip, clear_budget=True)
            note = "Бюджет снят по просьбе пользователя — план уже пересобран без лимита."
        elif facts.get("budget_rub") and facts["budget_rub"] != p.budget_rub:
            planner.set_constraints(trip, budget_rub=facts["budget_rub"])
            note = f"Новый бюджет {planner.rub(facts['budget_rub'])} уже применён, план пересобран."
        return None, note
    if p.destination and trip.status == "need_info":  # идёт уточнение: применяем ответ и спрашиваем остальное сами
        planner.apply_params(trip, _merge_facts({}, facts), known=list(facts))
        if planner.clarify(trip):
            return planner.clarify_text(trip), ""
        return None, "Пользователь ответил на все уточняющие вопросы — вызови plan_trip и расскажи о поездке."
    if facts.get("destination") and not trip.destination_options:
        planner.apply_params(trip, _merge_facts({}, facts), known=list(facts))
        if planner.clarify(trip):
            return planner.clarify_text(trip), ""
    return None, ""


def clarification_reply(trip: Trip) -> str | None:
    """Если после хода модели всё ещё не хватает данных — вопрос от планировщика."""
    return planner.clarify_text(trip) if not trip.days and planner.clarify(trip) else None


def fallback_reply(trip: Trip) -> str:
    """Модель сделала слишком много шагов: отвечаем по фактическому состоянию поездки, а не заглушкой."""
    from .agent_offline import describe_plan
    if (q := clarification_reply(trip)):
        return q
    if trip.days:
        return describe_plan(trip, intro="Вот текущий план поездки:")
    return "Не удалось разобрать запрос. Напишите, куда и когда хотите поехать, — например: «Казань с 12 по 15 декабря, из Москвы, двое взрослых»."


def _merge_facts(args: dict, facts: dict) -> dict:
    merged = {**args, **{k: v for k, v in facts.items() if k not in LISTS}}
    for k in LISTS:
        if k in facts:
            merged[k] = list(dict.fromkeys([*(args.get(k) or []), *facts[k]]))
    return merged


def _within_budget(trip: Trip, name: str, args: dict) -> dict:
    """Выбор модели не должен выводить поездку за бюджет, если до этого она в него укладывалась."""
    backup = trip.model_copy(deep=True)
    r = planner.select_transport(trip, args["option_id"]) if name == "select_transport" else planner.select_hotel(trip, args["hotel_id"])
    if "error" not in r and trip.budget.over_by and not backup.budget.over_by:
        over = trip.budget.over_by
        trip.__dict__.update(backup.__dict__)
        return {"error": f"Этот вариант выводит поездку за бюджет на {planner.rub(over)} — выбор отменён. "
                         "Предложи пользователю варианты в пределах бюджета или спроси, готов ли он его увеличить."}
    return r


def execute(trip: Trip, name: str, args: dict) -> dict:
    if name == "update_trip_params":
        facts = _turn_facts.get()
        dropped = []
        # город, которого нет в сообщении и среди предложенных вариантов, модель придумала сама
        offered = {o.city_id for o in trip.destination_options}
        if args.get("destination") and "destination" not in facts and args["destination"] not in offered \
                and not trip.params.destination:
            dropped.append("destination")
        # «недорого» — не сумма; бюджет берём только из чисел в сообщении
        if args.get("budget_rub") and "budget_rub" not in facts:
            dropped.append("budget_rub")
        args = _merge_facts({k: v for k, v in args.items() if k not in dropped}, facts)
        # «названо пользователем» — только то, что парсер нашёл в его словах; догадки модели не считаются
        assumptions = planner.apply_params(trip, args, known=[k for k in facts if k in args])
        planner.log_tool(trip, name, ", ".join(f"{k}={v}" for k, v in args.items())[:160])
        out = {"params": trip.params.model_dump(exclude={"assumptions"}), "new_assumptions": assumptions,
               "missing": planner.missing(trip.params)}
        if dropped:
            out["ignored"] = {"fields": dropped, "reason": "Пользователь этого не говорил. Если город не назван — "
                              "вызови suggest_destinations; бюджет не выдумывай."}
        return out
    if name == "suggest_destinations":
        if facts := {k: v for k, v in _turn_facts.get().items() if k != "destination"}:
            planner.apply_params(trip, _merge_facts({}, facts))  # модель могла сразу позвать подбор, не передав пожелания
        return {"options": planner.suggest_destinations(trip)}
    if name == "plan_trip":
        # ответ на уточнение модель может не передать в update_trip_params — берём факты из сообщения сами
        if facts := {k: v for k, v in _turn_facts.get().items() if k != "destination" or not trip.params.destination}:
            planner.apply_params(trip, _merge_facts({}, facts), known=list(facts))
        if qs := planner.clarify(trip):
            return {"need_clarification": qs, "text": planner.clarify_text(trip),
                    "instruction": "Не собирай поездку. Задай пользователю эти вопросы одним сообщением и дождись ответа."}
        return planner.plan_trip(trip)
    if name == "get_trip_summary":
        return planner.summary(trip)
    if name == "list_day_places":
        d = next((x for x in trip.days if x.day == args["day"]), None)
        if not d:
            return {"error": "Нет такого дня"}
        return {"stops": [{"place_id": s.place.id, "name": s.place.name, "cats": s.place.cats, "arrive": s.arrive,
                           "ticket_rub": s.place.ticket_rub, "indoor": s.place.indoor} for s in d.stops],
                "unused_nearby": [{"place_id": p.id, "name": p.name, "cats": p.cats} for p in walks.unused_places(trip)[:10]]}
    if name in ("select_transport", "select_hotel"):
        return _within_budget(trip, name, args)
    if name == "modify_day":
        return planner.modify_day(trip, args["day"], args["action"], args.get("category"), args.get("place_id"))
    if name == "shift_dates":
        return planner.shift_dates(trip, args["days"])
    if name == "set_constraints":
        return planner.set_constraints(trip, **args)
    if name == "make_cheaper":
        return planner.make_cheaper(trip)
    return {"error": f"Неизвестный инструмент {name}"}
