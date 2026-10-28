import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, rub, type Auth } from "../api";
import type { Me, SavedGuest } from "../types";
import { DOC_KINDS, NAME_RX } from "./GuestsForm";
import { GlassIcon, Icon } from "./Icons";

const STATUS: Record<string, string> = {
  need_info: "Уточняем детали", choose_destination: "Выбор направления", planning: "Собирается", ready: "План готов", purchased: "Оплачено",
};

const fmtDate = (iso: string) => new Date(iso + (iso.length === 10 ? "T00:00" : "")).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });

/** Окно профиля: вход и регистрация, а после входа — поездки, оплаты и сохранённые пассажиры. */
export function ProfileSheet({ auth, device, reason, onAuth, onLogout, onOpenTrip, onClose }: {
  auth: Auth | null; device: string; reason?: string;
  onAuth: (a: Auth) => void; onLogout: () => void; onOpenTrip: (id: string) => void; onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="sheet-wrap" onClick={onClose}>
      <div className="sheet glass-modal profile" role="dialog" aria-modal="true" aria-label="Профиль" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-grip" />
        <div className="sheet-head">
          <h3>{auth ? `${auth.account.first_name} ${auth.account.last_name}` : "Профиль Waylo"}</h3>
          <GlassIcon name="close" label="Закрыть" size="sm" onClick={onClose} />
        </div>
        {auth ? <Cabinet auth={auth} onLogout={onLogout} onOpenTrip={onOpenTrip} />
          : <AuthForm device={device} reason={reason} onAuth={onAuth} />}
      </div>
    </div>,
    document.body,
  );
}

function AuthForm({ device, reason, onAuth }: { device: string; reason?: string; onAuth: (a: Auth) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [f, setF] = useState({ last: "", first: "", login: "", password: "", repeat: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));

  const submit = async () => {
    setError(null);
    if (mode === "register") {
      if (!NAME_RX.test(f.last.trim()) || !NAME_RX.test(f.first.trim())) return setError("Фамилия и имя — с заглавной буквы, только буквы");
      if (f.password.length < 8 || !/\d/.test(f.password) || !/[A-Za-zА-Яа-я]/.test(f.password)) return setError("Пароль: от 8 символов, буквы и цифры");
      if (f.password !== f.repeat) return setError("Пароли не совпадают");
    }
    if (!f.login.trim()) return setError("Укажите e-mail или телефон");
    setBusy(true);
    try {
      onAuth(mode === "login"
        ? await api.login({ login: f.login, password: f.password, device_id: device })
        : await api.register({ login: f.login, password: f.password, last_name: f.last.trim(), first_name: f.first.trim(), device_id: device }));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="sheet-body">
      {reason && <p className="form-warn"><Icon name="info" size={15} /> {reason}</p>}
      <nav className="segmented support-tabs" aria-label="Вход или регистрация">
        <button className={mode === "login" ? "on" : ""} onClick={() => { setMode("login"); setError(null); }}>Вход</button>
        <button className={mode === "register" ? "on" : ""} onClick={() => { setMode("register"); setError(null); }}>Регистрация</button>
      </nav>
      <form className="form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {mode === "register" && (
          <div className="pay-row">
            <label className="field"><span>Фамилия</span><input value={f.last} onChange={(e) => set("last", e.target.value)} autoComplete="family-name" maxLength={40} /></label>
            <label className="field"><span>Имя</span><input value={f.first} onChange={(e) => set("first", e.target.value)} autoComplete="given-name" maxLength={40} /></label>
          </div>
        )}
        <label className="field"><span>E-mail или телефон</span>
          <input value={f.login} onChange={(e) => set("login", e.target.value)} autoComplete="username" placeholder="name@mail.ru или +7 999 123-45-67" maxLength={120} /></label>
        <label className="field"><span>Пароль</span>
          <input type="password" value={f.password} onChange={(e) => set("password", e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} maxLength={128} />
          {mode === "register" && <small className="muted">От 8 символов, буквы и цифры.</small>}</label>
        {mode === "register" && (
          <label className="field"><span>Повторите пароль</span>
            <input type="password" value={f.repeat} onChange={(e) => set("repeat", e.target.value)} autoComplete="new-password" maxLength={128} /></label>
        )}
        {error && <p className="form-error">{error}</p>}
        <button className="btn primary big-btn" disabled={busy}>{busy ? "Подождите…" : mode === "login" ? "Войти" : "Создать профиль"}</button>
        <small className="muted">Поездки, собранные на этом устройстве до входа, сохранятся в профиле.</small>
      </form>
    </div>
  );
}

function Cabinet({ auth, onLogout, onOpenTrip }: { auth: Auth; onLogout: () => void; onOpenTrip: (id: string) => void }) {
  const [me, setMe] = useState<Me | null>(null);
  const [tab, setTab] = useState<"trips" | "orders" | "guests">("trips");
  const [error, setError] = useState<string | null>(null);
  const load = () => api.me().then(setMe).catch((e) => {
    setError((e as Error).message);
    if (/Войдите/.test((e as Error).message)) onLogout();  // сессия истекла
  });
  useEffect(() => { load(); }, [auth.token]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="sheet-body">
      <p className="muted profile-login">{auth.account.login}</p>
      <nav className="segmented support-tabs" aria-label="Разделы профиля">
        <button className={tab === "trips" ? "on" : ""} onClick={() => setTab("trips")}>Поездки{me ? ` · ${me.trips.length}` : ""}</button>
        <button className={tab === "orders" ? "on" : ""} onClick={() => setTab("orders")}>Оплаты{me ? ` · ${me.orders.length}` : ""}</button>
        <button className={tab === "guests" ? "on" : ""} onClick={() => setTab("guests")}>Пассажиры{me ? ` · ${me.guests.length}` : ""}</button>
      </nav>
      {error && <p className="form-error">{error}</p>}
      {!me ? <div className="spinner" /> : tab === "trips" ? (
        me.trips.length ? (
          <ul className="tickets">
            {me.trips.map((t) => (
              <li key={t.id}>
                <button className="ticket" onClick={() => onOpenTrip(t.id)}>
                  <span className={`tstatus ${t.order ? "s-answered" : ""}`}>{STATUS[t.status] ?? t.status}</span>
                  <b>{t.city}{t.start_date ? ` · ${fmtDate(t.start_date)}, ${t.nights} ноч.` : ""}</b>
                  <span className="muted">{t.adults} взр.{t.children ? ` + ${t.children} дет.` : ""}{t.total ? ` · ${rub(t.total)}` : ""}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="muted">Поездок пока нет — опишите поездку на главной.</p>
      ) : tab === "orders" ? (
        me.orders.length ? (
          <ul className="tickets">
            {me.orders.map((t) => (
              <li key={t.id}>
                <button className="ticket" onClick={() => onOpenTrip(t.id)}>
                  <span className="tstatus s-answered">Оплачено (демо)</span>
                  <b>{t.order!.order_id} · {rub(t.order!.total)}</b>
                  <span className="muted">{t.city}{t.order!.payment ? ` · ${t.order!.payment}` : ""} · {fmtDate(t.order!.created_at)}</span>
                  {t.order!.post_purchase.map((x) => <small key={x} className="muted">{x}</small>)}
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="muted">Оплат пока нет.</p>
      ) : <Passengers guests={me.guests} onChange={load} />}
      <button className="link logout" onClick={() => { api.logout().catch(() => undefined); onLogout(); }}>Выйти из профиля</button>
    </div>
  );
}

const EMPTY = { last: "", first: "", middle: "", birth: "", doc: "", doc_kind: DOC_KINDS[0].label };

function Passengers({ guests, onChange }: { guests: SavedGuest[]; onChange: () => void }) {
  const [edit, setEdit] = useState<(typeof EMPTY & { id?: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);
  const kind = DOC_KINDS.find((k) => k.label === edit?.doc_kind) ?? DOC_KINDS[0];

  const save = async () => {
    if (!edit) return;
    if (!NAME_RX.test(edit.last.trim()) || !NAME_RX.test(edit.first.trim())) return setError("Фамилия и имя — как в документе");
    if (edit.middle.trim() && !NAME_RX.test(edit.middle.trim())) return setError("Проверьте отчество");
    if (!edit.birth || new Date(edit.birth) > new Date()) return setError("Укажите дату рождения");
    if (edit.doc && !kind.rx.test(edit.doc.trim())) return setError(kind.hint);
    try { await api.saveGuest({ ...edit, last: edit.last.trim(), first: edit.first.trim(), middle: edit.middle.trim() }); setEdit(null); setError(null); onChange(); }
    catch (e) { setError((e as Error).message); }
  };

  if (edit) {
    const set = (k: keyof typeof EMPTY, v: string) => setEdit((x) => x && ({ ...x, [k]: v }));
    return (
      <form className="form" onSubmit={(e) => { e.preventDefault(); save(); }}>
        <div className="pay-row">
          <label className="field"><span>Фамилия</span><input value={edit.last} onChange={(e) => set("last", e.target.value)} maxLength={40} /></label>
          <label className="field"><span>Имя</span><input value={edit.first} onChange={(e) => set("first", e.target.value)} maxLength={40} /></label>
        </div>
        <div className="pay-row">
          <label className="field"><span>Отчество, если есть</span><input value={edit.middle} onChange={(e) => set("middle", e.target.value)} maxLength={40} /></label>
          <label className="field"><span>Дата рождения</span><input type="date" value={edit.birth} max={new Date().toISOString().slice(0, 10)} onChange={(e) => set("birth", e.target.value)} /></label>
        </div>
        <div className="pay-row">
          <label className="field"><span>Документ</span>
            <select value={edit.doc_kind} onChange={(e) => setEdit((x) => x && ({ ...x, doc_kind: e.target.value, doc: "" }))}>
              {DOC_KINDS.map((k) => <option key={k.label}>{k.label}</option>)}
            </select></label>
          <label className="field"><span>Серия и номер</span>
            <input value={edit.doc} placeholder={kind.placeholder} onChange={(e) => set("doc", kind.format(e.target.value))} maxLength={14} /></label>
        </div>
        {error && <p className="form-error">{error}</p>}
        <div className="clarify-actions">
          <button className="btn primary">Сохранить</button>
          <button type="button" className="btn" onClick={() => { setEdit(null); setError(null); }}>Отмена</button>
        </div>
      </form>
    );
  }
  return (
    <div className="passengers">
      {guests.length ? (
        <ul className="tickets">
          {guests.map((g) => (
            <li key={g.id} className="passenger">
              <div>
                <b>{g.last} {g.first} {g.middle}</b>
                <span className="muted">{fmtDate(g.birth)} {new Date(g.birth).getFullYear()} · {g.doc ? `${g.doc_kind} •••• ${g.doc.replace(/\s/g, "").slice(-4)}` : "документ не указан"}</span>
              </div>
              <div className="passenger-actions">
                <button className="link" onClick={() => setEdit({ ...EMPTY, ...g })}>Изменить</button>
                <button className="link danger" onClick={() => api.deleteGuest(g.id).then(onChange)}>Удалить</button>
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="muted">Сохранённых пассажиров пока нет. Их можно добавить здесь или при оформлении поездки.</p>}
      <button className="btn" onClick={() => setEdit({ ...EMPTY })}><Icon name="user" size={16} /> Добавить пассажира</button>
    </div>
  );
}
