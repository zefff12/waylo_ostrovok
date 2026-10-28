import { useEffect, useMemo, useState } from "react";
import type { SavedGuest } from "../types";
import { Icon } from "./Icons";

export type GuestDraft = { last: string; first: string; middle: string; birth: string; doc: string };
export type GuestOut = { full_name: string; birth_date: string; document: string; child: boolean };

type DocKind = { label: string; placeholder: string; rx: RegExp; hint: string; format: (v: string) => string };

export const PASSPORT: DocKind = {
  label: "Паспорт РФ", placeholder: "1234 567890", rx: /^\d{4} \d{6}$/, hint: "Серия и номер: 10 цифр",
  format: (v) => { const d = v.replace(/\D/g, "").slice(0, 10); return d.length > 4 ? `${d.slice(0, 4)} ${d.slice(4)}` : d; },
};
export const BIRTH: DocKind = {
  label: "Свидетельство о рождении", placeholder: "IV-МЮ 123456", rx: /^[IVXLC]{1,4}-[А-ЯЁ]{2} \d{6}$/,
  hint: "Римские цифры, две буквы и 6 цифр: IV-МЮ 123456",
  format: (v) => v.toUpperCase().replace(/[^IVXLCА-ЯЁ0-9\- ]/g, "").slice(0, 14),
};
export const DOC_KINDS = [PASSPORT, BIRTH];
export const NAME_RX = /^[А-ЯЁA-Z][а-яёa-z'-]+(?:[ -][А-ЯЁA-Z][а-яёa-z'-]+)*$/;

const EMPTY: GuestDraft = { last: "", first: "", middle: "", birth: "", doc: "" };

export function ageAt(birth: string, at: string): number {
  const b = new Date(birth + "T00:00"), d = new Date(at + "T00:00");
  let a = d.getFullYear() - b.getFullYear();
  if (d.getMonth() < b.getMonth() || (d.getMonth() === b.getMonth() && d.getDate() < b.getDate())) a--;
  return a;
}

export function docFor(birth: string, at: string, child = false): DocKind {
  if (!birth) return child ? BIRTH : PASSPORT;
  return ageAt(birth, at) < 14 ? BIRTH : PASSPORT;
}

const docKind = (g: GuestDraft, tripStart: string, child: boolean) => docFor(g.birth, tripStart, child);

export function GuestsForm({ adults, kids, tripStart, saved, onValid }: {
  adults: number; kids: number; tripStart: string; saved: SavedGuest[];
  onValid: (g: GuestOut[] | null, drafts: (GuestDraft & { doc_kind: string })[], remember: boolean) => void;
}) {
  const total = adults + kids;
  const [guests, setGuests] = useState<GuestDraft[]>(() => Array.from({ length: total }, () => ({ ...EMPTY })));
  const [remember, setRemember] = useState(true);
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const errorsOf = (g: GuestDraft, i: number) => {
    const e: Partial<Record<keyof GuestDraft, string>> = {};
    if (!NAME_RX.test(g.last.trim())) e.last = "Фамилия как в документе";
    if (!NAME_RX.test(g.first.trim())) e.first = "Имя как в документе";
    if (g.middle.trim() && !NAME_RX.test(g.middle.trim())) e.middle = "Проверьте отчество";
    const child = i >= adults;
    if (!g.birth) e.birth = "Укажите дату рождения";
    else {
      const age = ageAt(g.birth, tripStart);
      if (age < 0 || new Date(g.birth) > new Date()) e.birth = "Дата рождения в будущем";
      else if (!child && age < 18) e.birth = "Взрослому на момент поездки должно быть 18+";
      else if (child && age >= 18) e.birth = "Ребёнку на момент поездки должно быть меньше 18";
    }
    const k = docKind(g, tripStart, child);
    if (!k.rx.test(g.doc.trim())) e.doc = k.hint;
    return e;
  };

  useEffect(() => {
    const ok = guests.every((g, i) => Object.keys(errorsOf(g, i)).length === 0);
    const drafts = guests.map((g, i) => ({ ...g, doc_kind: docKind(g, tripStart, i >= adults).label }));
    onValid(ok ? guests.map((g, i) => ({
      full_name: [g.last, g.first, g.middle].map((x) => x.trim()).filter(Boolean).join(" "),
      birth_date: g.birth, child: i >= adults,
      document: `${drafts[i].doc_kind} •••• ${g.doc.replace(/\s/g, "").slice(-4)}`,
    })) : null, drafts, remember);
  }, [guests, remember, tripStart]);

  const set = (i: number, k: keyof GuestDraft, v: string) =>
    setGuests((gs) => gs.map((g, j) => (j === i ? { ...g, [k]: v } : g)));
  const show = (i: number, k: string) => touched[`${i}.${k}`];
  const touch = (i: number, k: string) => setTouched((t) => ({ ...t, [`${i}.${k}`]: true }));

  const pick = (i: number, s: SavedGuest) => {
    const g = { last: s.last, first: s.first, middle: s.middle, birth: s.birth, doc: "" };
    const need = docKind(g, tripStart, i >= adults);
    g.doc = s.doc_kind === need.label ? s.doc : "";
    setGuests((gs) => gs.map((x, j) => (j === i ? g : x)));
    setTouched((t) => ({ ...t, ...Object.fromEntries(["last", "first", "middle", "birth", "doc"].map((k) => [`${i}.${k}`, true])) }));
  };
  const used = useMemo(() => new Set(guests.map((g) => `${g.last}|${g.first}|${g.birth}`)), [guests]);

  return (
    <div className="guests">
      {guests.map((g, i) => {
        const e = errorsOf(g, i);
        const k = docKind(g, tripStart, i >= adults);
        const options = saved.filter((s) => !used.has(`${s.last}|${s.first}|${s.birth}`)
          && (ageAt(s.birth, tripStart) >= 18) === (i < adults));
        const field = (key: keyof GuestDraft, label: string, extra: Record<string, unknown> = {}) => (
          <label className={`field ${show(i, key) && e[key] ? "invalid" : ""}`}>
            <span>{label}</span>
            <input value={g[key]} autoComplete="off" onBlur={() => touch(i, key)}
              onChange={(ev) => set(i, key, key === "doc" ? k.format(ev.target.value) : ev.target.value)} {...extra} />
            {show(i, key) && e[key] && <small className="form-error">{e[key]}</small>}
          </label>
        );
        return (
          <fieldset key={i} className="guest">
            <legend><Icon name="user" size={16} /> {i < adults ? `Взрослый ${i + 1}` : `Ребёнок ${i - adults + 1}`}</legend>
            {options.length > 0 && (
              <div className="saved-pick" role="group" aria-label="Сохранённые гости">
                <small className="muted">Из профиля:</small>
                {options.map((s) => (
                  <button key={s.id} type="button" className="chip" onClick={() => pick(i, s)}>
                    {s.last} {s.first}<span className="muted"> · {new Date(s.birth + "T00:00").toLocaleDateString("ru-RU")}</span>
                  </button>
                ))}
              </div>
            )}
            <div className="guest-grid">
              {field("last", "Фамилия", { placeholder: "Иванова", maxLength: 40 })}
              {field("first", "Имя", { placeholder: "Анна", maxLength: 40 })}
              {field("middle", "Отчество, если есть", { placeholder: "Сергеевна", maxLength: 40 })}
              {field("birth", "Дата рождения", { type: "date", max: new Date().toISOString().slice(0, 10) })}
            </div>
            <div className="guest-doc">
              {field("doc", k.label, { placeholder: k.placeholder, maxLength: 14, inputMode: k === BIRTH ? "text" : "numeric" })}
              <small className="muted">
                {i >= adults ? "До 14 лет — свидетельство о рождении, с 14 лет — паспорт РФ. Тип подберётся по дате рождения."
                  : "Паспорт гражданина РФ."}
              </small>
            </div>
          </fieldset>
        );
      })}
      <label className="agree">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        <span>Сохранить гостей в профиль — в следующий раз их можно будет подставить одним нажатием.</span>
      </label>
    </div>
  );
}
