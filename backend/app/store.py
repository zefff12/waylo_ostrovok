"""Поездки, история диалога с LLM и профиль предпочтений (память между сессиями)."""
from __future__ import annotations

import json
import time

from .db import connect
from .schemas import Trip

UPSERT_TRIP = ("INSERT INTO trips (id, user_id, data, messages, chat, updated) VALUES (?,?,?,?,?,?) "
               "ON CONFLICT (id) DO UPDATE SET user_id=excluded.user_id, data=excluded.data, messages=excluded.messages, "
               "chat=excluded.chat, updated=excluded.updated")


def save_trip(trip: Trip, messages: list | dict | None = None, chat: list | None = None) -> None:
    with connect() as c:
        row = c.one("SELECT messages, chat FROM trips WHERE id=?", (trip.id,))
        m = json.dumps(messages, ensure_ascii=False) if messages is not None else (row[0] if row else "[]")
        ch = json.dumps(chat, ensure_ascii=False) if chat is not None else (row[1] if row else "[]")
        c.execute(UPSERT_TRIP, (trip.id, trip.user_id, trip.model_dump_json(), m, ch, time.time()))


def load_trip(trip_id: str) -> tuple[Trip, list | dict, list] | None:
    with connect() as c:
        row = c.one("SELECT data, messages, chat FROM trips WHERE id=?", (trip_id,))
    if not row:
        return None
    return Trip.model_validate_json(row[0]), json.loads(row[1] or "[]"), json.loads(row[2] or "[]")


def latest_trip(user_id: str) -> str | None:
    with connect() as c:
        row = c.one("SELECT id FROM trips WHERE user_id=? ORDER BY updated DESC LIMIT 1", (user_id,))
    return row[0] if row else None


def trips_of(user_id: str, limit: int = 50) -> list[Trip]:
    with connect() as c:
        rows = c.all("SELECT data FROM trips WHERE user_id=? ORDER BY updated DESC LIMIT ?", (user_id, limit))
    return [Trip.model_validate_json(r[0]) for r in rows]


def reassign(old_user: str, new_user: str) -> int:
    """Поездки, собранные до входа в аккаунт, переходят в профиль."""
    moved = 0
    for t in trips_of(old_user, 200):
        t.user_id = new_user
        save_trip(t)
        moved += 1
    with connect() as c:
        if (row := c.one("SELECT data FROM profiles WHERE user_id=?", (old_user,))) and not load_profile(new_user):
            c.execute("INSERT INTO profiles (user_id, data) VALUES (?,?) ON CONFLICT (user_id) DO UPDATE SET data=excluded.data",
                      (new_user, row[0]))
    return moved


def load_profile(user_id: str) -> dict:
    with connect() as c:
        row = c.one("SELECT data FROM profiles WHERE user_id=?", (user_id,))
    return json.loads(row[0]) if row else {}


def remember(trip: Trip) -> None:
    """Запоминаем устойчивые предпочтения, а не конкретную поездку."""
    if trip.user_id == "anonymous":
        return
    p = trip.params
    prof = load_profile(trip.user_id)
    prof["interests"] = list(dict.fromkeys([*p.interests, *prof.get("interests", [])]))[:6]
    if p.pets:
        prof["pets"] = True
    if p.children:
        prof["children"] = p.children
    if p.walking == "low":
        prof["walking"] = "low"
    prof["origin"] = p.origin
    if p.priority != "balanced":
        prof["priority"] = p.priority
    with connect() as c:
        c.execute("INSERT INTO profiles (user_id, data) VALUES (?,?) ON CONFLICT (user_id) DO UPDATE SET data=excluded.data",
                  (trip.user_id, json.dumps(prof, ensure_ascii=False)))


def forget(user_id: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
