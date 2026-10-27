import { useState } from "react";
import type { Trip } from "../types";
import { rub } from "../api";
import { KindBadge, SectionTitle } from "./TripTab";
import { Icon } from "./Icons";

export function CheckoutTab({ trip, busy, onCheckout, onExtra }: {
  trip: Trip; busy: boolean; onCheckout: (name: string) => void; onExtra: (kind: string) => void;
}) {
  const [name, setName] = useState("");
  const [agree, setAgree] = useState(false);
  const [tried, setTried] = useState(false);
  if (!trip.days.length) return <section className="state card-solid"><Icon name="bag" size={26} /><b>Корзина пуста</b><span className="muted">Сначала соберите поездку — затем её можно оформить.</span></section>;
  const crit = trip.connections.filter((c) => c.level === "critical");
  const warn = trip.connections.filter((c) => c.level === "warning");
  const b = trip.budget;

  if (trip.order) {
    const o = trip.order;
    return (
      <section className="screen checkout">
        <div className="card-solid done">
          <span className="done-icon"><Icon name="check" size={26} /></span>
          <span className="eyebrow-dark">Демо-заказ оформлен</span>
          <h2>{o.order_id}</h2>
          <p className="muted">{o.status}</p>
          <ul className="order-lines">{o.lines.map((l) => <li key={l}><Icon name="check" size={15} /> {l}</li>)}</ul>
          <div className="stat-big">{rub(b.total)}<small>реальной оплаты не было</small></div>
        </div>
        <SectionTitle icon="spark" title="После покупки" hint="Агент может отправить запросы по купленной поездке (демо, никуда не уходит)." />
        <div className="card-solid">
          <div className="day-actions">
            <button className="btn" disabled={busy} onClick={() => onExtra("early_checkin")}><Icon name="hotel" size={16} /> Запросить ранний заезд</button>
            <button className="btn" disabled={busy} onClick={() => onExtra("transfer")}><Icon name="route" size={16} /> Заказать трансфер к отелю</button>
          </div>
          {o.post_purchase.length > 0 && <ul className="order-lines">{o.post_purchase.map((x) => <li key={x}><Icon name="check" size={15} /> {x}</li>)}</ul>}
        </div>
      </section>
    );
  }

  const submit = () => {
    setTried(true);
    if (!agree || crit.length) return;
    onCheckout(name.trim() || "Гость Waylo");
  };

  return (
    <section className="screen checkout">
      <div className="demo-banner"><Icon name="info" size={17} /> Демо-оформление: реальной оплаты и бронирования не будет, платёжные данные не запрашиваются.</div>

      <SectionTitle icon="check" title="1. Проверка поездки" hint="Агент сверил прибытие, заселение, трансфер и выезд." />
      <div className={`card-solid checks ${crit.length ? "critical" : ""}`}>
        {crit.length === 0 && warn.length === 0 && <div className="check ok"><span className="level ok">Готово</span><div>Состыковки в порядке</div></div>}
        {[...crit, ...warn].map((c) => (
          <div key={c.code} className={`check ${c.level}`}>
            <span className={`level ${c.level}`}>{c.level === "critical" ? "Критично" : "Важно"}</span>
            <div>{c.text}{c.fix && <div className="fix">{c.fix}</div>}</div>
          </div>
        ))}
      </div>

      <SectionTitle icon="bag" title="2. Корзина" hint="Итоговая стоимость и тип каждой цены." />
      <div className="card-solid">
        <table className="budget">
          <tbody>
            {b.items.map((i) => (
              <tr key={i.id}><td>{i.title}</td><td><KindBadge kind={i.kind} source={i.source} /></td><td className="num">{rub(i.amount)}</td></tr>
            ))}
            <tr className="sum"><td>Итого</td><td /><td className="num">{rub(b.total)}</td></tr>
          </tbody>
        </table>
        {b.over_by > 0 && <p className="form-warn"><Icon name="alert" size={15} /> Выше бюджета на {rub(b.over_by)}. Оформить можно, но агент советует сэкономить — напишите в чат «сделай дешевле».</p>}
      </div>

      <SectionTitle icon="user" title="3. Данные для брони" />
      <div className="card-solid form">
        <label className="field">
          <span>Имя гостя</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Например: Алекс" maxLength={60} autoComplete="off" />
          <small className="muted">Можно вымышленное. Если оставить пустым — «Гость Waylo».</small>
        </label>
        <label className={`agree ${tried && !agree ? "invalid" : ""}`}>
          <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
          <span>Понимаю, что это демонстрация и оплата не списывается</span>
        </label>
        {tried && !agree && <p className="form-error">Отметьте согласие, чтобы продолжить.</p>}
        {crit.length > 0 && <p className="form-error">Сначала исправьте критичные проблемы в шаге 1 — например, попросите агента в чате.</p>}
        <button className="btn primary big-btn" disabled={busy || crit.length > 0} onClick={submit}>
          {busy ? "Оформляем…" : `Оформить демо-заказ · ${rub(b.total)}`}
        </button>
      </div>
    </section>
  );
}
