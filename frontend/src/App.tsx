import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, loadAuth, modelLabel, saveAuth, type Auth, type TripResponse } from "./api";
import type { ChatMsg, Health, SavedGuest, Trip } from "./types";
import { Chat } from "./components/Chat";
import { TripTab } from "./components/TripTab";
import { WalksTab } from "./components/WalksTab";
import { CheckoutTab } from "./components/CheckoutTab";
import { Backdrop, sceneFor, SCENE_LABEL } from "./components/Backdrop";
import { GlassIcon, Icon, type IconName } from "./components/Icons";
import { Onboarding, Splash, introSeen } from "./components/Intro";
import { Markdown } from "./components/Markdown";
import { SupportSheet } from "./components/Support";
import { ProfileSheet } from "./components/Profile";
import type { GuestDraft, GuestOut } from "./components/GuestsForm";

const EXAMPLES = [
  "Хочу на пять дней в Санкт-Петербург в ноябре. Бюджет — 45 000 рублей на двоих. Любим красивые улицы, необычные кафе, музеи и атмосферные места для фотографий. Хотим жить недалеко от центра и не проводить весь отпуск в транспорте",
  "Хочу куда-нибудь к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов",
  "Трёхдневная поездка в Казань, бюджет 40 тысяч, архитектура и местная кухня",
  "Калининград на выходные с собакой",
];

const MOODS: { icon: IconName; label: string; prompt: string }[] = [
  { icon: "wave", label: "К морю", prompt: "Хочу к тёплому морю, недорого" },
  { icon: "mountain", label: "Природа", prompt: "Хочу на природу, красивые виды и прогулки" },
  { icon: "building", label: "Города", prompt: "Хочу посмотреть красивый город, архитектура и музеи" },
  { icon: "cup", label: "Гастро", prompt: "Хочу поехать поесть вкусно, местная кухня и кафе" },
  { icon: "sun", label: "Тепло зимой", prompt: "Куда поехать зимой, где тепло, бюджет 150 тысяч на двоих" },
];

const POPULAR = ["spb", "kazan", "sochi", "kaliningrad", "yerevan", "tbilisi", "irkutsk", "istanbul", "murmansk", "samarkand"];

const TAG_VIEW: [string, IconName, string][] = [
  ["sea", "wave", "море"], ["nature", "mountain", "природа"], ["architecture", "building", "архитектура"],
  ["history", "museum", "история"], ["food", "cup", "кухня"], ["warm", "sun", "тепло"], ["culture", "museum", "музеи"],
];

type Tab = "trip" | "walks" | "checkout";
const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: "trip", label: "Поездка", icon: "hotel" },
  { id: "walks", label: "Прогулки", icon: "map" },
  { id: "checkout", label: "Оформление", icon: "bag" },
];

function userId(): string {
  try {
    let id = localStorage.getItem("waylo_user");
    if (!id) { id = "u_" + Math.random().toString(36).slice(2, 10); localStorage.setItem("waylo_user", id); }
    return id;
  } catch { return "anonymous"; }
}

const SESSION = "waylo_session_v1";
type Saved = { trip: Trip | null; chat: ChatMsg[]; tab: Tab; mode: "auto" | "offline" };

function readSaved(): Saved | null {
  try { return JSON.parse(localStorage.getItem(SESSION) ?? "null"); } catch { return null; }
}

const DRAFT = "waylo_draft_v1";
type Draft = Partial<{ prompt: string; city: string; from: string; to: string; adults: number; kids: number; touched: boolean }>;

function readDraft(): Draft {
  try { return JSON.parse(localStorage.getItem(DRAFT) ?? "{}"); } catch { return {}; }
}

function readPaused(): boolean {
  try { return localStorage.getItem("waylo_video_paused") === "1"; } catch { return false; }
}

export default function App() {
  const [saved] = useState(readSaved);
  const [health, setHealth] = useState<Health | null>(null);
  const [trip, setTrip] = useState<Trip | null>(saved?.trip ?? null);
  const [chat, setChat] = useState<ChatMsg[]>(saved?.chat ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>(saved?.tab ?? "trip");
  const [mode, setMode] = useState<"auto" | "offline">(saved?.mode ?? "auto");
  const [device] = useState(userId);
  const [auth, setAuth] = useState<Auth | null>(loadAuth);
  const user = auth?.account.id ?? device;
  const [profile, setProfile] = useState<{ reason?: string } | null>(null);
  const [savedGuests, setSavedGuests] = useState<SavedGuest[]>([]);
  const [lastTrip, setLastTrip] = useState<string | null>(null);
  const [paused, setPaused] = useState(readPaused);
  const [chatOpen, setChatOpen] = useState(false);
  const [supportOpen, setSupportOpen] = useState(false);
  const [intro, setIntro] = useState<"splash" | "onboarding" | null>(
    (introSeen() || saved?.trip) && !new URLSearchParams(location.search).has("intro") ? null : "splash");

  useEffect(() => {
    api.health().then(setHealth).catch(() => setError("Сервер Waylo недоступен. Запустите: uv run --project backend uvicorn app.main:app --app-dir backend --port 8000"));
    api.latest(user).then((r) => setLastTrip(r.trip_id)).catch(() => undefined);
    if (saved?.trip) {
      const t = saved.trip;
      api.trip(t.id).then(apply).catch(() => api.restore(t, saved.chat).then(apply).catch(() => undefined));
    }
  }, [user]);

  useEffect(() => {
    try {
      if (trip || chat.length) localStorage.setItem(SESSION, JSON.stringify({ trip, chat: chat.slice(-200), tab, mode }));
      else localStorage.removeItem(SESSION);
    } catch {}
  }, [trip, chat, tab, mode]);

  const togglePause = () => setPaused((p) => {
    try { localStorage.setItem("waylo_video_paused", p ? "0" : "1"); } catch {}
    return !p;
  });

  const apply = (r: TripResponse) => { setTrip(r.trip); setChat(r.chat); };

  async function run(fn: () => Promise<TripResponse>) {
    setBusy(true); setError(null);
    try { apply(await fn()); } catch (e) {
      setError((e as Error).message);
      if (trip?.id) api.trip(trip.id).then(apply).catch(() => undefined);
    } finally { setBusy(false); }
  }

  useEffect(() => {
    const onShow = () => { if (document.visibilityState === "visible" && trip?.id && !busy) api.trip(trip.id).then(apply).catch(() => undefined); };
    document.addEventListener("visibilitychange", onShow);
    return () => document.removeEventListener("visibilitychange", onShow);
  }, [trip?.id, busy]);

  const send = (text: string) => {
    setChat((c) => [...c, { role: "user", text, at: new Date().toTimeString().slice(0, 5) }]);
    run(() => api.chat(trip?.id ?? null, user, text, mode));
  };

  const start = (text: string) => { setTab("trip"); setIntro(null); send(text); };
  const reset = () => { setTrip(null); setChat([]); setError(null); setChatOpen(false); };
  const splashDone = useCallback(() => setIntro("onboarding"), []);
  const closeProfile = useCallback(() => setProfile(null), []);
  const onAuth = (a: Auth) => { saveAuth(a); setAuth(a); setProfile(null); };
  const onLogout = () => { saveAuth(null); setAuth(null); setSavedGuests([]); };
  const openTrip = (id: string) => { setProfile(null); setTab("trip"); run(() => api.trip(id)); };

  useEffect(() => {
    if (auth && tab === "checkout") api.me().then((m) => setSavedGuests(m.guests)).catch(() => undefined);
  }, [auth, tab]);

  const checkout = async (tripId: string, guests: GuestOut[], card: string, toSave: (GuestDraft & { doc_kind: string })[]) => {
    await Promise.all(toSave.map((g) => api.saveGuest({ ...g, last: g.last.trim(), first: g.first.trim(), middle: g.middle.trim() })
      .catch(() => undefined)));
    return api.checkout(tripId, guests, card);
  };
  const closeSupport = useCallback(() => setSupportOpen(false), []);
  const cityNames = useMemo(() => Object.fromEntries((health?.cities ?? []).map((c) => [c.id, c.name])), [health]);
  const home = !trip && !chat.length;
  const scene = sceneFor(trip, health);
  const tripReady = Boolean(trip?.days.length) && !trip?.budget_gap;

  return (
    <>
      <Backdrop scene={scene} mode={home ? "home" : "results"} paused={paused} youtubeId={health?.home_youtube_id} />
      {home ? (
        <Home health={health} onStart={start} lastTrip={lastTrip}
          onOpenLast={() => lastTrip && run(() => api.trip(lastTrip))} mode={mode} setMode={setMode}
          paused={paused} togglePause={togglePause} error={error} onHelp={() => setIntro("onboarding")} hidden={intro !== null}
          onSupport={() => setSupportOpen(true)} onProfile={() => setProfile({})} authName={auth?.account.first_name ?? null} />
      ) : (
        <div className="app">
          <header className="topbar glass-light">
            <GlassIcon name="back" label="Новая поездка" onClick={reset} />
            <button className="brand" onClick={reset} title="На главную"><img src="/logo-dark.png" alt="waylo" /></button>
            <TripSummary trip={trip} city={cityNames[trip?.params.destination ?? ""] ?? ""} busy={busy} />
            <nav className="segmented" aria-label="Разделы поездки">
              {TABS.map((t) => (
                <button key={t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}
                  disabled={t.id !== "trip" && !tripReady} aria-current={tab === t.id ? "page" : undefined}>{t.label}</button>
              ))}
            </nav>
            <div className="topbar-end">
              <AgentStatus health={health} mode={mode} setMode={setMode} compact />
              <GlassIcon name="user" label={auth ? "Профиль" : "Войти"} onClick={() => setProfile({})} size="sm" active={Boolean(auth)} />
              <GlassIcon name="support" label="Поддержка" onClick={() => setSupportOpen(true)} size="sm" />
              <GlassIcon name={paused ? "play" : "pause"} label={paused ? `Включить видео (${SCENE_LABEL[scene]})` : "Остановить фоновое видео"}
                onClick={togglePause} size="sm" />
            </div>
          </header>
          {error && <div className="toast error" role="alert"><Icon name="alert" size={17} /> <span>{error}</span> <button className="link" onClick={() => setError(null)}>Скрыть</button></div>}
          <div className={`layout ${chatOpen ? "chat-open" : ""}`}>
            <main className="panel" key={tab}>
              {trip && trip.status === "need_info" && !trip.days.length ? (
                <Clarify question={[...chat].reverse().find((m) => m.role === "assistant")?.text ?? ""} busy={busy} onSend={send} />
              ) : trip ? (
                <>
                  {tab === "trip" && <TripTab trip={trip} busy={busy} city={cityNames[trip.params.destination ?? ""] ?? ""}
                    onDestination={(c) => run(() => api.destination(trip.id, c))}
                    onTransport={(id) => run(() => api.transport(trip.id, id))}
                    onHotel={(id) => run(() => api.hotel(trip.id, id))} onSend={send} />}
                  {tab === "walks" && <WalksTab trip={trip} busy={busy}
                    onDay={(d, a, extra) => run(() => api.day(trip.id, d, a, extra))} />}
                  {tab === "checkout" && <CheckoutTab trip={trip} busy={busy} auth={auth} saved={savedGuests}
                    onLogin={() => setProfile({ reason: "Чтобы оплатить поездку, войдите в профиль или создайте его." })}
                    onCheckout={(g, card, toSave) => run(() => checkout(trip.id, g, card, toSave))}
                    onExtra={(k, card) => run(() => api.extras(trip.id, k, card))} />}
                </>
              ) : <Loading busy={busy} />}
            </main>
            <Chat chat={chat} trip={trip} busy={busy} onSend={send} onClose={() => setChatOpen(false)} />
          </div>
          <nav className="bottom-nav glass-floating" aria-label="Разделы поездки">
            {TABS.map((t) => (
              <button key={t.id} className={tab === t.id && !chatOpen ? "on" : ""} disabled={t.id !== "trip" && !tripReady}
                onClick={() => { setTab(t.id); setChatOpen(false); }}>
                <Icon name={t.icon} size={20} /><span>{t.label}</span>
              </button>
            ))}
            <button className={chatOpen ? "on" : ""} onClick={() => setChatOpen((o) => !o)}>
              <Icon name="chat" size={20} /><span>Агент</span>{busy && <i className="nav-dot" />}
            </button>
          </nav>
        </div>
      )}
      {profile && <ProfileSheet auth={auth} device={device} reason={profile.reason} onAuth={onAuth} onLogout={onLogout}
        onOpenTrip={openTrip} onClose={closeProfile} />}
      {supportOpen && <SupportSheet user={user} tripId={trip?.id ?? null} onClose={closeSupport} />}
      {intro === "splash" && <Splash onDone={splashDone} />}
      {intro === "onboarding" && <Onboarding onFinish={() => setIntro(null)} onTry={start} />}
    </>
  );
}

function TripSummary({ trip, city, busy }: { trip: Trip | null; city: string; busy: boolean }) {
  if (!trip?.params.destination) return <div className="tsum"><b>{busy ? "Агент разбирает запрос…" : "Новая поездка"}</b></div>;
  const p = trip.params;
  const start = p.start_date && trip.days.length ? new Date(p.start_date + "T00:00") : null;
  const end = start ? new Date(start.getTime() + (p.nights ?? 0) * 864e5) : null;
  const fmt = (d: Date) => d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  return (
    <div className="tsum">
      <b>{city}</b>
      <span>{start && end && <><Icon name="calendar" size={14} /> {fmt(start)} – {fmt(end)}</>}</span>
      <span><Icon name="guests" size={14} /> {p.adults + p.children}{p.pets ? " + питомец" : ""}</span>
    </div>
  );
}

function Clarify({ question, busy, onSend }: { question: string; busy: boolean; onSend: (t: string) => void }) {
  const [answer, setAnswer] = useState("");
  const submit = () => { if (answer.trim() && !busy) { onSend(answer.trim()); setAnswer(""); } };
  if (busy) return <Loading busy />;
  return (
    <section className="clarify card-solid">
      <span className="gicon gicon-md as-icon"><Icon name="chat" size={19} /></span>
      <h2>Нужно уточнить пару деталей</h2>
      <Markdown text={question} />
      <form className="clarify-form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <label className="field">
          <span>Ваш ответ</span>
          <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} rows={2} autoFocus
            placeholder="Например: с 12 по 15 декабря, из Казани, двое взрослых, бюджет 60 000"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} />
        </label>
        <div className="clarify-actions">
          <button className="btn primary" disabled={!answer.trim()}><Icon name="send" size={16} /> Ответить</button>
          <button type="button" className="btn" onClick={() => onSend("На ваше усмотрение")}>На ваше усмотрение</button>
        </div>
      </form>
    </section>
  );
}

function Loading({ busy }: { busy: boolean }) {
  return (
    <section className="state card-solid">
      {busy ? (
        <>
          <div className="spinner" />
          <b>Агент собирает поездку</b>
          <span className="muted">Разбираю запрос, ищу дорогу и отели, смотрю погоду и строю прогулки — обычно несколько секунд.</span>
          <div className="skeleton"><i /><i /><i /></div>
        </>
      ) : <span className="muted">Здесь появится план поездки</span>}
    </section>
  );
}

function Home({ health, onStart, paused, togglePause, error, onHelp, hidden, onSupport, onProfile, authName }: {
  health: Health | null; onStart: (t: string) => void; lastTrip: string | null; onOpenLast: () => void;
  mode: "auto" | "offline"; setMode: (m: "auto" | "offline") => void; paused: boolean; togglePause: () => void;
  error: string | null; onHelp: () => void; hidden: boolean; onSupport: () => void; onProfile: () => void; authName: string | null;
}) {
  const [draft] = useState(readDraft);
  const [prompt, setPrompt] = useState(draft.prompt ?? "");
  const [city, setCity] = useState(draft.city ?? "");
  const [from, setFrom] = useState(draft.from ?? "");
  const [to, setTo] = useState(draft.to ?? "");
  const [adults, setAdults] = useState(draft.adults ?? 2);
  const [kids, setKids] = useState(draft.kids ?? 0);
  const [touched, setTouched] = useState(draft.touched ?? false);
  useEffect(() => {
    try { localStorage.setItem(DRAFT, JSON.stringify({ prompt, city, from, to, adults, kids, touched })); } catch {}
  }, [prompt, city, from, to, adults, kids, touched]);
  const area = useRef<HTMLTextAreaElement>(null);
  const cities = health?.cities ?? [];
  const cityName = (id: string) => cities.find((c) => c.id === id)?.name ?? "";
  const day = (iso: string) => new Date(iso + "T00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  const nights = from && to ? Math.round((+new Date(to) - +new Date(from)) / 864e5) : 0;

  const compose = () => {
    const parts = [prompt.trim()];
    if (city && !prompt.toLowerCase().includes(cityName(city).toLowerCase().slice(0, 5))) parts.push(`Направление: ${cityName(city)}.`);
    if (from) parts.push(nights > 0 ? `Даты: с ${day(from)} по ${day(to)}, ${nights} ноч.` : `Даты: с ${day(from)}.`);
    if (touched) parts.push(`Едут ${adults} взрослых` + (kids ? ` и ${kids} детей.` : ", без детей."));
    return parts.filter(Boolean).join(" ");
  };
  const canGo = Boolean(prompt.trim() || city);
  const go = () => { if (canGo) onStart(compose() || `Поездка в ${cityName(city)}`); };
  const clear = () => { setPrompt(""); setCity(""); setFrom(""); setTo(""); setAdults(2); setKids(0); setTouched(false); area.current?.focus(); };
  const today = new Date().toISOString().slice(0, 10);
  const pickFrom = (v: string) => { setFrom(v); if (to && v && to <= v) setTo(""); };

  return (
    <div className={`home ${hidden ? "behind" : ""}`}>
      <header className="home-top">
        <img src="/logo-white.png" alt="waylo" className="home-logo" />
        <div className="home-top-actions">
          <button className="pill glass-subtle" onClick={onHelp}><Icon name="info" size={16} /> Как это работает</button>
          <button className="pill glass-subtle" onClick={onSupport}><Icon name="support" size={16} /> Поддержка</button>
          <GlassIcon name={paused ? "play" : "pause"} label={paused ? "Включить фоновое видео" : "Остановить фоновое видео"} onClick={togglePause} size="sm" />
          <button className="pill glass-subtle" onClick={onProfile}><Icon name="user" size={16} /> {authName ?? "Войти"}</button>
        </div>
      </header>

      <section className="home-hero">
        <span className="eyebrow glass-subtle"><Icon name="compass" size={14} /> ИИ-агент для путешествий</span>
        <h1>Одно сообщение.<br />Вся поездка.</h1>
        <p>Опишите, куда и как хотите поехать, — Waylo подберёт направление, дорогу и отель, посчитает бюджет и составит прогулки по дням.</p>
      </section>

      <form className="search glass-floating" onSubmit={(e) => { e.preventDefault(); go(); }} aria-label="Запрос к агенту">
        <label className="search-label" htmlFor="prompt">Опишите поездку</label>
        <div className="search-prompt">
          <Icon name="compass" size={20} />
          <textarea id="prompt" ref={area} value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2}
            placeholder="Например: 4 дня в Казани в декабре вдвоём, бюджет 50 000, любим архитектуру и кухню"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } }} />
          {(prompt || city || from) && <GlassIcon name="close" label="Очистить запрос" size="sm" onClick={clear} />}
        </div>
        <div className="search-fields">
          <label className="sfield">
            <Icon name="pin" size={18} />
            <span><small>Направление</small>
              <select value={city} onChange={(e) => setCity(e.target.value)}>
                <option value="">Любое — подскажет агент</option>
                {cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </span>
          </label>
          <div className="sfield sfield-dates">
            <Icon name="calendar" size={18} />
            <label><small>Туда</small><input type="date" min={today} value={from} onChange={(e) => pickFrom(e.target.value)} aria-label="Дата начала поездки" /></label>
            <span className="dates-sep" aria-hidden="true">—</span>
            <label><small>Обратно{nights > 0 ? ` · ${nights} ноч.` : ""}</small>
              <input type="date" min={from || today} value={to} disabled={!from} onChange={(e) => setTo(e.target.value)} aria-label="Дата окончания поездки" /></label>
          </div>
          <div className="sfield sfield-guests">
            <Icon name="guests" size={18} />
            <Counter label="Взрослые" value={adults} min={1} max={8} onChange={(v) => { setTouched(true); setAdults(v); }} />
            <Counter label="Дети" value={kids} min={0} max={6} onChange={(v) => { setTouched(true); setKids(v); }} />
          </div>
          <button className="btn primary search-go" disabled={!canGo}><Icon name="search" size={18} /> Спланировать</button>
        </div>
        <p className="search-hint">Enter — отправить · Shift + Enter — новая строка · Поля необязательны: всё можно написать словами</p>
      </form>

      <section className="home-block">
        <h2 className="block-title">Быстрый старт</h2>
        <div className="moods">
          {MOODS.map((m) => (
            <button key={m.label} className="mood glass-subtle" onClick={() => onStart(m.prompt)}>
              <span className="gicon gicon-sm as-icon"><Icon name={m.icon} size={16} /></span>{m.label}
            </button>
          ))}
        </div>
      </section>

      <section className="home-block">
        <h2 className="block-title">Популярные направления</h2>
        <div className="dest-rail">
          {POPULAR.map((id) => cities.find((c) => c.id === id)).filter(Boolean).map((c) => {
            const tags = TAG_VIEW.filter(([t]) => c!.tags.includes(t)).slice(0, 2);
            return (
              <button key={c!.id} className="dest-card glass-light" onClick={() => onStart(`Хочу в ${c!.name} на 4 дня вдвоём`)}>
                <span className="dest-icons">{tags.map(([t, icon]) => <span key={t} className="gicon gicon-sm as-icon"><Icon name={icon} size={15} /></span>)}</span>
                <b>{c!.name}</b>
                <small>{c!.country}{tags.length ? " · " + tags.map(([, , l]) => l).join(", ") : ""}</small>
                <span className="dest-go">Спланировать <Icon name="back" size={14} className="flip" /></span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="home-block">
        <h2 className="block-title">Примеры запросов</h2>
        <div className="examples">
          {EXAMPLES.map((x) => (
            <button key={x} className="example glass-light" onClick={() => onStart(x)}>
              <Icon name="chat" size={16} /><span>{x.length > 130 ? x.slice(0, 128) + "…" : x}</span>
            </button>
          ))}
        </div>
      </section>

      <footer className="home-foot">
        {error && <div className="toast error" role="alert"><Icon name="alert" size={17} /> <span>{error}</span></div>}
      </footer>
    </div>
  );
}

function Counter({ label, value, min, max, onChange }: {
  label: string; value: number; min: number; max: number; onChange: (v: number) => void;
}) {
  return (
    <span className="counter"><small>{label}</small>
      <span className="stepper">
        <button type="button" aria-label={`${label}: меньше`} disabled={value <= min} onClick={() => onChange(value - 1)}>−</button>
        <b aria-live="polite">{value}</b>
        <button type="button" aria-label={`${label}: больше`} disabled={value >= max} onClick={() => onChange(value + 1)}>+</button>
      </span>
    </span>
  );
}

function AgentStatus({ health, mode, setMode, compact }: {
  health: Health | null; mode: "auto" | "offline"; setMode: (m: "auto" | "offline") => void; compact?: boolean;
}) {
  if (!health) return null;
  const llm = health.agent !== "offline";
  return (
    <div className={`agent-status glass-subtle ${compact ? "compact" : ""}`}>
      <span className={`dot ${llm && mode === "auto" ? "on" : ""}`} />
      {llm ? (
        <select value={mode} onChange={(e) => setMode(e.target.value as "auto" | "offline")} aria-label="Режим агента">
          <option value="auto">{health.agent === "claude" && health.model ? modelLabel(health.model) : `${health.provider_label} · ${health.model}`}</option>
          <option value="offline">Офлайн-агент (без LLM)</option>
        </select>
      ) : <span title="Задайте GIGACHAT_CREDENTIALS или ANTHROPIC_API_KEY в .env, чтобы включить LLM">Офлайн-агент</span>}
    </div>
  );
}
