"""Геометрия и время: расстояния, пешие переходы, поездки по городу."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

WALK_KMH = 4.5
DETOUR = 1.3  # улицы не по прямой


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def walk_minutes(dist_km: float) -> int:
    return max(1, round(dist_km * DETOUR / WALK_KMH * 60))


def transit_minutes(dist_km: float) -> int:
    """Метро/такси по городу: посадка + ~20 км/ч в среднем."""
    return round(10 + dist_km * DETOUR / 20 * 60)


def taxi_rub(dist_km: float) -> int:
    return int(round((250 + dist_km * DETOUR * 32) / 50) * 50)


def taxi_minutes(dist_km: float) -> int:
    return round(8 + dist_km * DETOUR / 30 * 60)


def hm(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def fmt_hm(minutes: int) -> str:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def add_minutes(dt: datetime, minutes: int) -> datetime:
    return dt + timedelta(minutes=minutes)
