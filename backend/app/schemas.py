"""Структуры состояния поездки. Всё, что показывает frontend, лежит здесь."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Тип значения цены или факта: подтверждено внешним API, расчётная оценка или синтетика.
ValueKind = Literal["confirmed", "estimate", "demo"]


class TripParams(BaseModel):
    origin: str = "moscow"
    destination: str | None = None
    start_date: str | None = None  # ISO, дата прибытия
    nights: int | None = None
    adults: int = 2
    children: int = 0
    pets: bool = False
    budget_rub: int | None = None
    interests: list[str] = Field(default_factory=list)
    walking: Literal["normal", "low"] = "normal"
    month: int | None = None
    wishes: list[str] = Field(default_factory=list)  # sea, warm, cheap, short_trip, center
    max_travel_hours: float | None = None
    priority: Literal["balanced", "price", "location", "cancellation"] = "balanced"
    transport_pref: Literal["any", "train", "plane"] = "any"
    assumptions: list[str] = Field(default_factory=list)
    known: list[str] = Field(default_factory=list)  # что пользователь назвал сам, а не взято по умолчанию
    clarified: bool = False  # уточняющие вопросы уже задавали — второй раз не спрашиваем, берём допущения

    @property
    def travelers(self) -> int:
        return self.adults + self.children


class Explanation(BaseModel):
    why: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class DestinationOption(BaseModel):
    city_id: str
    name: str
    country: str
    travel_hours: float
    travel_mode: str
    est_total_rub: int
    climate: dict | None = None  # {tmax, tmin, rainy_days, source, kind}
    explanation: Explanation
    score: float


class Leg(BaseModel):
    from_name: str
    to_name: str
    depart: str  # ISO datetime
    arrive: str
    duration_min: int
    carrier: str
    number: str | None = None


class TransportOption(BaseModel):
    id: str
    mode: Literal["train", "plane"]
    title: str
    outbound: Leg
    inbound: Leg
    price_per_person: int
    price_total: int
    kind: ValueKind
    source: str
    pets_allowed: bool
    transfers: int = 0
    door_to_door_hours: float
    explanation: Explanation = Field(default_factory=Explanation)
    score: float = 0


class Hotel(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    district: str
    stars: int
    rating: float
    price_per_night: int
    nights: int
    total: int
    cancellation: Literal["free", "partial", "non_refundable"]
    cancellation_text: str
    meals: Literal["none", "breakfast", "half_board"]
    pets_allowed: bool
    kids_friendly: bool
    checkin: str = "14:00"
    checkout: str = "12:00"
    early_checkin_price: int
    distance_center_km: float
    kind: ValueKind = "demo"
    source: str = "Демо-отель Waylo (вымышленный, цены синтетические)"
    website: str | None = None
    osm_url: str | None = None
    facts: dict[str, ValueKind] = Field(default_factory=dict)  # тип данных по полям: name, price, cancellation…
    explanation: Explanation = Field(default_factory=Explanation)
    score: float = 0


class Place(BaseModel):
    id: str
    name: str
    cats: list[str]
    lat: float
    lon: float
    indoor: bool
    visit_min: int
    ticket_rub: int
    closed_weekdays: list[int] = Field(default_factory=list)  # 0 = понедельник
    hours_status: Literal["unknown", "unverified", "confirmed"] = "unverified"
    description: str = ""
    source: str = "Демо-набор Waylo (координаты приблизительные)"


class Stop(BaseModel):
    place: Place
    arrive: str  # HH:MM
    depart: str
    leg_mode: Literal["start", "walk", "transit"]
    leg_km: float
    leg_min: int
    leg_cost_rub: int = 0
    note: str | None = None


class DayWeather(BaseModel):
    tmax: float | None = None
    tmin: float | None = None
    precip_mm: float | None = None
    label: str
    kind: ValueKind
    source: str


class DayPlan(BaseModel):
    day: int
    date: str
    title: str
    place_ids: list[str]
    stops: list[Stop] = Field(default_factory=list)
    less_walking: bool = False
    indoor_only: bool = False
    start_time: str = "10:00"
    end_limit: str = "20:00"
    walk_km: float = 0
    transit_min: int = 0
    cost_rub: int = 0
    weather: DayWeather | None = None
    notes: list[str] = Field(default_factory=list)


class BudgetItem(BaseModel):
    id: str
    category: Literal["transport", "hotel", "transfer", "food", "tickets", "local_transport", "extras"]
    title: str
    amount: int
    kind: ValueKind
    source: str
    note: str | None = None


class Budget(BaseModel):
    items: list[BudgetItem] = Field(default_factory=list)
    total: int = 0
    limit: int | None = None
    over_by: int = 0
    savings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ConnectionCheck(BaseModel):
    level: Literal["ok", "warning", "critical"]
    code: str
    text: str
    fix: str | None = None


class ChangeEntry(BaseModel):
    at: str
    summary: str
    details: list[str] = Field(default_factory=list)


class ToolEvent(BaseModel):
    tool: str
    summary: str
    ok: bool = True


class ExtraOffer(BaseModel):
    kind: Literal["early_checkin", "transfer"]
    title: str
    note: str
    amount: int
    paid: bool = False


class Order(BaseModel):
    order_id: str
    created_at: str
    total: int
    lines: list[str]
    status: str = "DEMO — оплата не производилась, бронирований не создано"
    payment: str | None = None  # «Visa •••• 4242» — номер карты на сервер не передаётся
    post_purchase: list[str] = Field(default_factory=list)
    offers: list[ExtraOffer] = Field(default_factory=list)



class Trip(BaseModel):
    id: str
    user_id: str = "anonymous"
    status: Literal["need_info", "choose_destination", "planning", "ready", "purchased"] = "need_info"
    params: TripParams = Field(default_factory=TripParams)
    destination_options: list[DestinationOption] = Field(default_factory=list)
    transport_options: list[TransportOption] = Field(default_factory=list)
    hotel_options: list[Hotel] = Field(default_factory=list)
    selected_transport_id: str | None = None
    selected_hotel_id: str | None = None
    places: list[Place] = Field(default_factory=list)
    days: list[DayPlan] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    connections: list[ConnectionCheck] = Field(default_factory=list)
    changes: list[ChangeEntry] = Field(default_factory=list)
    tool_log: list[ToolEvent] = Field(default_factory=list)
    order: Order | None = None
    data_notes: list[str] = Field(default_factory=list)

    def transport(self) -> TransportOption | None:
        return next((t for t in self.transport_options if t.id == self.selected_transport_id), None)

    def hotel(self) -> Hotel | None:
        return next((h for h in self.hotel_options if h.id == self.selected_hotel_id), None)

    def place(self, pid: str) -> Place | None:
        return next((p for p in self.places if p.id == pid), None)
