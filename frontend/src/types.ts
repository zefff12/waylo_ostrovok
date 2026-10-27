export type Kind = "confirmed" | "estimate" | "demo";

export interface Explanation { why: string[]; tradeoffs: string[]; risks: string[] }

export interface TripParams {
  origin: string; destination: string | null; start_date: string | null; nights: number | null;
  adults: number; children: number; pets: boolean; budget_rub: number | null; interests: string[];
  walking: "normal" | "low"; month: number | null; wishes: string[]; assumptions: string[];
}

export interface DestinationOption {
  city_id: string; name: string; country: string; travel_hours: number; travel_mode: string;
  est_total_rub: number; climate: { tmax: number | null; tmin: number | null; rainy_days: number; source: string } | null;
  explanation: Explanation; score: number;
}

export interface Leg { from_name: string; to_name: string; depart: string; arrive: string; duration_min: number; carrier: string; number?: string | null }

export interface TransportOption {
  id: string; mode: "train" | "plane"; title: string; outbound: Leg; inbound: Leg;
  price_per_person: number; price_total: number; kind: Kind; source: string; pets_allowed: boolean;
  transfers: number; door_to_door_hours: number; explanation: Explanation; score: number;
}

export interface Hotel {
  id: string; name: string; lat: number; lon: number; district: string; stars: number; rating: number;
  price_per_night: number; nights: number; total: number; cancellation: "free" | "partial" | "non_refundable";
  cancellation_text: string; meals: "none" | "breakfast" | "half_board"; pets_allowed: boolean; kids_friendly: boolean;
  checkin: string; checkout: string; early_checkin_price: number; distance_center_km: number; kind: Kind; source: string;
  website: string | null; osm_url: string | null; facts: Record<string, Kind>;
  explanation: Explanation; score: number;
}

export interface Place {
  id: string; name: string; cats: string[]; lat: number; lon: number; indoor: boolean; visit_min: number;
  ticket_rub: number; closed_weekdays: number[]; hours_status: string; description: string; source: string;
}

export interface Stop { place: Place; arrive: string; depart: string; leg_mode: "start" | "walk" | "transit"; leg_km: number; leg_min: number; leg_cost_rub: number; note: string | null }

export interface DayPlan {
  day: number; date: string; title: string; place_ids: string[]; stops: Stop[]; less_walking: boolean; indoor_only: boolean;
  start_time: string; end_limit: string; walk_km: number; transit_min: number; cost_rub: number;
  weather: { label: string; kind: Kind; source: string; precip_mm: number | null } | null; notes: string[];
}

export interface BudgetItem { id: string; category: string; title: string; amount: number; kind: Kind; source: string; note: string | null }
export interface Budget { items: BudgetItem[]; total: number; limit: number | null; over_by: number; savings: string[]; assumptions: string[] }
export interface ConnectionCheck { level: "ok" | "warning" | "critical"; code: string; text: string; fix: string | null }
export interface ChangeEntry { at: string; summary: string; details: string[] }
export interface ToolEvent { tool: string; summary: string; ok: boolean }
export interface ExtraOffer { kind: "early_checkin" | "transfer"; title: string; note: string; amount: number; paid: boolean }
export interface Order {
  order_id: string; created_at: string; total: number; lines: string[]; status: string; payment: string | null;
  post_purchase: string[]; offers: ExtraOffer[];
}

export interface Trip {
  id: string; status: "need_info" | "choose_destination" | "planning" | "ready" | "purchased";
  params: TripParams; destination_options: DestinationOption[]; transport_options: TransportOption[];
  hotel_options: Hotel[]; selected_transport_id: string | null; selected_hotel_id: string | null;
  places: Place[]; days: DayPlan[]; budget: Budget; connections: ConnectionCheck[]; changes: ChangeEntry[];
  tool_log: ToolEvent[]; order: Order | null;
}

export interface ChatMsg { role: "user" | "assistant"; text: string; agent?: string; at: string }

export interface Health {
  ok: boolean; agent: "claude" | "gigachat" | "offline"; model: string | null; provider_label: string | null;
  integrations: Record<string, string>; cities: { id: string; name: string; country: string; tags: string[] }[]; yandex_js_key: string | null; home_youtube_id: string | null;
}
