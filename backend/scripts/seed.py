"""Демо-данные: тестовый профиль с двумя сохранёнными пассажирами.

    docker compose exec app backend/.venv/bin/python backend/scripts/seed.py

Повторный запуск ничего не ломает: если профиль уже есть, скрипт только сообщает об этом.
Таблицы создаются автоматически при первом подключении к базе.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import accounts  # noqa: E402

LOGIN, PASSWORD = "demo@waylo.ru", "waylo2026"

try:
    acc, _ = accounts.register(LOGIN, PASSWORD, "Демо", "Пользователь")
except ValueError:
    print(f"Профиль {LOGIN} уже есть")
    sys.exit(0)
accounts.save_guest(acc.id, accounts.Guest(last="Иванова", first="Анна", middle="Сергеевна", birth="1990-05-14",
                                           doc="4510 123456", doc_kind="Паспорт РФ"))
accounts.save_guest(acc.id, accounts.Guest(last="Иванова", first="Мария", middle="Петровна", birth="2018-07-20",
                                           doc="IV-МЮ 123456", doc_kind="Свидетельство о рождении"))
print(f"Создан профиль {LOGIN} / {PASSWORD} с двумя пассажирами")
