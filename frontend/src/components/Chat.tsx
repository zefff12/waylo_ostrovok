import { useEffect, useRef, useState } from "react";
import type { ChatMsg, Trip } from "../types";
import { Markdown } from "./Markdown";
import { GlassIcon, Icon } from "./Icons";

const QUICK_READY = [
  "Сделай дешевле",
  "На второй день хочу меньше ходить и заменить одну достопримечательность на кафе",
  "Начался дождь",
  "Добавь музей на третий день",
  "А если на два дня позже?",
  "С нами едет собака",
];

export function Chat({ chat, trip, busy, onSend, onClose }: {
  chat: ChatMsg[]; trip: Trip | null; busy: boolean; onSend: (text: string) => void; onClose?: () => void;
}) {
  const [text, setText] = useState("");
  const [showLog, setShowLog] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [chat.length, busy]);

  const send = (t: string) => {
    if (!t.trim() || busy) return;
    onSend(t.trim());
    setText("");
  };

  return (
    <aside className="chat glass-modal" aria-label="Чат с агентом">
      <div className="chat-head">
        <span className="chat-title"><span className="gicon gicon-sm as-icon"><Icon name="spark" size={15} /></span> ИИ-помощник</span>
        <span className="chat-head-actions">
          {trip && trip.tool_log.length > 0 && (
            <button className="link" onClick={() => setShowLog((v) => !v)}>
              {showLog ? "Скрыть" : "Что сделал агент"} ({trip.tool_log.length})
            </button>
          )}
          {onClose && <GlassIcon name="close" label="Свернуть чат" size="sm" className="chat-close" onClick={onClose} />}
        </span>
      </div>
      {showLog && trip && (
        <ol className="toollog">
          {trip.tool_log.slice().reverse().map((e, i) => (
            <li key={i} className={e.ok ? "" : "bad"}><code>{e.tool}</code> {e.summary}</li>
          ))}
        </ol>
      )}
      <div className="msgs">
        {chat.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" ? <Markdown text={m.text} /> : <p>{m.text}</p>}
            <span className="meta">{m.at}{m.agent && m.role === "assistant" ? ` · ${agentLabel(m.agent)}` : ""}</span>
          </div>
        ))}
        {busy && <div className="msg assistant typing"><span /><span /><span /> Агент ищет и считает…</div>}
        <div ref={end} />
      </div>
      {trip?.days.length ? (
        <div className="chips">
          {QUICK_READY.map((q) => <button key={q} className="chip" disabled={busy} onClick={() => send(q)}>{q}</button>)}
        </div>
      ) : null}
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <textarea
          value={text}
          placeholder="Например: «сделай дешевле» или «замени Эрмитаж на кафе»"
          aria-label="Сообщение агенту"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
          rows={2}
        />
        <button className="send" disabled={busy || !text.trim()} aria-label="Отправить"><Icon name="send" size={19} /></button>
      </form>
    </aside>
  );
}

function agentLabel(a: string) {
  return { claude: "Claude", gigachat: "GigaChat", offline: "офлайн-агент", "offline-fallback": "офлайн (резерв)", ui: "интерфейс" }[a] ?? a;
}
