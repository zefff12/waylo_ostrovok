# Waylo (О!дин запрос)

ИИ-агент для путешествий: по одному сообщению уточняет недостающее, подбирает направление, дорогу и отель в пределах бюджета, строит прогулки по дням с картой и доводит поездку до демо-оплаты в профиле.

- Видео-скринкаст: https://disk.yandex.ru/d/FWfNhPAEZTHawA
- Развёрнутый сервис: https://waylo-cfp5.onrender.com

## Быстрый старт

```bash
git clone https://github.com/zefff12/waylo_ostrovok.git
cd waylo_ostrovok
cp .env.example .env   # ключи необязательны: без них работает агент на правилах
docker compose up --build
# открыть http://localhost:8080
```

## Зависимости и переменные окружения

Рекомендованные ресурсы:
- 1 CPU core
- 1 GB RAM

- Postgres 16 (в `docker-compose.yml` как `db`)
- Redis не используется

- `APP_PORT` (по умолчанию `8080`)
- `DATABASE_URL` (пример: `postgresql://waylo:waylo@db:5432/waylo`)
- `WAYLO_LLM` (по умолчанию `auto`; варианты: `gigachat`, `claude`, `offline`)
- `GIGACHAT_CREDENTIALS` (по умолчанию пусто; ключ авторизации GigaChat API)
- `GIGACHAT_MODEL` (по умолчанию `GigaChat-2-Max`)
- `ANTHROPIC_API_KEY` (по умолчанию пусто)
- `WAYLO_MODEL` (по умолчанию `claude-haiku-5-5`)
- `TRAVELPAYOUTS_TOKEN` (по умолчанию пусто; цены перелётов Aviasales)
- `DGIS_API_KEY` (по умолчанию пусто; кафе рядом из 2ГИС)
- `YANDEX_JS_API_KEY` (по умолчанию пусто; без ключа карта OpenStreetMap)
- `WAYLO_HOME_VIDEO` (по умолчанию `https://youtu.be/lyh2kAjcmSY`)
- `SUPPORT_ADMIN_TOKEN` (по умолчанию пусто; ключ страницы `/support-admin`)

## Сидирование

```bash
# таблицы создаются при первом запуске; создаём тестового пользователя с двумя сохранёнными гостями
docker compose exec app bash -lc "backend/.venv/bin/python backend/scripts/seed.py"
```

## Маршруты/доступ

- `/` — UI
- `/health` — 200 OK, JSON `{ "status": "ok" }`
- Тестовый пользователь: `demo@waylo.ru / waylo2026`
