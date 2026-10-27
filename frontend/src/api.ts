import type { ChatMsg, Health, Trip } from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = `${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* тело не JSON */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export type TripResponse = { trip: Trip; chat: ChatMsg[] };
export type ChatResponse = TripResponse & { reply: string; agent: string; elapsed_ms: number };

let healthOnceP: Promise<Health> | null = null;
/** /api/health один раз за сессию — для компонентов, которым нужны настройки (ключ карты). */
export const healthOnce = () => (healthOnceP ??= api.health());

export const api = {
  health: () => call<Health>("/api/health"),
  chat: (trip_id: string | null, user_id: string, message: string, mode: string) =>
    post<ChatResponse>("/api/chat", { trip_id, user_id, message, mode }),
  trip: (id: string) => call<TripResponse>(`/api/trips/${id}`),
  latest: (user: string) => call<{ trip_id: string | null; profile: Record<string, unknown> }>(`/api/users/${user}/latest`),
  forget: (user: string) => call<{ ok: boolean }>(`/api/users/${user}/profile`, { method: "DELETE" }),
  destination: (id: string, city: string) => post<TripResponse>(`/api/trips/${id}/destination`, { option_id: city }),
  transport: (id: string, opt: string) => post<TripResponse>(`/api/trips/${id}/transport`, { option_id: opt }),
  hotel: (id: string, opt: string) => post<TripResponse>(`/api/trips/${id}/hotel`, { option_id: opt }),
  day: (id: string, day: number, action: string, extra: { category?: string; place_id?: string } = {}) =>
    post<TripResponse>(`/api/trips/${id}/days/${day}`, { action, ...extra }),
  checkout: (id: string, guests: unknown[], card?: string) => post<TripResponse>(`/api/trips/${id}/checkout`, { guests, card }),
  restore: (trip: Trip, chat: ChatMsg[]) => post<TripResponse>("/api/trips/restore", { trip, chat }),
  extras: (id: string, kind: string, card?: string) => post<TripResponse>(`/api/trips/${id}/extras`, { kind, card }),
};

/** claude-haiku-5-5 → «Claude Haiku 5.5» */
export const modelLabel = (id: string) =>
  id.replace(/^claude-/, "Claude ").replace(/-(\d+)-(\d+)$/, " $1.$2").replace(/-(\d+)$/, " $1")
    .replace(/\b([a-z])/g, (c) => c.toUpperCase());

export const rub =(n: number) => `${Math.round(n).toLocaleString("ru-RU")} ₽`;

export const KIND_LABEL: Record<string, string> = { confirmed: "реальные данные", estimate: "оценка", demo: "демо" };

export const CAT_LABEL: Record<string, string> = {
  museum: "музей", architecture: "архитектура", view: "вид", park: "парк", cafe: "кафе", history: "история",
  hidden: "необычное", shopping: "шопинг", theatre: "театр", beach: "пляж",
};

export function fmtDT(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function fmtDate(iso: string) {
  return new Date(iso + "T00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "long", weekday: "short" });
}
