import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, modelLabel, type TripResponse } from "./api";
import type { ChatMsg, Health, Trip } from "./types";
import { Chat } from "./components/Chat";
import { TripTab } from "./components/TripTab";
import { WalksTab } from "./components/WalksTab";
import { CheckoutTab } from "./components/CheckoutTab";
import { Backdrop, sceneFor, SCENE_LABEL } from "./components/Backdrop";
import { GlassIcon, Icon, type IconName } from "./components/Icons";
import { Onboarding, Splash, introSeen } from "./components/Intro";

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

function readPaused(): boolean {
  try { return localStorage.getItem("waylo_video_paused") === "1"; } catch { return false; }
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [trip, setTrip] = useState<Trip | null>(null);
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("trip");
  const [mode, setMode] = useState<"auto" | "offline">("auto");
  const [user] = useState(userId);
  const [lastTrip, setLastTrip] = useState<string | null>(null);
  const [paused, setPaused] = useState(readPaused);
  const [chatOpen, setChatOpen] = useState(false);
  // ?intro — показать заставку и онбординг заново (удобно на презентации)
  const [intro, setIntro] = useState<"splash" | "onboarding" | null>(
    introSeen() && !new URLSearchParams(location.search).has("intro") ? null : "splash");

  useEffect(() => {
    api.health().then(setHealth).catch(() => setError("Сервер Waylo недоступен. Запустите: uv run --project backend uvicorn app.main:app --app-dir backend --port 8000"));
    api.latest(user).then((r) => setLastTrip(r.trip_id)).catch(() => undefined);
  }, [user]);

  const togglePause = () => setPaused((p) => {
    try { localStorage.setItem("waylo_video_paused", p ? "0" : "1"); } catch { /* приватный режим */ }
    return !p;
  });

  const apply = (r: TripResponse) => { setTrip(r.trip); setChat(r.chat); };

  async function run(fn: () => Promise<TripResponse>) {
    setBusy(true); setError(null);
    try { apply(await fn()); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const send = (text: string) => {
    setChat((c) => [...c, { role: "user", text, at: new Date().toTimeString().slice(0, 5) }]);
    run(() => api.chat(trip?.id ?? null, user, text, mode));
  };

  const start = (text: string) => { setTab("trip"); setIntro(null); send(text); };
  const reset = () => { setTrip(null); setChat([]); setError(null); setChatOpen(false); };
  const splashDone = useCallback(() => setIntro("onboarding"), []);
  const cityNames = useMemo(() => Object.fromEntries((health?.cities ?? []).map((c) => [c.id, c.name])), [health]);
  const home = !trip && !chat.length;
  const scene = sceneFor(trip, health);
  const tripReady = Boolean(trip?.days.length);

  return (
    <>
      <Backdrop scene={scene} mode={home ? "home" : "results"} paused={paused} youtubeId={health?.home_youtube_id} />
      {home ? (
        <Home health={health} onStart={start} lastTrip={lastTrip}
          onOpenLast={() => lastTrip && run(() => api.trip(lastTrip))} mode={mode} setMode={setMode}
          paused={paused} togglePause={togglePause} error={error} onHelp={() => setIntro("onboarding")} hidden={intro !== null} />
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
              <GlassIcon name={paused ? "play" : "pause"} label={paused ? `Включить видео (${SCENE_LABEL[scene]})` : "Остановить фоновое видео"}
                onClick={togglePause} size="sm" />
            </div>
          </header>
          {error && <div className="toast error" role="alert"><Icon name="alert" size={17} /> <span>{error}</span> <button className="link" onClick={() => setError(null)}>Скрыть</button></div>}
          <div className={`layout ${chatOpen ? "chat-open" : ""}`}>
            <main className="panel" key={tab}>
              {trip ? (
                <>
                  {tab === "trip" && <TripTab trip={trip} busy={busy} city={cityNames[trip.params.destination ?? ""] ?? ""}
                    onDestination={(c) => run(() => api.destination(trip.id, c))}
                    onTransport={(id) => run(() => api.transport(trip.id, id))}
                    onHotel={(id) => run(() => api.hotel(trip.id, id))} />}
                  {tab === "walks" && <WalksTab trip={trip} busy={busy}
                    onDay={(d, a, extra) => run(() => api.day(trip.id, d, a, extra))} />}
                  {tab === "checkout" && <CheckoutTab trip={trip} busy={busy}
                    onCheckout={(n) => run(() => api.checkout(trip.id, n))}
                    onExtra={(k) => run(() => api.extras(trip.id, k))} />}
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
      {intro === "splash" && <Splash onDone={splashDone} />}
      {intro === "onboarding" && <Onboarding onFinish={() => setIntro(null)} onTry={start} />}
    </>
  );
}

function TripSummary({ trip, city, busy }: { trip: Trip | null; city: string; busy: boolean }) {
  if (!trip?.params.destination) return <div className="tsum"><b>{busy ? "Агент разбирает запрос…" : "Новая поездка"}</b></div>;
  const p = trip.params;
  const start = p.start_date ? new Date(p.start_date + "T00:00") : null;
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

function Home({ health, onStart, lastTrip, onOpenLast, mode, setMode, paused, togglePause, error, onHelp, hidden }: {
  health: Health | null; onStart: (t: string) => void; lastTrip: string | null; onOpenLast: () => void;
  mode: "auto" | "offline"; setMode: (m: "auto" | "offline") => void; paused: boolean; togglePause: () => void;
  error: string | null; onHelp: () => void; hidden: boolean;
}) {
  const [prompt, setPrompt] = useState("");
  const [city, setCity] = useState("");
  const [date, setDate] = useState("");
  const [guests, setGuests] = useState(2);
  const [touched, setTouched] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const cities = health?.cities ?? [];
  const cityName = (id: string) => cities.find((c) => c.id === id)?.name ?? "";

  const compose = () => {
    const parts = [prompt.trim()];
    if (city && !prompt.toLowerCase().includes(cityName(city).toLowerCase().slice(0, 5))) parts.push(`Направление: ${cityName(city)}.`);
    if (date) parts.push(`Заезд ${new Date(date + "T00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}.`);
    if (touched && guests !== 2) parts.push(guests === 1 ? "Еду один." : `Нас ${guests} человека.`);
    return parts.filter(Boolean).join(" ");
  };
  const canGo = Boolean(prompt.trim() || city);
  const go = () => { if (canGo) onStart(compose() || `Поездка в ${cityName(city)}`); };
  const clear = () => { setPrompt(""); setCity(""); setDate(""); setGuests(2); setTouched(false); area.current?.focus(); };
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className={`home ${hidden ? "behind" : ""}`}>
      <header className="home-top">
        <img src="/logo-white.png" alt="waylo" className="home-logo" />
        <div className="home-top-actions">
          <button className="pill glass-subtle" onClick={onHelp}><Icon name="info" size={16} /> Как это работает</button>
          <GlassIcon name={paused ? "play" : "pause"} label={paused ? "Включить фоновое видео" : "Остановить фоновое видео"} onClick={togglePause} size="sm" />
          {lastTrip && <GlassIcon name="user" label="Моя последняя поездка" onClick={onOpenLast} />}
        </div>
      </header>

      <section className="home-hero">
        <span className="eyebrow glass-subtle"><Icon name="spark" size={14} /> ИИ-агент для путешествий</span>
        <h1>Одно сообщение.<br />Вся поездка.</h1>
        <p>Опишите, куда и как хотите поехать, — Waylo подберёт направление, дорогу и отель, посчитает бюджет и составит прогулки по дням.</p>
      </section>

      <form className="search glass-floating" onSubmit={(e) => { e.preventDefault(); go(); }} aria-label="Запрос к агенту">
        <label className="search-label" htmlFor="prompt">Опишите поездку</label>
        <div className="search-prompt">
          <Icon name="spark" size={20} />
          <textarea id="prompt" ref={area} value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2}
            placeholder="Например: 4 дня в Казани в декабре вдвоём, бюджет 50 000, любим архитектуру и кухню"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } }} />
          {(prompt || city || date) && <GlassIcon name="close" label="Очистить запрос" size="sm" onClick={clear} />}
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
          <label className="sfield">
            <Icon name="calendar" size={18} />
            <span><small>Заезд</small><input type="date" min={today} value={date} onChange={(e) => setDate(e.target.value)} /></span>
          </label>
          <div className="sfield">
            <Icon name="guests" size={18} />
            <span><small>Гости</small>
              <span className="stepper">
                <button type="button" aria-label="Меньше гостей" disabled={guests <= 1} onClick={() => { setTouched(true); setGuests((g) => Math.max(1, g - 1)); }}>−</button>
                <b aria-live="polite">{guests}</b>
                <button type="button" aria-label="Больше гостей" disabled={guests >= 8} onClick={() => { setTouched(true); setGuests((g) => Math.min(8, g + 1)); }}>+</button>
              </span>
            </span>
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
        <AgentStatus health={health} mode={mode} setMode={setMode} />
        {error && <div className="toast error" role="alert"><Icon name="alert" size={17} /> <span>{error}</span></div>}
      </footer>
    </div>
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
      {!compact && (
        <details>
          <summary>Источники данных</summary>
          <ul>{Object.entries(health.integrations).map(([k, v]) => <li key={k}><b>{k}</b>: {v}</li>)}</ul>
        </details>
      )}
    </div>
  );
}
