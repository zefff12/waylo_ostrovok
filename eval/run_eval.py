from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("WAYLO_DB", str(Path(tempfile.gettempdir()) / "waylo_eval.sqlite3"))
Path(os.environ["WAYLO_DB"]).unlink(missing_ok=True)

from fastapi.testclient import TestClient

from app.main import PROVIDERS, app, provider

CASES = [
    ("СПб на 5 дней, 45к", ["Хочу на пять дней в Санкт-Петербург в ноябре. Бюджет — 45 000 рублей на двоих. Любим красивые улицы, необычные кафе, музеи и атмосферные места для фотографий. Хотим жить недалеко от центра"],
     lambda t: (len(t["days"]) == 5 and t["budget"]["limit"] == 45000, "5 дней и лимит 45 000")),
    ("Демо-сценарий: правка дня 2", ["Трёхдневная поездка в Петербург, бюджет 40 тысяч, архитектура, музеи и необычные кафе",
                                      "На второй день хочу меньше ходить и заменить одну достопримечательность на кафе"],
     lambda t: (t["days"][1]["less_walking"] and any("cafe" in s["place"]["cats"] for s in t["days"][1]["stops"]), "день 2: меньше ходьбы + кафе")),
    ("Размытый запрос → направления", ["Хочу куда-нибудь к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов"],
     lambda t: (len(t["destination_options"]) >= 2, "2–3 направления")),
    ("Размытый → выбор → план", ["Хочу к морю в ноябре, недорого", "Сочи"],
     lambda t: (t["params"]["destination"] == "sochi" and len(t["days"]) > 0, "собран Сочи")),
    ("Питомец", ["Калининград на выходные с собакой"],
     lambda t: (_hotel(t)["pets_allowed"], "отель разрешает животных")),
    ("Питомец добавлен позже", ["Казань на 3 дня", "с нами едет собака"],
     lambda t: (t["params"]["pets"] and _hotel(t)["pets_allowed"], "пересобран отель под питомца")),
    ("Сдвиг дат", ["Нижний Новгород на 3 дня в декабре", "а если на два дня позже?"],
     lambda t: (any("сдвинута" in c["summary"] for c in t["changes"]), "даты сдвинуты без поиска с нуля")),
    ("Бюджет превышен", ["Дубай на неделю вдвоём, бюджет 60 тысяч"],
     lambda t: (t["budget_gap"] is not None and t["budget_gap"]["min_total"] > 60000, "«ничего не найдено» и минимальная цена")),
    ("Сделай дешевле", ["Москва на 4 дня, хотим музеи", "сделай дешевле"],
     lambda t: (any(c["summary"] == "Сделали дешевле" for c in t["changes"]), "удешевление выполнено")),
    ("Дождь", ["Петербург на 3 дня", "на второй день дождь"],
     lambda t: (t["days"][1]["indoor_only"] and all(s["place"]["indoor"] for s in t["days"][1]["stops"]), "день 2 только под крышей")),
    ("Устали", ["Казань на 2 дня", "мы устали, не хотим много ходить"],
     lambda t: (t["days"][0]["less_walking"], "меньше ходьбы")),
    ("Добавить музей", ["Санкт-Петербург на 4 дня", "добавь музей на третий день"],
     lambda t: (any("museum" in s["place"]["cats"] for s in t["days"][2]["stops"]), "в дне 3 есть музей")),
    ("Смена отеля", ["Москва на 3 дня", "поменяй отель на подешевле"],
     lambda t: (any(c["summary"].startswith("Выбран отель") for c in t["changes"]), "отель сменён, маршруты пересчитаны")),
    ("Конкретные даты", ["Казань с 14 по 16 декабря из Петербурга"],
     lambda t: (t["params"]["start_date"].endswith("12-14") and t["params"]["nights"] == 2 and t["params"]["origin"] == "spb", "даты и город отправления")),
    ("Поездом", ["В Петербург на поезде на выходные"],
     lambda t: (_transport(t)["mode"] == "train", "выбран поезд")),
    ("Семья с детьми", ["Анталья на неделю с двумя детьми"],
     lambda t: (t["params"]["children"] == 2 and _hotel(t)["kids_friendly"], "отель подходит детям")),
    ("Соло", ["Еду одна в Стамбул на 4 дня, люблю кофейни и необычные места"],
     lambda t: (t["params"]["adults"] == 1, "1 путешественник")),
    ("Неизвестный город", ["Хочу в Улан-Удэ"],
     lambda t: (True, "не падает")),
    ("Ближнее зарубежье", ["Ереван на 4 дня вдвоём, любим вино и старый город"],
     lambda t: (t["params"]["destination"] == "yerevan" and len(t["days"]) == 4, "собран Ереван")),
    ("Байкал зимой", ["На Байкал в феврале на 5 дней"],
     lambda t: (t["params"]["destination"] == "irkutsk" and _transport(t)["mode"] == "plane", "Иркутск, самолёт")),
    ("Город без аэропорта", ["Выходные во Владимире и Суздале"],
     lambda t: (t["params"]["destination"] == "vladimir" and all(o["mode"] == "train" for o in t["transport_options"]), "только поезд")),
    ("Тепло и недорого зимой", ["Хочу к тёплому морю в декабре, недорого"],
     lambda t: (len(t["destination_options"]) >= 2 and len({o["country"] for o in t["destination_options"]}) >= 2,
                "разные страны в вариантах")),
    ("Пустой запрос", ["привет"],
     lambda t: (t["status"] == "need_info", "один уточняющий вопрос")),
    ("Бессмысленный текст", ["asdf qwerty 123"],
     lambda t: (t["status"] == "need_info", "один уточняющий вопрос")),
    ("Новый бюджет", ["Сочи на 5 дней", "бюджет 50000"],
     lambda t: (t["budget"]["limit"] == 50000, "лимит обновлён")),
    ("Отмена важна", ["Москва на 3 дня, важна бесплатная отмена"],
     lambda t: (_hotel(t)["cancellation"] == "free", "бесплатная отмена")),
    ("Уточняющие вопросы", ["Я хочу съездить в Москву. Нас будет 3 взрослых. Бюджет 60 тысяч рублей"],
     lambda t: (t["status"] == "need_info" and not t["days"], "агент спросил даты и город отправления")),
    ("Ответ на уточнение", ["Я хочу съездить в Москву. Нас будет 3 взрослых. Бюджет 60 тысяч рублей", "с 12 по 15 декабря, из Казани"],
     lambda t: (t["params"]["origin"] == "kazan" and t["params"]["nights"] == 3 and len(t["days"]) > 0, "план с датами и городом из ответа")),
    ("Переспрашивает до полной картины", ["хочу в москву", "с 30 октября по 4 ноября"],
     lambda t: (t["status"] == "need_info" and not t["days"] and t["params"]["nights"] == 5, "после неполного ответа — снова вопрос")),
    ("Ответ без «из» и голым числом", ["хочу в москву", "нижний новгород. 60000"],
     lambda t: (t["params"]["destination"] == "moscow" and t["params"]["origin"] == "nizhny"
                and t["params"]["budget_rub"] == 60000 and t["status"] == "need_info", "город отправления и бюджет из ответа")),
    ("Бюджет снят — план пересобран", ["Москва с 30 октября по 4 ноября из Нижнего Новгорода, двое взрослых, бюджет 60 000",
                                       "ну окей бюджет не ограниченный"],
     lambda t: (t["budget"]["limit"] is None and not any(c["code"] == "over_budget" for c in t["connections"]), "лимит снят, нет превышения")),
    ("Бюджет соблюдён", ["Петербург с 5 по 8 декабря из Москвы вдвоём, бюджет 45 000"],
     lambda t: (t["budget"]["total"] <= 45000, "итог не выше лимита")),
    ("Покупка", ["Казань на 3 дня"], None),
    ("После покупки", ["Петербург на 3 дня"], None),
]


def _hotel(t):
    return next(h for h in t["hotel_options"] if h["id"] == t["selected_hotel_id"])


def _transport(t):
    return next(o for o in t["transport_options"] if o["id"] == t["selected_transport_id"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    args = ap.parse_args()
    mode = "auto" if args.llm else "offline"
    prov = provider() if args.llm else "offline"
    label = "офлайн-агент" if prov == "offline" else f"{prov} · {PROVIDERS[prov][0].MODEL}"
    print(f"Агент: {label}")
    c = TestClient(app)
    auth = c.post("/api/auth/register", json={"login": f"eval{int(time.time())}@waylo.test", "password": "evalpass123",
                                              "last_name": "Тест", "first_name": "Замер"}).json()
    H = {"Authorization": f"Bearer {auth['token']}"}
    rows = []
    for name, msgs, check in CASES:
        trip_id, trip, first_rec_ms, clar = None, None, None, 0
        t0 = time.time()
        error = None
        agents: set[str] = set()
        try:
            for m in msgs:
                r = c.post("/api/chat", json={"trip_id": trip_id, "user_id": f"eval_{len(rows)}", "message": m, "mode": mode})
                r.raise_for_status()
                j = r.json()
                trip, trip_id = j["trip"], j["trip"]["id"]
                agents.add(j["chat"][-1].get("agent", "?"))
                if trip["status"] == "need_info":
                    clar += 1
                    if trip["params"]["destination"] and not trip["days"] and name not in ("Уточняющие вопросы", "Ответ на уточнение", "Переспрашивает до полной картины", "Ответ без «из» и голым числом"):
                        r = c.post("/api/chat", json={"trip_id": trip_id, "user_id": f"eval_{len(rows)}",
                                                      "message": "На ваше усмотрение", "mode": mode})
                        r.raise_for_status()
                        j = r.json()
                        trip = j["trip"]
                        agents.add(j["chat"][-1].get("agent", "?"))
                if first_rec_ms is None and (trip["days"] or trip["destination_options"]):
                    first_rec_ms = int((time.time() - t0) * 1000)
            completed = None
            if trip and trip["days"]:
                if name in ("Покупка", "После покупки"):
                    r = c.post(f"/api/trips/{trip_id}/checkout", json={"guests": [{"full_name": f"Иванов Гость {i + 1}", "birth_date": "1990-01-01",
                                                                     "document": "Паспорт РФ •••• 0000"}
                                                                    for i in range(trip["params"]["adults"] + trip["params"]["children"])]}, headers=H)
                    completed = r.status_code == 200
                    if completed and name == "После покупки":
                        completed = c.post(f"/api/trips/{trip_id}/extras", json={"kind": "early_checkin"}, headers=H).status_code == 200
                    trip = r.json().get("trip", trip)
                else:
                    completed = True
            ok, note = (check(trip) if check else (bool(completed), "демо-оформление прошло"))
        except Exception as e:
            ok, note, completed, error = False, f"ошибка: {e}", False, str(e)
        crit = sum(1 for x in (trip or {}).get("connections", []) if x["level"] == "critical")
        rows.append({"name": name, "ok": ok, "note": note, "completed": completed, "clar": clar,
                     "first_ms": first_rec_ms, "crit": crit, "error": error, "fallback": "offline-fallback" in agents})
        print(f"{'✓' if ok else '✗'} {name:32s} {note:40s} уточн.={clar} первая рек.={first_rec_ms} мс крит.={crit}")

    planned = [r for r in rows if r["completed"] is not None]
    passed = sum(r["ok"] for r in rows)
    first = [r["first_ms"] for r in rows if r["first_ms"] is not None]
    summary = {
        "Кейсов": len(rows),
        "Проверки пройдены": f"{passed}/{len(rows)}",
        "Доведено до плана/корзины": f"{sum(1 for r in planned if r['completed'])}/{len(planned)}",
        "Среднее число уточнений": round(sum(r["clar"] for r in rows) / len(rows), 2),
        "Время до первой рекомендации, медиана": f"{sorted(first)[len(first) // 2]} мс" if first else "—",
        "Критичных ошибок состыковок": sum(r["crit"] for r in rows),
        "Ответов из резервного офлайн-агента": sum(r["fallback"] for r in rows),
    }
    print()
    for k, v in summary.items():
        print(f"{k}: {v}")
    out = ROOT / "eval" / ("results.md" if prov == "offline" else f"results_{prov}.md")
    with out.open("w", encoding="utf-8") as f:
        f.write(f"# Замер агента Waylo ({label})\n\n")
        for k, v in summary.items():
            f.write(f"- **{k}:** {v}\n")
        f.write("\n| Кейс | Результат | Проверка | Уточнений | Первая рекомендация | Критичных состыковок |\n|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['name']} | {'✓' if r['ok'] else '✗'} | {r['note']} | {r['clar']} | {r['first_ms'] or '—'} мс | {r['crit']} |\n")
    print(f"\nОтчёт: {out}")


if __name__ == "__main__":
    main()
