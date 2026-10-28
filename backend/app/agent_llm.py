"""Агент на Claude (по умолчанию Haiku 5.5, модель задаётся WAYLO_MODEL) с tool calling.

LLM понимает запрос, решает, какие инструменты вызвать, и объясняет результат.
Бизнес-логика и расчёты — в planner.py; модель получает их результаты как JSON.
"""
from __future__ import annotations

import json
import logging
import os

import anthropic

from . import planner
from .agent_tools import SYSTEM, TOOLS, begin_turn, clarification_reply, execute, fallback_reply
from .schemas import Trip

log = logging.getLogger("waylo.agent")

MODEL = os.getenv("WAYLO_MODEL", "claude-haiku-5-5")
# Server-side fallback при отказе есть у Opus 5.5 / Sonnet 5.5 / Fable 5.1; у Haiku 5.5 его нет —
# параметр fallbacks там не передаём, отказ обрабатываем в коде.
SUPPORTS_FALLBACK = not MODEL.startswith("claude-haiku")
EFFORT = os.getenv("WAYLO_EFFORT", "medium")
MAX_STEPS = 12


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def handle(trip: Trip, text: str, messages: list, profile: dict | None = None) -> str:
    """Один ход диалога. messages — история (только добавляем, не редактируем)."""
    client = anthropic.Anthropic()
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
    for _ in range(MAX_STEPS):
        params = dict(model=MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
                      output_config={"effort": EFFORT})
        if SUPPORTS_FALLBACK:
            response = client.beta.messages.create(**params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        else:
            response = client.messages.create(**params)
        messages.append({"role": "assistant", "content": response.to_dict()["content"]})
        if response.stop_reason == "refusal":
            return "Не могу помочь с этим запросом. Давайте вернёмся к планированию поездки."
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            return "\n".join(b.text for b in response.content if b.type == "text").strip() or "Готово — смотрите план справа."
        results = []
        for tu in tool_uses:
            try:
                out = execute(trip, tu.name, dict(tu.input))
                results.append({"type": "tool_result", "tool_use_id": tu.id,
                                "content": json.dumps(out, ensure_ascii=False, default=str)[:20000],
                                **({"is_error": True} if "error" in out else {})})
            except Exception as e:  # инструмент упал — модель должна узнать об этом, а не получить тишину
                log.exception("tool %s failed", tu.name)
                planner.log_tool(trip, tu.name, f"ошибка: {e}", ok=False)
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": f"Ошибка инструмента: {e}", "is_error": True})
        messages.append({"role": "user", "content": results})
        if (q := clarification_reply(trip)) and any("need_clarification" in r["content"] for r in results):
            messages.append({"role": "assistant", "content": q})
            return q
    return fallback_reply(trip)
