"""Подключение к базе: PostgreSQL, если задан DATABASE_URL, иначе локальный файл SQLite.

Запросы пишутся один раз с плейсхолдером «?»; для PostgreSQL он заменяется на «%s».
Upsert через INSERT … ON CONFLICT … DO UPDATE одинаково работает в обеих СУБД.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = Path(os.getenv("WAYLO_DB", Path(__file__).resolve().parent.parent / "waylo.sqlite3"))

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS trips (id TEXT PRIMARY KEY, user_id TEXT, data TEXT, messages TEXT, chat TEXT, updated DOUBLE PRECISION)",
    "CREATE TABLE IF NOT EXISTS profiles (user_id TEXT PRIMARY KEY, data TEXT)",
    "CREATE TABLE IF NOT EXISTS support (id TEXT PRIMARY KEY, user_id TEXT, data TEXT, updated DOUBLE PRECISION)",
    "CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, login TEXT UNIQUE, data TEXT, created DOUBLE PRECISION)",
    "CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, account_id TEXT, created DOUBLE PRECISION)",
    "CREATE TABLE IF NOT EXISTS guests (id TEXT PRIMARY KEY, account_id TEXT, data TEXT, updated DOUBLE PRECISION)",
    "CREATE INDEX IF NOT EXISTS trips_user ON trips (user_id)",
    "CREATE INDEX IF NOT EXISTS guests_account ON guests (account_id)",
]
# старые локальные базы SQLite создавались без колонки updated
MIGRATIONS = ["ALTER TABLE trips ADD COLUMN updated DOUBLE PRECISION", "ALTER TABLE support ADD COLUMN updated DOUBLE PRECISION"]

_lock = threading.RLock()  # вложенные connect() в одном потоке не должны блокировать друг друга
_ready = False


class _Conn:
    def __init__(self, raw: Any):
        self.raw = raw

    def execute(self, sql: str, params: tuple = ()) -> Any:
        if PG:
            sql = sql.replace("?", "%s")
        cur = self.raw.cursor()
        cur.execute(sql, params)
        return cur

    def one(self, sql: str, params: tuple = ()) -> tuple | None:
        return self.execute(sql, params).fetchone()

    def all(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self.execute(sql, params).fetchall()


def _open() -> Any:
    if PG:
        import psycopg  # только когда нужна PostgreSQL

        return psycopg.connect(DATABASE_URL, autocommit=True, connect_timeout=10)
    c = sqlite3.connect(SQLITE_PATH)
    c.isolation_level = None  # автокоммит, как у PostgreSQL выше
    return c


def _init(c: _Conn) -> None:
    global _ready
    for s in SCHEMA:
        c.execute(s)
    if not PG:
        for m in MIGRATIONS:
            try:
                c.execute(m)
            except sqlite3.OperationalError:
                pass  # колонка уже есть
    _ready = True


@contextmanager
def connect() -> Iterator[_Conn]:
    raw = _open()
    try:
        c = _Conn(raw)
        if not _ready:
            with _lock:
                if not _ready:
                    _init(c)
        if PG:
            yield c
        else:
            with _lock:  # SQLite не любит одновременную запись из нескольких потоков
                yield c
    finally:
        raw.close()


def kind() -> str:
    return "postgresql" if PG else "sqlite"
