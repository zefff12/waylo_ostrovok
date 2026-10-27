import { Fragment, type ReactNode } from "react";

/** Мини-рендер ответов агента: **жирный**, _курсив_, списки «• / - / 1.». Без HTML — безопасно. */
function inline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.length > 2 && p.startsWith("_") && p.endsWith("_")) return <em key={i} className="muted">{p.slice(1, -1)}</em>;
    return <Fragment key={i}>{p}</Fragment>;
  });
}

// старые сообщения в истории могли содержать эмодзи — в интерфейсе их не показываем
const EMOJI = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{23E9}-\u{23FA}\u{FE0F}\u{200D}\u{20E3}]/gu;
const KEYCAP = /([0-9#*])\u{FE0F}?\u{20E3}/gu;  // «1️⃣» → «1. »

export function Markdown({ text }: { text: string }) {
  const lines = text.replace(KEYCAP, "$1. ").replace(EMOJI, "").split("\n");
  const out: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = () => {
    if (list.length) out.push(<ul key={`ul${out.length}`}>{list}</ul>);
    list = [];
  };
  lines.forEach((raw, i) => {
    const line = raw.trimEnd();
    const m = line.match(/^\s*(?:[•\-*]|\d+\.)\s+(.*)$/);
    if (m && !line.startsWith("**")) {
      list.push(<li key={i}>{inline(m[1])}</li>);
      return;
    }
    flush();
    if (line.trim()) out.push(<p key={i}>{inline(line)}</p>);
  });
  flush();
  return <div className="md">{out}</div>;
}
