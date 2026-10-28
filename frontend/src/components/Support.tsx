import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import type { Ticket } from "../types";
import { GlassIcon, Icon } from "./Icons";

export const TOPIC_LABEL: Record<Ticket["topic"], string> = {
  trip: "Вопрос по поездке", payment: "Оплата и заказ", bug: "Ошибка на сайте", other: "Другое",
};
export const STATUS_LABEL: Record<Ticket["status"], string> = { open: "Ждёт ответа", answered: "Есть ответ", closed: "Закрыто" };

const STORE = "waylo_support_v1";  // копия своих обращений: сервер на бесплатном Render может её потерять

function loadLocal(): Ticket[] {
  try { return JSON.parse(localStorage.getItem(STORE) ?? "[]"); } catch { return []; }
}
function saveLocal(ts: Ticket[]) {
  try { localStorage.setItem(STORE, JSON.stringify(ts.slice(0, 50))); } catch { /* приватный режим */ }
}

const fmt = (iso: string) => new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Окно поддержки: новое обращение и переписка по своим обращениям. */
export function SupportSheet({ user, tripId, onClose }: { user: string; tripId: string | null; onClose: () => void }) {
  const [tickets, setTickets] = useState<Ticket[]>(loadLocal);
  const [view, setView] = useState<"new" | "list" | string>(() => (loadLocal().length ? "list" : "new"));
  const [topic, setTopic] = useState<Ticket["topic"]>(tripId ? "trip" : "other");
  const [text, setText] = useState("");
  const [contact, setContact] = useState("");
  const [attach, setAttach] = useState(Boolean(tripId));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<Ticket | null>(null);

  const update = (ts: Ticket[]) => { setTickets(ts); saveLocal(ts); };

  useEffect(() => {
    api.supportSync(user, loadLocal()).then((r) => update(r.tickets)).catch(() => undefined);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [user, onClose]);

  const submit = async () => {
    if (text.trim().length < 10) { setError("Опишите вопрос подробнее — хотя бы пару предложений."); return; }
    if (contact.trim() && !/^\S+@\S+\.\S+$|^\+?[\d\s()-]{10,}$|^@\w{4,}$/.test(contact.trim())) {
      setError("Контакт: e-mail, телефон или ник в Telegram (@name). Или оставьте поле пустым."); return;
    }
    setBusy(true); setError(null);
    try {
      const t = await api.support({ user_id: user, topic, text: text.trim(), contact: contact.trim() || undefined, trip_id: attach ? tripId : null });
      update([t, ...tickets]); setSent(t); setText("");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const open = tickets.find((t) => t.id === view);

  return createPortal(
    <div className="sheet-wrap" onClick={onClose}>
      <div className="sheet glass-modal support" role="dialog" aria-modal="true" aria-label="Поддержка" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-grip" />
        <div className="sheet-head">
          <h3>{open ? `Обращение ${open.id}` : "Поддержка Waylo"}</h3>
          <GlassIcon name="close" label="Закрыть" size="sm" onClick={onClose} />
        </div>
        {!open && (
          <nav className="segmented support-tabs" aria-label="Разделы поддержки">
            <button className={view === "new" ? "on" : ""} onClick={() => { setView("new"); setSent(null); }}>Новое обращение</button>
            <button className={view === "list" ? "on" : ""} onClick={() => setView("list")}>Мои обращения{tickets.length ? ` · ${tickets.length}` : ""}</button>
          </nav>
        )}

        {open ? <Thread ticket={open} user={user} onBack={() => setView("list")}
          onUpdate={(t) => update(tickets.map((x) => (x.id === t.id ? t : x)))} />
        : view === "list" ? (
          tickets.length ? (
            <ul className="tickets">
              {tickets.map((t) => (
                <li key={t.id}>
                  <button className="ticket" onClick={() => setView(t.id)}>
                    <span className={`tstatus s-${t.status}`}>{STATUS_LABEL[t.status]}</span>
                    <b>{TOPIC_LABEL[t.topic]} · {t.id}</b>
                    <span className="muted">{t.messages[t.messages.length - 1]?.text.slice(0, 90)}</span>
                    <small className="muted">{fmt(t.created_at)}</small>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="muted">Обращений пока нет.</p>
        ) : sent ? (
          <div className="support-done">
            <span className="done-icon"><Icon name="check" size={24} /></span>
            <b>Обращение {sent.id} отправлено</b>
            <span className="muted">Ответ появится в разделе «Мои обращения» на этом устройстве{sent.contact ? `; для связи поддержка увидит ваш контакт ${sent.contact}` : ""}.</span>
            <button className="btn" onClick={() => setView(sent.id)}>Открыть обращение</button>
          </div>
        ) : (
          <form className="form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <label className="field">
              <span>Тема</span>
              <select value={topic} onChange={(e) => setTopic(e.target.value as Ticket["topic"])}>
                {Object.entries(TOPIC_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Сообщение</span>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={4000}
                placeholder="Опишите, что случилось или что хотите узнать" />
            </label>
            <label className="field">
              <span>Как с вами связаться (необязательно)</span>
              <input value={contact} onChange={(e) => setContact(e.target.value)} maxLength={120} placeholder="e-mail, телефон или @telegram" />
            </label>
            {tripId && (
              <label className="agree">
                <input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} />
                <span>Приложить текущую поездку — поддержка увидит план и заказ</span>
              </label>
            )}
            {error && <p className="form-error">{error}</p>}
            <button className="btn primary big-btn" disabled={busy}><Icon name="send" size={16} /> {busy ? "Отправляем…" : "Отправить обращение"}</button>
          </form>
        )}
      </div>
    </div>,
    document.body,
  );
}

function Thread({ ticket, user, onBack, onUpdate }: { ticket: Ticket; user: string; onBack: () => void; onUpdate: (t: Ticket) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const send = async () => {
    if (!text.trim()) return;
    setBusy(true); setError(null);
    try { onUpdate(await api.supportMessage(ticket.id, user, text.trim())); setText(""); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="thread">
      <button className="link" onClick={onBack}><Icon name="back" size={14} /> Все обращения</button>
      <p className="muted">{TOPIC_LABEL[ticket.topic]} · {STATUS_LABEL[ticket.status]}</p>
      <div className="thread-msgs">
        {ticket.messages.map((m, i) => (
          <div key={i} className={`tmsg ${m.author}`}>
            <small>{m.author === "user" ? "Вы" : "Поддержка Waylo"} · {fmt(m.at)}</small>
            <p>{m.text}</p>
          </div>
        ))}
        {ticket.status === "open" && <p className="muted">Ответ поддержки появится здесь.</p>}
      </div>
      {ticket.status !== "closed" && (
        <form className="thread-form" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={4000} placeholder="Дополнить обращение" />
          <button className="btn primary" disabled={busy || !text.trim()}><Icon name="send" size={16} /> Отправить</button>
        </form>
      )}
      {error && <p className="form-error">{error}</p>}
    </div>
  );
}

/** Страница сотрудника поддержки: /support-admin, вход по ключу SUPPORT_ADMIN_TOKEN. */
export function SupportAdmin() {
  const [token, setToken] = useState(() => { try { return sessionStorage.getItem("waylo_admin") ?? ""; } catch { return ""; } });
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replies, setReplies] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<"active" | "all">("active");

  const load = async (t = token) => {
    setError(null);
    try {
      const r = await api.supportAdmin(t);
      setTickets(r.tickets);
      try { sessionStorage.setItem("waylo_admin", t); } catch { /* приватный режим */ }
    } catch (e) { setTickets(null); setError((e as Error).message); }
  };
  useEffect(() => { if (token) load(); }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (fn: () => Promise<Ticket>) => {
    try { const t = await fn(); setTickets((ts) => ts?.map((x) => (x.id === t.id ? t : x)) ?? null); }
    catch (e) { setError((e as Error).message); }
  };

  const shown = (tickets ?? []).filter((t) => filter === "all" || t.status !== "closed");
  return (
    <div className="admin">
      <header className="admin-head card-solid">
        <img src="/logo-dark.png" alt="waylo" />
        <h1>Поддержка: обращения</h1>
        {tickets && <button className="btn" onClick={() => load()}>Обновить</button>}
      </header>
      {!tickets ? (
        <form className="card-solid form admin-login" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <label className="field"><span>Ключ доступа</span>
            <input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
            <small className="muted">Значение SUPPORT_ADMIN_TOKEN из настроек сервера.</small>
          </label>
          {error && <p className="form-error">{error}</p>}
          <button className="btn primary" disabled={!token}>Войти</button>
        </form>
      ) : (
        <>
          <nav className="segmented" aria-label="Фильтр">
            <button className={filter === "active" ? "on" : ""} onClick={() => setFilter("active")}>Открытые</button>
            <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>Все · {tickets.length}</button>
          </nav>
          {error && <p className="form-error">{error}</p>}
          {!shown.length && <p className="card-solid muted">Обращений нет.</p>}
          {shown.map((t) => (
            <article key={t.id} className="card-solid admin-ticket">
              <div className="admin-ticket-head">
                <b>{t.id} · {TOPIC_LABEL[t.topic]}</b>
                <span className={`tstatus s-${t.status}`}>{STATUS_LABEL[t.status]}</span>
              </div>
              <small className="muted">{fmt(t.created_at)} · пользователь {t.user_id}{t.contact ? ` · контакт: ${t.contact}` : ""}{t.trip_id ? ` · поездка ${t.trip_id}` : ""}</small>
              <div className="thread-msgs">
                {t.messages.map((m, i) => (
                  <div key={i} className={`tmsg ${m.author}`}><small>{m.author === "user" ? "Пользователь" : "Поддержка"} · {fmt(m.at)}</small><p>{m.text}</p></div>
                ))}
              </div>
              {t.status !== "closed" && (
                <form className="thread-form" onSubmit={(e) => {
                  e.preventDefault();
                  const txt = (replies[t.id] ?? "").trim();
                  if (txt) act(() => api.supportReply(token, t.id, txt)).then(() => setReplies((r) => ({ ...r, [t.id]: "" })));
                }}>
                  <textarea rows={2} value={replies[t.id] ?? ""} onChange={(e) => setReplies((r) => ({ ...r, [t.id]: e.target.value }))} placeholder="Ответ пользователю" />
                  <div className="clarify-actions">
                    <button className="btn primary" disabled={!(replies[t.id] ?? "").trim()}>Ответить</button>
                    <button type="button" className="btn" onClick={() => act(() => api.supportClose(token, t.id))}>Закрыть</button>
                  </div>
                </form>
              )}
            </article>
          ))}
        </>
      )}
    </div>
  );
}
