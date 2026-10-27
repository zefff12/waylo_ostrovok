"""Разбор русского текста правилами — для офлайн-агента (без LLM) и как подсказка для Claude."""
from __future__ import annotations

import re
from datetime import date

from .data import CITIES, find_city

NUM_WORDS = {
    "один": 1, "одну": 1, "одного": 1, "два": 2, "две": 2, "двух": 2, "три": 3, "трёх": 3, "трех": 3, "четыре": 4,
    "четырёх": 4, "пять": 5, "пяти": 5, "шесть": 6, "шести": 6, "семь": 7, "семи": 7, "восемь": 8, "десять": 10,
    "двое": 2, "трое": 3, "четверо": 4, "пятеро": 5, "шестеро": 6, "одним": 1, "двумя": 2, "тремя": 3,
}
MONTH_STEMS = ["январ", "феврал", "март", "апрел", "ма[йяе]", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]
INTERESTS = {
    "architecture": r"архитектур|красив\w* улиц|здани|модерн",
    "museum": r"музе|галере|выставк|искусств",
    "cafe": r"кафе|кофе|гастро|ед[аыу]\b|ресторан|вкусн|кухн",
    "park": r"парк|сад\b|природ|зелен",
    "view": r"вид[ыа]?\b|панорам|смотров|фото|атмосферн",
    "history": r"истори|крепост|кремл",
    "hidden": r"необычн|малоизвест|локальн|нетурист|секретн|атмосферн",
    "shopping": r"шопинг|магазин|покупк",
    "theatre": r"театр|балет|опер",
    "beach": r"пляж|купат",
}
ORDINALS = {"перв": 1, "втор": 2, "трет": 3, "четв": 4, "пят": 5, "шест": 6, "седьм": 7}


def _num(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    return NUM_WORDS.get(tok)


def parse_request(text: str) -> dict:
    """Параметры поездки из свободного текста. Возвращает только то, что удалось найти."""
    low = text.lower().replace("ё", "е")
    out: dict = {}

    m_from = re.search(r"\bиз\s+([а-я\-]+(?:\s+[а-я]+)?)", low)
    if m_from and (c := find_city(m_from.group(1))):
        out["origin"] = c.id
        low_wo_origin = low.replace(m_from.group(0), " ")
    else:
        low_wo_origin = low
    if c := find_city(low_wo_origin):
        out["destination"] = c.id

    # длительность
    if m := re.search(r"(\d+|[а-я]+)[\s-]*(дн|дня|дней|день|ноч)", low):
        n = _num(m.group(1))
        if n:
            out["nights"] = n if m.group(2).startswith("ноч") else max(1, n - 1)
    if m := re.search(r"(двух|трех|четырех|пяти|шести|семи)дневн", low):
        out["nights"] = {"двух": 1, "трех": 2, "четырех": 3, "пяти": 4, "шести": 5, "семи": 6}[m.group(1)]
    if re.search(r"на неделю|недельн", low):
        out["nights"] = 6
    if re.search(r"на выходные|выходных", low):
        out["nights"] = 2

    # месяц и даты
    for i, stem in enumerate(MONTH_STEMS):
        if re.search(rf"\b{stem}\w*", low) and not (i == 4 and not re.search(r"\bма[йяе]\b|\bмая\b", low)):
            out["month"] = i + 1
            if m := re.search(rf"(?:с\s+)?(\d{{1,2}})(?:\s*(?:[-–]|по)\s*(\d{{1,2}}))?\s+{stem}", low):
                today = date.today()
                year = today.year + ((i + 1) < today.month)
                try:
                    s = date(year, i + 1, int(m.group(1)))
                    out["start_date"] = s.isoformat()
                    if m.group(2):
                        out["nights"] = max(1, int(m.group(2)) - int(m.group(1)))
                except ValueError:
                    pass
            break

    # бюджет
    m = re.search(r"(\d[\d\s]*[.,]?\d*)\s*(тыс\w*|т\.р|к\b|000|руб\w*|₽|р\b)", low)
    if m and re.search(r"бюджет|до\s+\d|за\s+\d|руб|₽|тыс|\d\s*к\b", low):
        raw = m.group(1).replace(" ", "").replace(",", ".")
        try:
            val = float(raw)
            if m.group(2).startswith(("тыс", "т.р", "к")):
                val *= 1000
            elif m.group(2) == "000":
                val = val * 1000 if val < 1000 else val
            if 3000 <= val <= 5_000_000:
                out["budget_rub"] = int(val)
        except ValueError:
            pass

    # кто едет
    adults = None
    if re.search(r"на двоих|вдво[её]м|с девушкой|с парнем|с женой|с мужем|с подругой|с другом|\bпар[аойу]\b", low):
        adults = 2
    if re.search(r"на троих|втро[её]м", low):
        adults = 3
    if re.search(r"(еду|поеду|поехать|буду) (один|одна)\b|в одиночку|\bсоло\b", low):
        adults = 1
    if m := re.search(r"(\d+|[а-я]+)\s+(человек|взросл)", low):
        if n := _num(m.group(1)):
            adults = n
    if re.search(r"с реб[её]нком|с сыном|с дочк|с дочерью|с малыш", low):
        out["children"] = 1
        adults = adults or 2
    if m := re.search(r"с (\d+|двумя|тремя) детьми|с детьми", low):
        out["children"] = {"двумя": 2, "тремя": 3}.get(m.group(1) or "", int(m.group(1)) if (m.group(1) or "").isdigit() else 2)
        adults = adults or 2
    if m := re.search(r"(\d+|[а-я]+)\s+(реб[её]н\w*|дет[еи]й)\b", low):  # «1 ребёнок», «двое детей»
        if (n := _num(m.group(1))) is not None:
            out["children"] = n
            adults = adults or 2
    if re.search(r"без детей|детей нет|дет(ей|и) не будет", low):
        out["children"] = 0
    if adults:
        out["adults"] = adults
    if re.search(r"с собак|с псом|с котом|с кошкой|с питомц|с животн|собака", low):
        out["pets"] = True

    out["interests"] = [k for k, rx in INTERESTS.items() if re.search(rx, low)]
    wishes = []
    if re.search(r"мор[еяю]|пляж|купат", low):
        wishes.append("sea")
    if re.search(r"тепл|жар|солнц|загар", low):
        wishes.append("warm")
    if re.search(r"недорог|дешев|бюджетн|эконом", low):
        wishes.append("cheap")
    if re.search(r"центр|не проводить .*транспорт|рядом с|недалеко от", low):
        wishes.append("center")
    if re.search(r"музе|культур|истори", low):
        wishes.append("culture")
    if "beach" in out["interests"]:
        wishes.append("beach")
    out["wishes"] = wishes
    if re.search(r"без долгих перел|недолго лететь|недалеко лететь|без пересадок|короткий перел", low):
        out["max_travel_hours"] = 4.5
    if re.search(r"не (хотим|хочу|люблю)?\s*много ходить|меньше ходить|без долгих прогулок|мало ходить", low):
        out["walking"] = "low"
    if re.search(r"поездом|на поезде|\bпоезда?\b", low):
        out["transport_pref"] = "train"
    elif re.search(r"самол[её]т|лететь|полет", low) or (
            re.search(r"перел[её]т", low) and not re.search(r"без\s+\w*\s*перел", low)):
        out["transport_pref"] = "plane"
    if re.search(r"отмен", low):
        out["priority"] = "cancellation"
    return out


def is_vague(text: str, parsed: dict) -> bool:
    low = text.lower()
    return not parsed.get("destination") and bool(
        parsed.get("wishes") or re.search(r"куда[- ]нибудь|не знаю куда|куда поехать|посоветуй|предложи|варианты", low))


def day_ref(text: str) -> int | None:
    low = text.lower()
    if m := re.search(r"(\d)[\s-]*(?:й|ой|ий)?\s*д(ень|ня)", low):
        return int(m.group(1))
    for stem, n in ORDINALS.items():
        if re.search(rf"\b(во?|на)?\s*{stem}\w*\s+д(ень|ня|не)", low):
            return n
    if re.search(r"сегодня|в первый день", low):
        return 1
    if re.search(r"завтра", low):
        return 2
    if re.search(r"последн\w* д", low):
        return -1
    return None


def parse_command(text: str) -> list[tuple[str, dict]]:
    """Команды изменения готового плана. Порядок важен: сначала глобальные, потом по дням."""
    low = text.lower().replace("ё", "е")
    cmds: list[tuple[str, dict]] = []
    day = day_ref(text)
    if m := re.search(r"на (\d+|один|два|три|четыре|пять|неделю) (дн\w*|день) (позже|раньше)|(позже|раньше) на (\d+|один|два|три|четыре|пять) (дн\w*|день)", low):
        n = _num(m.group(1) or m.group(5)) or (7 if "недел" in (m.group(1) or "") else 1)
        sign = 1 if (m.group(3) or m.group(4)) == "позже" else -1
        cmds.append(("shift_dates", {"days": sign * n}))
    elif re.search(r"на день позже|днем позже", low):
        cmds.append(("shift_dates", {"days": 1}))
    if m := re.search(r"бюджет\w*\s*(?:до|в|—|-|:)?\s*(\d[\d\s]*)\s*(тыс\w*|к\b)?", low):
        val = int(m.group(1).replace(" ", ""))
        if m.group(2):
            val *= 1000
        if val >= 3000:
            cmds.append(("set_constraints", {"budget_rub": val}))
    if re.search(r"дешевл|сэконом|подешевле|уложи\w* в бюджет|бюджет меньше|слишком дорого", low) and "отел" not in low:
        cmds.append(("make_cheaper", {}))
    if re.search(r"с нами (едет|поедет)|берем с собой|с собак|собака|с котом|с питомц", low) and not re.search(r"без собак", low):
        cmds.append(("set_constraints", {"pets": True}))
    if re.search(r"без собак|без питомц", low):
        cmds.append(("set_constraints", {"pets": False}))
    if re.search(r"с реб[её]нком|с детьми", low):
        cmds.append(("set_constraints", {"children": 1}))
    if re.search(r"отмен\w* важн|важн\w* отмен|бесплатн\w* отмен", low):
        cmds.append(("set_constraints", {"priority": "cancellation"}))
    if re.search(r"(поменя|смени|друг)\w* отел|отель (ближе|подешевле|дешевле|получше)", low):
        cmds.append(("change_hotel", {"mode": "cheaper" if re.search(r"дешев", low) else "closer" if "ближе" in low else "next"}))
    if re.search(r"на поезд|поездом|хочу поезд", low):
        cmds.append(("switch_transport", {"mode": "train"}))
    elif re.search(r"на самол[её]т|самол[её]том|лучше лететь|перел[её]т", low):
        cmds.append(("switch_transport", {"mode": "plane"}))
    d = day or 1
    if re.search(r"дожд|ливень|непогод|под крыш", low):
        cmds.append(("modify_day", {"day": day or 1, "action": "rain"}))
    if re.search(r"устал|меньше ход|не хоч\w* (много )?ходить|не (хотим|хочу) много ходить|ноги болят|медленнее", low):
        cmds.append(("modify_day", {"day": d, "action": "less_walking"}))
    if re.search(r"(замени|вместо|поменяй)\w*.*(на|в) кафе|кафе вместо", low):
        cmds.append(("modify_day", {"day": day or 2, "action": "replace_with_cafe"}))
    elif m := re.search(r"добав\w*\s+(еще\s+|ещё\s+)?(музей|кафе|парк|вид|смотров|архитектур|что-то необычн)", low):
        cat = {"музей": "museum", "кафе": "cafe", "парк": "park", "вид": "view", "смотров": "view",
               "архитектур": "architecture", "что-то необычн": "hidden"}[m.group(2)]
        cmds.append(("modify_day", {"day": day or 1, "action": "add_category", "category": cat}))
    if re.search(r"перестро\w* маршрут|перестрой", low) and not cmds:
        cmds.append(("rebuild", {}))
    if re.search(r"оформ|купить|покупк|брониру|в корзину", low):
        cmds.append(("checkout_hint", {}))
    return cmds


def city_name(cid: str | None) -> str:
    return CITIES[cid].name if cid and cid in CITIES else "?"
