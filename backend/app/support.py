from __future__ import annotations

import json
import os
import random
import string
import time
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .db import connect

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


def save(t: Ticket) -> Ticket:
    with connect() as c:
        c.execute("INSERT INTO support (id, user_id, data, updated) VALUES (?,?,?,?) ON CONFLICT (id) DO UPDATE "
                  "SET user_id=excluded.user_id, data=excluded.data, updated=excluded.updated",
                  (t.id, t.user_id, t.model_dump_json(), time.time()))
    return t


def get(ticket_id: str) -> Ticket | None:
    with connect() as c:
        row = c.one("SELECT data FROM support WHERE id=?", (ticket_id,))
    return Ticket.model_validate_json(row[0]) if row else None


def by_user(user_id: str) -> list[Ticket]:
    with connect() as c:
        rows = c.all("SELECT data FROM support WHERE user_id=? ORDER BY updated DESC", (user_id,))
    return [Ticket.model_validate_json(r[0]) for r in rows]


def all_tickets() -> list[Ticket]:
    with connect() as c:
        rows = c.all("SELECT data FROM support ORDER BY updated DESC LIMIT 500")
    return [Ticket.model_validate_json(r[0]) for r in rows]


def create(user_id: str, topic: str, text: str, contact: str | None, trip_id: str | None) -> Ticket:
    tid = "WS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return save(Ticket(id=tid, user_id=user_id, topic=topic, contact=contact or None, trip_id=trip_id,
                       created_at=_now(), messages=[SupportMessage(author="user", text=text, at=_now())]))


def add_message(t: Ticket, author: str, text: str) -> Ticket:
    t.messages.append(SupportMessage(author=author, text=text, at=_now()))
    t.status = "answered" if author == "support" else "open"
    return save(t)


def admin_token() -> str | None:
    return os.getenv("SUPPORT_ADMIN_TOKEN") or None


def dump(ts: list[Ticket]) -> list[dict]:
    return json.loads(json.dumps([t.model_dump() for t in ts], ensure_ascii=False))
