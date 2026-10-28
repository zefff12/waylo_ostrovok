"""Агент на GigaChat (Сбер) с вызовом функций. Те же инструменты, что у Claude (agent_tools).

Особенности API GigaChat:
- авторизация: ключ авторизации (Base64 от Client ID:Client Secret) → POST /oauth → токен на 30 минут;
- функция за ход одна: модель возвращает message.function_call {name, arguments}, finish_reason = "function_call";
- результат отправляется сообщением role="function" с JSON-объектом, обёрнутым в строку;
- TLS-сертификат API выдан Russian Trusted Root CA (Минцифры) — путь к нему задаётся GIGACHAT_CA_BUNDLE.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path

import httpx

from . import planner
from .agent_tools import SYSTEM, TOOLS, begin_turn, clarification_reply, execute, fallback_reply
from .schemas import Trip

log = logging.getLogger("waylo.gigachat")

MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Max")
BASE_URL = os.getenv("GIGACHAT_BASE_URL", "https://api.giga.chat/v1").rstrip("/")
AUTH_URL = os.getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
MAX_STEPS = 12
BUNDLED_CA = Path(__file__).resolve().parent.parent.parent / "certs" / "russian_trusted_root_ca.cer"

_token: dict = {"value": None, "expires_at": 0.0}
_lock = threading.Lock()


class GigaChatError(Exception):
    """Любая ошибка обращения к GigaChat: сеть, TLS, авторизация, ответ API."""


def available() -> bool:
    return bool(os.getenv("GIGACHAT_CREDENTIALS"))


def _verify() -> str | bool:
    bundle = os.getenv("GIGACHAT_CA_BUNDLE")
    if bundle:
        return bundle
    if BUNDLED_CA.is_file():  # сертификат лежит в репозитории — на сервере путь задавать не нужно
        return str(BUNDLED_CA)
    if os.getenv("GIGACHAT_VERIFY_SSL", "true").lower() in ("0", "false", "no"):
        return False  # только для локальной разработки
    return True


def _client() -> httpx.Client:
    return httpx.Client(verify=_verify(), timeout=httpx.Timeout(60.0, connect=10.0))


def _get_token(client: httpx.Client) -> str:
    with _lock:
        if _token["value"] and time.time() < _token["expires_at"] - 60:
            return _token["value"]
        try:
            r = client.post(AUTH_URL, data={"scope": SCOPE}, headers={
                "Authorization": f"Basic {os.environ['GIGACHAT_CREDENTIALS']}",
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            })
        except httpx.ConnectError as e:
            raise GigaChatError(_tls_hint(e)) from e
        except httpx.HTTPError as e:
            raise GigaChatError(f"сеть: {type(e).__name__}") from e
        if r.status_code != 200:
            raise GigaChatError(f"авторизация {r.status_code}: проверьте GIGACHAT_CREDENTIALS и GIGACHAT_SCOPE ({r.text[:120]})")
        body = r.json()
        _token["value"] = body["access_token"]
        _token["expires_at"] = body.get("expires_at", 0) / 1000 or time.time() + 25 * 60  # API отдаёт миллисекунды
        return _token["value"]


def _tls_hint(e: Exception) -> str:
    if "CERTIFICATE_VERIFY_FAILED" in str(e) or "certificate" in str(e).lower():
        return ("TLS: сертификат GigaChat выдан Russian Trusted Root CA. Скачайте корневой сертификат Минцифры "
                "и укажите путь в GIGACHAT_CA_BUNDLE (см. README)")
    return f"сеть: {type(e).__name__}"


def _functions() -> list[dict]:
    """Схемы Anthropic → функции GigaChat: input_schema → parameters, без additionalProperties."""
    def clean(schema: dict) -> dict:
        out = {k: v for k, v in schema.items() if k != "additionalProperties"}
        if "properties" in out:
            out["properties"] = {k: clean(v) for k, v in out["properties"].items()}
        if "items" in out and isinstance(out["items"], dict):
            out["items"] = clean(out["items"])
        return out

    return [{"name": t["name"], "description": t["description"], "parameters": clean(t["input_schema"])} for t in TOOLS]


FUNCTIONS = _functions()


def _chat(client: httpx.Client, messages: list[dict]) -> dict:
    token = _get_token(client)
    try:
        r = client.post(f"{BASE_URL}/chat/completions", headers={"Authorization": f"Bearer {token}"}, json={
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM}, *messages],
            "functions": FUNCTIONS,
            "function_call": "auto",
        })
    except httpx.ConnectError as e:
        raise GigaChatError(_tls_hint(e)) from e
    except httpx.HTTPError as e:
        raise GigaChatError(f"сеть: {type(e).__name__}") from e
    if r.status_code == 401:
        _token["value"] = None
        raise GigaChatError("токен отклонён (401) — повторите запрос")
    if r.status_code != 200:
        raise GigaChatError(f"API {r.status_code}: {r.text[:200]}")
    return r.json()


def _json_result(out: dict, limit: int = 20000) -> str:
    """GigaChat требует валидный JSON в строке — длинный результат не обрезаем посередине, а оборачиваем."""
    s = json.dumps(out, ensure_ascii=False, default=str)
    if len(s) <= limit:
        return s
    return json.dumps({"note": "результат сокращён", "data": s[:limit - 200]}, ensure_ascii=False)


def handle(trip: Trip, text: str, messages: list, profile: dict | None = None) -> str:
    """Один ход диалога. messages — история в формате GigaChat (без system), только добавляем."""
    content = text
    if profile and not messages:
        content += f"\n\n[Память о прошлых поездках пользователя: {json.dumps(profile, ensure_ascii=False)}. Учитывай, если уместно, и скажи об этом.]"
    if trip.days:
        content += f"\n\n[Состояние: поездка уже собрана, город {trip.params.destination}, {len(trip.days)} дн. Меняй точечно.]"
    early, note = begin_turn(trip, text)
    if early:  # уточнение идёт без модели: вопросы задаёт планировщик
        messages += [{"role": "user", "content": content}, {"role": "assistant", "content": early}]
        return early
    if note:
        content += f"\n\n[{note}]"
    messages.append({"role": "user", "content": content})
    with _client() as client:
        for _ in range(MAX_STEPS):
            data = _chat(client, messages)
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            finish = choice.get("finish_reason")
            call = msg.get("function_call")
            if finish == "blacklist":
                messages.append({"role": "assistant", "content": msg.get("content") or ""})
                return "GigaChat отказался отвечать на этот запрос. Давайте вернёмся к планированию поездки."
            if not call:
                answer = (msg.get("content") or "").strip()
                messages.append({"role": "assistant", "content": answer})
                return answer or "Готово — смотрите план справа."
            # ответ с вызовом функции возвращаем в историю как есть, вместе с functions_state_id
            assistant = {"role": "assistant", "content": msg.get("content") or "", "function_call": call}
            if msg.get("functions_state_id"):
                assistant["functions_state_id"] = msg["functions_state_id"]
            messages.append(assistant)
            args = call.get("arguments") or {}
            if isinstance(args, str):  # в документации тип описан двояко: объект или JSON-строка
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
            try:
                out = execute(trip, call["name"], args)
            except Exception as e:  # модель должна узнать об ошибке и исправиться, а не получить тишину
                log.exception("tool %s failed", call.get("name"))
                planner.log_tool(trip, call.get("name", "?"), f"ошибка: {e}", ok=False)
                out = {"error": f"Ошибка инструмента: {e}"}
            messages.append({"role": "function", "name": call["name"], "content": _json_result(out)})
            if "need_clarification" in out:  # данных не хватает — заканчиваем ход вопросом, а не новыми вызовами
                messages.append({"role": "assistant", "content": out["text"]})
                return out["text"]
    return fallback_reply(trip)
