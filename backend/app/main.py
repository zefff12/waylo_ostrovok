"""HTTP API Waylo."""
from __future__ import annotations

import logging
import os
import random
import secrets
import re
import string
import time
import uuid
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
load_dotenv()

from fastapi import FastAPI, Header, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import agent_gigachat, agent_llm, agent_offline, connections, integrations, planner, store, support  # noqa: E402
from .data import CITIES  # noqa: E402
from .schemas import Guest, Order, Trip  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("waylo")

app = FastAPI(title="Waylo API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ChatIn(BaseModel):
    trip_id: str | None = None
    user_id: str = "anonymous"
    message: str
    mode: str = "auto"  # auto | llm | offline


class ChatOut(BaseModel):
    trip: Trip
    reply: str
    agent: str
    elapsed_ms: int
    chat: list[dict]


class SelectIn(BaseModel):
    option_id: str


# Номер карты на сервер не приходит: интерфейс присылает только платёжную систему и последние 4 цифры.
CARD = r"^(Visa|Mastercard|МИР|Карта) •••• \d{4}$"


class CheckoutIn(BaseModel):
    guests: list[Guest] = Field(default_factory=list)
    card: str | None = Field(default=None, pattern=CARD)


class RestoreIn(BaseModel):
    trip: Trip
    chat: list[dict] = Field(default_factory=list)


class ExtraIn(BaseModel):
    kind: str  # early_checkin | transfer
    card: str | None = Field(default=None, pattern=CARD)


def _get(trip_id: str) -> tuple[Trip, list, list]:
    got = store.load_trip(trip_id)
    if not got:
        raise HTTPException(404, "Поездка не найдена")
    return got


# Провайдер LLM: WAYLO_LLM = auto | claude | gigachat | offline. auto — первый, для которого задан ключ.
PROVIDERS = {
    "claude": (agent_llm, (anthropic.APIConnectionError, anthropic.APIStatusError)),
    "gigachat": (agent_gigachat, (agent_gigachat.GigaChatError,)),
}
PROVIDER_LABEL = {"claude": "Claude", "gigachat": "GigaChat"}


def provider() -> str:
    want = os.getenv("WAYLO_LLM", "auto").lower()
    if want in PROVIDERS:
        return want if PROVIDERS[want][0].available() else "offline"
    if want == "offline":
        return "offline"
    return next((name for name, (mod, _) in PROVIDERS.items() if mod.available()), "offline")


def _histories(messages) -> dict:
    """История диалога хранится отдельно для каждого провайдера: форматы сообщений у них разные."""
    if isinstance(messages, list):
        return {"claude": messages} if messages else {}
    return messages or {}


_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿⏩-⏺️‍⃣]")


def youtube_id(url: str) -> str | None:
    """ID ролика из youtu.be/…, youtube.com/watch?v=…, /embed/…, /shorts/… или сам ID."""
    m = re.search(r"(?:youtu\.be/|[?&]v=|/embed/|/shorts/|/live/)([\w-]{11})", url or "") or re.fullmatch(r"([\w-]{11})", (url or "").strip())
    return m.group(1) if m else None


def strip_emoji(text: str) -> str:
    """Интерфейс без эмодзи: LLM иногда добавляет их вопреки инструкции."""
    out = re.sub("([0-9#*])️?⃣", r"\1. ", text)  # «1️⃣» → «1. »
    out = re.sub(r"[ \t]{2,}", " ", _EMOJI.sub("", out))
    return "\n".join(line.lstrip() if line.strip() else "" for line in out.split("\n")).strip()


def _note_ui(histories: dict, user_text: str, reply: str) -> None:
    """Сообщить LLM об изменении, сделанном кнопкой, — дописываем в конец, историю не редактируем."""
    for msgs in histories.values():
        if msgs:
            msgs.append({"role": "user", "content": user_text})
            msgs.append({"role": "assistant", "content": reply})


@app.get("/api/health")
def health() -> dict:
    p = provider()
    model = {"claude": agent_llm.MODEL, "gigachat": agent_gigachat.MODEL}.get(p)
    return {"ok": True, "agent": p, "model": model, "provider_label": PROVIDER_LABEL.get(p),
            "integrations": integrations.status(), "cities": [{"id": c.id, "name": c.name, "country": c.country, "tags": c.tags} for c in CITIES.values()],
            # ключ JavaScript API публичный по устройству: он защищён ограничением по HTTP Referer в кабинете Яндекса
            "yandex_js_key": os.getenv("YANDEX_JS_API_KEY") or None,
            "home_youtube_id": youtube_id(os.getenv("WAYLO_HOME_VIDEO", "https://youtu.be/lyh2kAjcmSY"))}


@app.post("/api/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    t0 = time.time()
    if body.trip_id and (got := store.load_trip(body.trip_id)):
        trip, messages, chat_log = got
    else:
        trip, messages, chat_log = Trip(id=uuid.uuid4().hex[:10], user_id=body.user_id), [], []
    profile = store.load_profile(body.user_id) if not trip.days else None
    chat_log.append({"role": "user", "text": body.message, "at": datetime.now().strftime("%H:%M")})
    histories = _histories(messages)
    agent = "offline" if body.mode == "offline" else provider()
    if agent in PROVIDERS:
        module, errors = PROVIDERS[agent]
        label = PROVIDER_LABEL[agent]
        backup = trip.model_copy(deep=True)
        msgs = list(histories.get(agent, []))
        try:
            reply = module.handle(trip, body.message, msgs, profile)
            histories[agent] = msgs
        except errors as e:
            log.warning("%s недоступен: %s", label, e)
            trip = backup
            reason = str(e) if agent == "gigachat" else type(e).__name__
            planner.log_tool(trip, agent, f"LLM недоступна ({reason}) — ответил офлайн-агент", ok=False)
            reply = agent_offline.handle(trip, body.message, profile)
            reply = f"**{label} недоступен** ({reason}), ответил офлайн-агент.\n\n" + reply
            agent = "offline-fallback"
    else:
        reply = agent_offline.handle(trip, body.message, profile)
        agent = "offline"
    reply = strip_emoji(reply)
    chat_log.append({"role": "assistant", "text": reply, "agent": agent, "at": datetime.now().strftime("%H:%M")})
    store.save_trip(trip, histories, chat_log)
    if trip.days:
        store.remember(trip)
    return ChatOut(trip=trip, reply=reply, agent=agent, elapsed_ms=int((time.time() - t0) * 1000), chat=chat_log)


@app.get("/api/trips/{trip_id}")
def get_trip(trip_id: str) -> dict:
    trip, _, chat_log = _get(trip_id)
    return {"trip": trip, "chat": chat_log}


@app.post("/api/trips/restore")
def restore_trip(body: RestoreIn) -> dict:
    """Вернуть поездку из копии в браузере. На бесплатном Render база живёт до перезапуска сервиса,
    поэтому браузер хранит последнюю поездку и при необходимости отдаёт её обратно."""
    if got := store.load_trip(body.trip.id):
        return {"trip": got[0], "chat": got[2]}
    store.save_trip(body.trip, {}, body.chat[-200:])
    return {"trip": body.trip, "chat": body.chat[-200:]}


class SupportIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=40)
    topic: str = Field(pattern="^(trip|payment|bug|other)$")
    text: str = Field(min_length=10, max_length=4000)
    contact: str | None = Field(default=None, max_length=120)
    trip_id: str | None = Field(default=None, max_length=40)


class SupportReplyIn(BaseModel):
    user_id: str | None = None
    text: str = Field(min_length=1, max_length=4000)


class SupportSyncIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=40)
    tickets: list[support.Ticket] = Field(default_factory=list, max_length=50)


@app.post("/api/support")
def support_create(body: SupportIn) -> dict:
    t = support.create(body.user_id, body.topic, body.text.strip(), (body.contact or "").strip(), body.trip_id)
    log.info("support ticket %s (%s)", t.id, t.topic)
    return t.model_dump()


@app.post("/api/support/sync")
def support_sync(body: SupportSyncIn) -> dict:
    """Обращения пользователя; копии из браузера, которых сервер не знает, восстанавливаются."""
    known = {t.id for t in support.by_user(body.user_id)}
    for t in body.tickets:
        if t.id not in known and t.user_id == body.user_id:
            support.save(t)
    return {"tickets": support.dump(support.by_user(body.user_id))}


@app.post("/api/support/{ticket_id}/messages")
def support_user_message(ticket_id: str, body: SupportReplyIn) -> dict:
    t = support.get(ticket_id)
    if not t or t.user_id != body.user_id:
        raise HTTPException(404, "Обращение не найдено")
    return support.add_message(t, "user", body.text.strip()).model_dump()


def _admin(token: str | None) -> None:
    expected = support.admin_token()
    if not expected:
        raise HTTPException(503, "Панель поддержки не настроена: задайте SUPPORT_ADMIN_TOKEN в переменных окружения")
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(401, "Неверный ключ доступа")


@app.get("/api/support/admin")
def support_admin_list(x_admin_token: str | None = Header(default=None)) -> dict:
    _admin(x_admin_token)
    return {"tickets": support.dump(support.all_tickets())}


@app.post("/api/support/admin/{ticket_id}/reply")
def support_admin_reply(ticket_id: str, body: SupportReplyIn, x_admin_token: str | None = Header(default=None)) -> dict:
    _admin(x_admin_token)
    t = support.get(ticket_id)
    if not t:
        raise HTTPException(404, "Обращение не найдено")
    return support.add_message(t, "support", body.text.strip()).model_dump()


@app.post("/api/support/admin/{ticket_id}/close")
def support_admin_close(ticket_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _admin(x_admin_token)
    t = support.get(ticket_id)
    if not t:
        raise HTTPException(404, "Обращение не найдено")
    t.status = "closed"
    return support.save(t).model_dump()


@app.get("/api/users/{user_id}/latest")
def latest(user_id: str) -> dict:
    return {"trip_id": store.latest_trip(user_id), "profile": store.load_profile(user_id)}


@app.delete("/api/users/{user_id}/profile")
def forget(user_id: str) -> dict:
    store.forget(user_id)
    return {"ok": True}


@app.post("/api/trips/{trip_id}/destination")
def choose_destination(trip_id: str, body: SelectIn) -> dict:
    trip, messages, chat_log = _get(trip_id)
    if body.option_id not in CITIES:
        raise HTTPException(400, "Неизвестный город")
    planner.apply_params(trip, {"destination": body.option_id})
    if planner.clarify(trip):
        text = planner.clarify_text(trip)
    else:
        planner.plan_trip(trip)
        text = agent_offline.describe_plan(trip, intro=f"Выбрали {CITIES[body.option_id].name}. Собрал поездку:")
    chat_log.append({"role": "assistant", "text": text, "agent": "ui", "at": datetime.now().strftime("%H:%M")})
    histories = _histories(messages)  # чтобы LLM знала о выборе, сделанном кнопкой
    _note_ui(histories, f"[Пользователь выбрал в интерфейсе направление {body.option_id}; "
             + ("поездка собрана через plan_trip.]" if trip.days else f"агент задал уточняющие вопросы: {text}]"),
             "Принято, поездка собрана." if trip.days else "Жду ответа пользователя.")
    store.save_trip(trip, histories, chat_log)
    return {"trip": trip, "chat": chat_log}


def _ui_change(trip_id: str, fn, *args) -> dict:
    trip, messages, chat_log = _get(trip_id)
    r = fn(trip, *args)
    if "error" in r:
        raise HTTPException(400, r["error"])
    entry = trip.changes[-1] if trip.changes else None
    if entry:
        chat_log.append({"role": "assistant", "agent": "ui", "at": datetime.now().strftime("%H:%M"),
                         "text": f"**{entry.summary}**\n" + "\n".join(f"• {d}" for d in entry.details)})
    histories = _histories(messages)
    if entry:
        _note_ui(histories, f"[Изменение в интерфейсе: {entry.summary}. {'; '.join(entry.details)}]", "Принято.")
    store.save_trip(trip, histories, chat_log)
    return {"trip": trip, "chat": chat_log}


@app.post("/api/trips/{trip_id}/transport")
def select_transport(trip_id: str, body: SelectIn) -> dict:
    return _ui_change(trip_id, planner.select_transport, body.option_id)


@app.post("/api/trips/{trip_id}/hotel")
def select_hotel(trip_id: str, body: SelectIn) -> dict:
    return _ui_change(trip_id, planner.select_hotel, body.option_id)


class DayIn(BaseModel):
    action: str
    category: str | None = None
    place_id: str | None = None


@app.post("/api/trips/{trip_id}/days/{day}")
def modify_day(trip_id: str, day: int, body: DayIn) -> dict:
    return _ui_change(trip_id, planner.modify_day, day, body.action, body.category, body.place_id)


@app.post("/api/trips/{trip_id}/checkout")
def checkout(trip_id: str, body: CheckoutIn) -> dict:
    """Демо-оформление: никаких платежей и бронирований, только сводка и номер заказа с пометкой DEMO."""
    trip, messages, chat_log = _get(trip_id)
    if not trip.days:
        raise HTTPException(400, "Поездка ещё не собрана")
    trip.connections = connections.check(trip)
    if connections.has_critical(trip):
        crit = next(c for c in trip.connections if c.level == "critical")
        raise HTTPException(409, f"Оформление заблокировано: {crit.text}. {crit.fix or ''}")
    kind_ru = {"confirmed": "реальные данные", "estimate": "оценка", "demo": "демо"}
    if len(body.guests) != trip.params.travelers:
        raise HTTPException(422, f"Нужны данные всех путешественников: {trip.params.travelers}, получено {len(body.guests)}")
    lines = [f"{i.title} — {planner.rub(i.amount)} ({kind_ru.get(i.kind, i.kind)})" for i in trip.budget.items]
    oid = "WAYLO-DEMO-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    trip.order = Order(order_id=oid, created_at=datetime.now().isoformat(timespec="minutes"), total=trip.budget.total,
                       lines=lines, payment=body.card, guests=body.guests)
    trip.order.offers = planner.extra_offers(trip)
    trip.status = "purchased"
    planner.log_tool(trip, "demo_checkout", f"{oid}: {planner.rub(trip.budget.total)}, гостей: {len(body.guests)} — оплата не производилась")
    paid = f" Оплата: {body.card} (демо, деньги не списаны)." if body.card else " Реальной оплаты и брони нет."
    chat_log.append({"role": "assistant", "agent": "ui", "at": datetime.now().strftime("%H:%M"),
                     "text": f"Демо-заказ **{oid}** оформлен на {planner.rub(trip.budget.total)}.{paid}\n"
                             "После покупки могу оформить ранний заезд или трансфер до отеля — каждую услугу оплачиваете отдельно."})
    store.save_trip(trip, messages, chat_log)
    return {"trip": trip, "chat": chat_log}


@app.post("/api/trips/{trip_id}/extras")
def extras(trip_id: str, body: ExtraIn) -> dict:
    trip, messages, chat_log = _get(trip_id)
    if trip.status != "purchased" or not trip.order:
        raise HTTPException(400, "Доступно после оформления")
    r = planner.add_extra(trip, body.kind)
    if "error" in r:
        raise HTTPException(409, r["error"])
    card = f", карта {body.card}" if body.card else ""
    trip.order.post_purchase.append(f"{r['added']} — {planner.rub(r['amount'])}, оплачено{card} (демо, деньги не списаны)")
    trip.order.total = trip.budget.total
    trip.order.offers = planner.extra_offers(trip)
    chat_log.append({"role": "assistant", "agent": "ui", "at": datetime.now().strftime("%H:%M"),
                     "text": f"Оплачено: **{r['added']}** — {planner.rub(r['amount'])}. Итого по заказу теперь {planner.rub(trip.budget.total)}."})
    store.save_trip(trip, messages, chat_log)
    return {"trip": trip, "chat": chat_log}


# Собранный frontend (npm run build) раздаётся тем же сервером — удобно для демо одной командой.
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
