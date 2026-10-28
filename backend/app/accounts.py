"""Профиль пользователя: регистрация, вход, сессии и сохранённые пассажиры.

Пароль хранится как PBKDF2-SHA256 с солью, сессия — случайный токен, в базе лежит только его хеш.
Без входа поездку можно собрать, но нельзя оплатить.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import uuid
from collections import defaultdict

from pydantic import BaseModel, Field

from .db import connect

ITERATIONS = 200_000
SESSION_TTL = 60 * 60 * 24 * 30  # 30 дней
_fails: dict[str, list[float]] = defaultdict(list)  # защита от перебора пароля: попытки входа по логину


class Account(BaseModel):
    id: str
    login: str  # e-mail в нижнем регистре или телефон в формате +79991234567
    last_name: str
    first_name: str
    created: float


class Guest(BaseModel):
    """Сохранённый пассажир. Номер документа хранится полностью — его подставляют при оформлении."""
    id: str = ""
    last: str = Field(min_length=1, max_length=40)
    first: str = Field(min_length=1, max_length=40)
    middle: str = Field(default="", max_length=40)
    birth: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    doc: str = Field(default="", max_length=20)
    doc_kind: str = Field(default="", max_length=40)


def normalize_login(raw: str) -> str | None:
    s = raw.strip().lower()
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zа-я]{2,}", s):
        return s
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10 and digits[0] == "9":
        return "+7" + digits
    return None


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def register(login: str, password: str, last_name: str, first_name: str) -> tuple[Account, str]:
    salt = secrets.token_hex(16)
    acc = Account(id="acc_" + uuid.uuid4().hex[:12], login=login, last_name=last_name, first_name=first_name, created=time.time())
    data = {**acc.model_dump(), "salt": salt, "pw": _hash(password, salt)}
    with connect() as c:
        if c.one("SELECT id FROM accounts WHERE login=?", (login,)):
            raise ValueError("Аккаунт с такой почтой или телефоном уже есть — войдите")
        c.execute("INSERT INTO accounts (id, login, data, created) VALUES (?,?,?,?)", (acc.id, login, json.dumps(data), acc.created))
    return acc, new_session(acc.id)


def login(login_: str, password: str) -> tuple[Account, str]:
    now = time.time()
    _fails[login_] = [t for t in _fails[login_] if now - t < 300]
    if len(_fails[login_]) >= 8:
        raise PermissionError("Слишком много попыток. Подождите пять минут")
    with connect() as c:
        row = c.one("SELECT data FROM accounts WHERE login=?", (login_,))
    data = json.loads(row[0]) if row else None
    if not data or not secrets.compare_digest(_hash(password, data["salt"]), data["pw"]):
        _fails[login_].append(now)
        raise PermissionError("Неверная почта, телефон или пароль")
    _fails.pop(login_, None)
    acc = Account(**{k: data[k] for k in Account.model_fields})
    return acc, new_session(acc.id)


def new_session(account_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with connect() as c:
        c.execute("INSERT INTO sessions (token_hash, account_id, created) VALUES (?,?,?)", (_token_hash(token), account_id, time.time()))
    return token


def by_token(token: str | None) -> Account | None:
    if not token:
        return None
    with connect() as c:
        row = c.one("SELECT account_id, created FROM sessions WHERE token_hash=?", (_token_hash(token),))
        if not row or time.time() - row[1] > SESSION_TTL:
            return None
        acc = c.one("SELECT data FROM accounts WHERE id=?", (row[0],))
    if not acc:
        return None
    data = json.loads(acc[0])
    return Account(**{k: data[k] for k in Account.model_fields})


def logout(token: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def guests(account_id: str) -> list[Guest]:
    with connect() as c:
        rows = c.all("SELECT data FROM guests WHERE account_id=? ORDER BY updated DESC", (account_id,))
    return [Guest.model_validate_json(r[0]) for r in rows]


def save_guest(account_id: str, g: Guest) -> Guest:
    """Тот же человек (ФИО + дата рождения) обновляется, а не дублируется."""
    mine = guests(account_id)
    if g.id and g.id not in {x.id for x in mine}:
        g.id = ""  # чужой или устаревший id: сохраняем как нового пассажира, а не поверх чужого
    same = next((x for x in mine if (x.last.lower(), x.first.lower(), x.birth) == (g.last.lower(), g.first.lower(), g.birth)), None)
    g.id = g.id or (same.id if same else "g_" + uuid.uuid4().hex[:10])
    with connect() as c:
        c.execute("INSERT INTO guests (id, account_id, data, updated) VALUES (?,?,?,?) ON CONFLICT (id) DO UPDATE "
                  "SET data=excluded.data, updated=excluded.updated", (g.id, account_id, g.model_dump_json(), time.time()))
    return g


def delete_guest(account_id: str, guest_id: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM guests WHERE id=? AND account_id=?", (guest_id, account_id))
