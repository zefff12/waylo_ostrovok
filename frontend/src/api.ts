import type { ChatMsg, Health, Ticket, Trip } from "./types";

// Ход агента с несколькими вызовами LLM укладывается в минуту-две; дольше — считаем, что запрос потерян,
// чтобы интерфейс не висел в «агент думает» (например, после ухода во вкладку и возврата).
const TIMEOUT_MS = 150_000;

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, signal: AbortSignal.timeout(TIMEOUT_MS), ...init });
  } catch (e) {
    const name = (e as Error).name;
    throw new Error(name === "TimeoutError" || name === "AbortError"
      ? "Агент не ответил вовремя. План сохранён — попробуйте отправить сообщение ещё раз."
      : "Нет связи с сервером Waylo. Проверьте интернет и попробуйте ещё раз.");
  }
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
  support: (b: { user_id: string; topic: string; text: string; contact?: string; trip_id?: string | null }) => post<Ticket>("/api/support", b),
  supportSync: (user_id: string, tickets: Ticket[]) => post<{ tickets: Ticket[] }>("/api/support/sync", { user_id, tickets }),
  supportMessage: (id: string, user_id: string, text: string) => post<Ticket>(`/api/support/${id}/messages`, { user_id, text }),
  supportAdmin: (token: string) => call<{ tickets: Ticket[] }>("/api/support/admin", { headers: { "X-Admin-Token": token } }),
  supportReply: (token: string, id: string, text: string) => call<Ticket>(`/api/support/admin/${id}/reply`,
    { method: "POST", body: JSON.stringify({ text }), headers: { "Content-Type": "application/json", "X-Admin-Token": token } }),
  supportClose: (token: string, id: string) => call<Ticket>(`/api/support/admin/${id}/close`,
    { method: "POST", headers: { "X-Admin-Token": token } }),
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
