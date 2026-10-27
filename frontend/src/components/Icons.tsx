import type { ButtonHTMLAttributes, ReactNode } from "react";

/* Единый набор линейных иконок: сетка 24, линия 1.7, скруглённые концы. */
const P: Record<string, ReactNode> = {
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
  hotel: <><path d="M3.5 20V8.5l8.5-4 8.5 4V20" /><path d="M8 20v-5h8v5M8 11h.01M12 11h.01M16 11h.01" /></>,
  heart: <path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.4 4.3 4.3 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10Z" />,
  filter: <><path d="M4 7h16M7 12h10M10 17h4" /></>,
  map: <><path d="m3.5 6.5 5.5-2 6 2 5.5-2v13l-5.5 2-6-2-5.5 2Z" /><path d="M9 4.5v13M15 6.5v13" /></>,
  user: <><circle cx="12" cy="8.5" r="3.8" /><path d="M4.5 20c1.2-3.6 4-5.2 7.5-5.2s6.3 1.6 7.5 5.2" /></>,
  back: <path d="M14.5 5.5 8 12l6.5 6.5" />,
  close: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  calendar: <><rect x="4" y="5.5" width="16" height="14.5" rx="3" /><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" /></>,
  guests: <><circle cx="9" cy="9" r="3.2" /><path d="M3.5 19c.9-3 3-4.4 5.5-4.4s4.6 1.4 5.5 4.4" /><path d="M15.5 6.2a3 3 0 0 1 0 5.6M17.5 14.9c1.6.6 2.6 1.9 3 4.1" /></>,
  pin: <><path d="M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11Z" /><circle cx="12" cy="10" r="2.4" /></>,
  sort: <><path d="M7 4.5v15M3.8 8 7 4.5 10.2 8M17 19.5v-15M13.8 16l3.2 3.5 3.2-3.5" /></>,
  send: <path d="M4.5 12 19.5 4.5 15 19.5l-3.2-6.3Z" />,
  train: <><rect x="6" y="3.5" width="12" height="13" rx="3.5" /><path d="M6 11h12M9 20l1.5-3.5M15 20l-1.5-3.5M9.5 14h.01M14.5 14h.01" /></>,
  plane: <path d="M20.5 15.5v-1.8l-7.5-4.6V4.5a1.5 1.5 0 0 0-3 0v4.6l-7.5 4.6v1.8l7.5-2.3v4.6l-2 1.5v1.4l3.5-1 3.5 1v-1.4l-2-1.5v-4.6Z" />,
  wallet: <><rect x="3.5" y="6" width="17" height="13" rx="3" /><path d="M3.5 10h17M15.5 14.5h2" /></>,
  route: <><circle cx="6" cy="18" r="2.2" /><circle cx="18" cy="6" r="2.2" /><path d="M8 18h7.5a3 3 0 0 0 0-6h-7a3 3 0 0 1 0-6H16" /></>,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  alert: <><path d="M12 4 21 19.5H3Z" /><path d="M12 10v4M12 17h.01" /></>,
  spark: <path d="M12 3.5 13.8 10.2 20.5 12l-6.7 1.8L12 20.5l-1.8-6.7L3.5 12l6.7-1.8Z" />,
  chat: <path d="M5 18.5V7a2.5 2.5 0 0 1 2.5-2.5h9A2.5 2.5 0 0 1 19 7v6.5a2.5 2.5 0 0 1-2.5 2.5H9Z" />,
  bag: <><path d="M5.5 8.5h13l-1 11h-11Z" /><path d="M9 8.5V7a3 3 0 0 1 6 0v1.5" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" /></>,
  wave: <path d="M3 9c3-2.5 6 2.5 9 0s6 2.5 9 0M3 15c3-2.5 6 2.5 9 0s6 2.5 9 0" />,
  mountain: <path d="m2.5 19.5 6.5-11 4 6.5 2.5-3.5 6 8Z" />,
  building: <><path d="M5 20.5V5l7-2v17.5M12 8.5l7 2.5v9.5M3 20.5h18" /><path d="M8 8h.01M8 12h.01M8 16h.01M15.5 14h.01M15.5 17h.01" /></>,
  museum: <><path d="M3.5 9 12 4l8.5 5M5 9v9M9.5 9v9M14.5 9v9M19 9v9M3 20h18" /></>,
  cup: <><path d="M5 9h11v5a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5Z" /><path d="M16 10.5h1.5a2.5 2.5 0 0 1 0 5H16M8.5 3.5c0 1.5 1.5 1.5 1.5 3M12 3.5c0 1.5 1.5 1.5 1.5 3" /></>,
  sound: <><path d="M4.5 9.5h3l4.5-4v13l-4.5-4h-3Z" /><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" /></>,
  pause: <path d="M9 6v12M15 6v12" />,
  info: <><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5.5M12 7.8h.01" /></>,
  star: <path d="m12 4 2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.6-4.8 2.6.9-5.4-3.9-3.8 5.4-.8Z" />,
  play: <path d="M8 5.5v13l10.5-6.5Z" />,
};

export type IconName = keyof typeof P;

export function Icon({ name, size = 20, className = "" }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg className={`ic ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{P[name]}</svg>
  );
}

/** Стеклянная иконка-кнопка: маленький объект из стекла с символом внутри. */
export function GlassIcon({ name, label, active, size = "md", className = "", ...rest }: {
  name: IconName; label: string; active?: boolean; size?: "sm" | "md" | "lg";
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type="button" aria-label={label} title={label} className={`gicon gicon-${size} ${active ? "on" : ""} ${className}`} {...rest}>
      <Icon name={name} size={size === "sm" ? 16 : size === "lg" ? 22 : 19} />
    </button>
  );
}
