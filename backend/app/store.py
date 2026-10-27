"""SQLite: поездки, история диалога с LLM и профиль предпочтений (память между сессиями)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path

from .schemas import Trip

DB_PATH = Path(os.getenv("WAYLO_DB", Path(__file__).resolve().parent.parent / "waylo.sqlite3"))
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.execute("CREATE TABLE IF NOT EXISTS trips (id TEXT PRIMARY KEY, user_id TEXT, data TEXT, messages TEXT, chat TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS profiles (user_id TEXT PRIMARY KEY, data TEXT)")
    return c


def save_trip(trip: Trip, messages: list | dict | None = None, chat: list | None = None) -> None:
    with _lock, _conn() as c:
        row = c.execute("SELECT messages, chat FROM trips WHERE id=?", (trip.id,)).fetchone()
        m = json.dumps(messages, ensure_ascii=False) if messages is not None else (row[0] if row else "[]")
        ch = json.dumps(chat, ensure_ascii=False) if chat is not None else (row[1] if row else "[]")
        c.execute("REPLACE INTO trips (id, user_id, data, messages, chat) VALUES (?,?,?,?,?)",
                  (trip.id, trip.user_id, trip.model_dump_json(), m, ch))


def load_trip(trip_id: str) -> tuple[Trip, list | dict, list] | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT data, messages, chat FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not row:
        return None
    return Trip.model_validate_json(row[0]), json.loads(row[1] or "[]"), json.loads(row[2] or "[]")


def latest_trip(user_id: str) -> str | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT id FROM trips WHERE user_id=? ORDER BY rowid DESC LIMIT 1", (user_id,)).fetchone()
    return row[0] if row else None


def load_profile(user_id: str) -> dict:
    with _lock, _conn() as c:
        row = c.execute("SELECT data FROM profiles WHERE user_id=?", (user_id,)).fetchone()
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
    with _lock, _conn() as c:
        c.execute("REPLACE INTO profiles (user_id, data) VALUES (?,?)", (trip.user_id, json.dumps(prof, ensure_ascii=False)))


def forget(user_id: str) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
