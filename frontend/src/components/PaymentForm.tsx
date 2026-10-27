import { useEffect, useRef, useState } from "react";
import { rub } from "../api";
import { Icon } from "./Icons";

/**
 * Демо-оплата картой. Выглядит и проверяет поля как настоящая форма, но номер карты
 * не покидает браузер: наружу уходит только «Visa •••• 4242». Деньги не списываются.
 */
const TEST_CARD = "4242 4242 4242 4242";

function brand(digits: string): string {
  if (/^4/.test(digits)) return "Visa";
  if (/^(5[1-5]|2[2-7])/.test(digits) && !/^220[0-4]/.test(digits)) return "Mastercard";
  if (/^220[0-4]/.test(digits)) return "МИР";
  return "Карта";
}

function luhn(digits: string): boolean {
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    let d = +digits[digits.length - 1 - i];
    if (i % 2) { d *= 2; if (d > 9) d -= 9; }
    sum += d;
  }
  return digits.length >= 16 && sum % 10 === 0;
}

function expiryOk(v: string): boolean {
  const m = v.match(/^(\d{2})\/(\d{2})$/);
  if (!m || +m[1] < 1 || +m[1] > 12) return false;
  const end = new Date(2000 + +m[2], +m[1], 1);  // карта действует до конца месяца
  return end > new Date();
}

type Errors = Partial<Record<"number" | "exp" | "cvc" | "holder", string>>;

export function PaymentForm({ amount, busy, label, onPaid }: {
  amount: number; busy: boolean; label: string; onPaid: (card: string) => void;
}) {
  const [number, setNumber] = useState("");
  const [exp, setExp] = useState("");
  const [cvc, setCvc] = useState("");
  const [holder, setHolder] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [stage, setStage] = useState<"form" | "processing">("form");
  const timer = useRef<number>();
  useEffect(() => () => clearTimeout(timer.current), []);

  const digits = number.replace(/\D/g, "");
  const kind = brand(digits);

  const validate = (): Errors => {
    const e: Errors = {};
    if (!luhn(digits)) e.number = "Проверьте номер карты — 16 цифр";
    if (!expiryOk(exp)) e.exp = "Укажите срок ММ/ГГ, карта не должна быть просрочена";
    if (!/^\d{3}$/.test(cvc)) e.cvc = "3 цифры с обратной стороны";
    if (holder.trim().length < 2) e.holder = "Как на карте, латиницей";
    return e;
  };

  const pay = () => {
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) return;
    setStage("processing");
    // имитация подтверждения банком; номер дальше этой формы не передаётся
    timer.current = window.setTimeout(() => { setStage("form"); onPaid(`${kind} •••• ${digits.slice(-4)}`); }, 1400);
  };

  const useTest = () => {
    const d = new Date(); const yy = String((d.getFullYear() + 3) % 100).padStart(2, "0");
    setNumber(TEST_CARD); setExp(`12/${yy}`); setCvc("123"); if (!holder) setHolder("WAYLO GUEST"); setErrors({});
  };

  if (stage === "processing" || busy) {
    return (
      <div className="pay-processing" role="status">
        <div className="spinner" />
        <b>Подтверждаем оплату {rub(amount)}</b>
        <span className="muted">Демо: банк не вызывается, деньги не списываются.</span>
      </div>
    );
  }

  return (
    <form className="pay" onSubmit={(e) => { e.preventDefault(); pay(); }} noValidate>
      <div className={`pay-card ${kind === "Карта" ? "" : "known"}`} aria-hidden="true">
        <div className="pay-card-top"><Icon name="card" size={22} /><b>{digits ? kind : "Банковская карта"}</b></div>
        <div className="pay-card-num">{(number || "•••• •••• •••• ••••")}</div>
        <div className="pay-card-bottom"><span>{holder.toUpperCase() || "ИМЯ ВЛАДЕЛЬЦА"}</span><span>{exp || "ММ/ГГ"}</span></div>
      </div>

      <label className={`field ${errors.number ? "invalid" : ""}`}>
        <span>Номер карты</span>
        <input inputMode="numeric" autoComplete="off" placeholder="0000 0000 0000 0000" value={number} maxLength={19}
          onChange={(e) => setNumber(e.target.value.replace(/\D/g, "").slice(0, 16).replace(/(\d{4})(?=\d)/g, "$1 "))} />
        {errors.number && <small className="form-error">{errors.number}</small>}
      </label>
      <div className="pay-row">
        <label className={`field ${errors.exp ? "invalid" : ""}`}>
          <span>Срок действия</span>
          <input inputMode="numeric" autoComplete="off" placeholder="ММ/ГГ" value={exp} maxLength={5}
            onChange={(e) => { const d = e.target.value.replace(/\D/g, "").slice(0, 4); setExp(d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d); }} />
          {errors.exp && <small className="form-error">{errors.exp}</small>}
        </label>
        <label className={`field ${errors.cvc ? "invalid" : ""}`}>
          <span>CVC</span>
          <input inputMode="numeric" autoComplete="off" type="password" placeholder="•••" value={cvc} maxLength={3}
            onChange={(e) => setCvc(e.target.value.replace(/\D/g, "").slice(0, 3))} />
          {errors.cvc && <small className="form-error">{errors.cvc}</small>}
        </label>
      </div>
      <label className={`field ${errors.holder ? "invalid" : ""}`}>
        <span>Владелец карты</span>
        <input autoComplete="off" placeholder="IVAN IVANOV" value={holder} maxLength={40}
          onChange={(e) => setHolder(e.target.value.replace(/[^a-zA-Z\s-]/g, ""))} />
        {errors.holder && <small className="form-error">{errors.holder}</small>}
      </label>

      <p className="pay-note"><Icon name="lock" size={15} />
        <span>Демо-оплата: не вводите настоящую карту. Номер проверяется только в браузере и никуда не отправляется.{" "}
          <button type="button" className="link" onClick={useTest}>Подставить тестовую карту</button></span></p>
      <button className="btn primary big-btn"><Icon name="lock" size={16} /> {label} · {rub(amount)}</button>
    </form>
  );
}
