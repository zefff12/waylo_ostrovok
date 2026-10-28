"""Обращения в поддержку: пользователь пишет из интерфейса, сотрудник отвечает на /support-admin.

Хранятся в той же SQLite, что и поездки. Браузер держит копию своих обращений и при синхронизации
возвращает их, если сервер их потерял (на бесплатном Render база живёт до перезапуска).
"""
from __future__ import annotations

import json
import os
import random
import string
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .store import _conn, _lock

TOPICS = ("trip", "payment", "bug", "other")


class SupportMessage(BaseModel):
    author: Literal["user", "support"]
    text: str = Field(min_length=1, max_length=4000)
    at: str


class Ticket(BaseModel):
    id: str
    user_id: str
    topic: Literal["trip", "payment", "bug", "other"]
    contact: str | None = Field(default=None, max_length=120)
    trip_id: str | None = None
    status: Literal["open", "answered", "closed"] = "open"
    created_at: str
    messages: list[SupportMessage] = Field(default_factory=list)


def _now() -> str:
    return datetime.now().isoformat(timespec="minutes")


def _table(c) -> None:
    c.execute("CREATE TABLE IF NOT EXISTS support (id TEXT PRIMARY KEY, user_id TEXT, data TEXT)")


def save(t: Ticket) -> Ticket:
    with _lock, _conn() as c:
        _table(c)
        c.execute("REPLACE INTO support (id, user_id, data) VALUES (?,?,?)", (t.id, t.user_id, t.model_dump_json()))
    return t


def get(ticket_id: str) -> Ticket | None:
    with _lock, _conn() as c:
        _table(c)
        row = c.execute("SELECT data FROM support WHERE id=?", (ticket_id,)).fetchone()
    return Ticket.model_validate_json(row[0]) if row else None


def by_user(user_id: str) -> list[Ticket]:
    with _lock, _conn() as c:
        _table(c)
        rows = c.execute("SELECT data FROM support WHERE user_id=? ORDER BY rowid DESC", (user_id,)).fetchall()
    return [Ticket.model_validate_json(r[0]) for r in rows]


def all_tickets() -> list[Ticket]:
    with _lock, _conn() as c:
        _table(c)
        rows = c.execute("SELECT data FROM support ORDER BY rowid DESC LIMIT 500").fetchall()
    return [Ticket.model_validate_json(r[0]) for r in rows]


def create(user_id: str, topic: str, text: str, contact: str | None, trip_id: str | None) -> Ticket:
    tid = "WS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return save(Ticket(id=tid, user_id=user_id, topic=topic, contact=contact or None, trip_id=trip_id,  # type: ignore[arg-type]
                       created_at=_now(), messages=[SupportMessage(author="user", text=text, at=_now())]))


def add_message(t: Ticket, author: str, text: str) -> Ticket:
    t.messages.append(SupportMessage(author=author, text=text, at=_now()))  # type: ignore[arg-type]
    t.status = "answered" if author == "support" else "open"
    return save(t)


def admin_token() -> str | None:
    return os.getenv("SUPPORT_ADMIN_TOKEN") or None


def dump(ts: list[Ticket]) -> list[dict]:
    return json.loads(json.dumps([t.model_dump() for t in ts], ensure_ascii=False))
