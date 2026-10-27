import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { ExtraOffer, Trip } from "../types";
import { rub } from "../api";
import { KindBadge, SectionTitle } from "./TripTab";
import { GlassIcon, Icon } from "./Icons";
import { PaymentForm } from "./PaymentForm";

export function CheckoutTab({ trip, busy, onCheckout, onExtra }: {
  trip: Trip; busy: boolean; onCheckout: (name: string, card: string) => void; onExtra: (kind: string, card: string) => void;
}) {
  const [name, setName] = useState("");
  const [buying, setBuying] = useState<ExtraOffer | null>(null);
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
          <span className="eyebrow-dark">Заказ оплачен (демо)</span>
          <h2>{o.order_id}</h2>
          <p className="muted">{o.payment ? `Оплата картой ${o.payment}. ` : ""}Деньги не списаны, бронирований не создано.</p>
          <ul className="order-lines">{o.lines.map((l) => <li key={l}><Icon name="check" size={15} /> {l}</li>)}</ul>
          <div className="stat-big">{rub(b.total)}<small>итого по заказу, включая доп. услуги</small></div>
        </div>
        <SectionTitle icon="bag" title="Дополнительные услуги" hint="Цена известна заранее, каждая услуга оплачивается отдельно." />
        <div className="offers">
          {(o.offers ?? []).map((x) => (
            <article key={x.kind} className={`card-solid offer ${x.paid ? "paid" : ""}`}>
              <span className="gicon gicon-md as-icon"><Icon name={x.kind === "transfer" ? "route" : "hotel"} size={19} /></span>
              <div className="offer-body">
                <b>{x.title}</b>
                <span className="muted">{x.note}</span>
              </div>
              <div className="offer-side">
                <div className="offer-price">{rub(x.amount)}</div>
                {x.paid ? <span className="sel-badge"><Icon name="check" size={15} /> Оплачено</span>
                  : <button className="btn primary" disabled={busy} onClick={() => setBuying(x)}>Оформить</button>}
              </div>
            </article>
          ))}
        </div>
        {o.post_purchase.length > 0 && (
          <div className="card-solid"><ul className="order-lines">{o.post_purchase.map((x) => <li key={x}><Icon name="check" size={15} /> {x}</li>)}</ul></div>
        )}
        {buying && <PaySheet offer={buying} busy={busy} onClose={() => setBuying(null)}
          onPaid={(card) => { onExtra(buying.kind, card); setBuying(null); }} />}
      </section>
    );
  }

  return (
    <section className="screen checkout">
      <div className="demo-banner"><Icon name="info" size={17} /> Демо-оформление: оплата и бронь имитируются, деньги не списываются.</div>

      <SectionTitle icon="check" title="1. Проверка поездки" hint="Агент сверил прибытие, заселение, трансфер, выезд и бюджет." />
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
            {b.limit ? <tr><td className="muted">Ваш бюджет</td><td /><td className="num muted">{rub(b.limit)}</td></tr> : null}
          </tbody>
        </table>
      </div>

      <SectionTitle icon="card" title="3. Оплата" hint="Данные гостя и банковская карта." />
      <div className="card-solid form">
        <label className="field">
          <span>Имя гостя для брони</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Например: Алекс" maxLength={60} autoComplete="off" />
          <small className="muted">Можно вымышленное. Если оставить пустым — «Гость Waylo».</small>
        </label>
        {crit.length > 0
          ? <p className="form-error">Оплата недоступна: сначала исправьте критичные проблемы в шаге 1 — например, попросите агента в чате.</p>
          : <PaymentForm amount={b.total} busy={busy} label="Оплатить" onPaid={(card) => onCheckout(name.trim() || "Гость Waylo", card)} />}
      </div>
    </section>
  );
}

function PaySheet({ offer, busy, onClose, onPaid }: {
  offer: ExtraOffer; busy: boolean; onClose: () => void; onPaid: (card: string) => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(  // поверх шапки и чата, как фильтры отелей
    <div className="sheet-wrap" onClick={onClose}>
      <div className="sheet glass-modal" role="dialog" aria-modal="true" aria-label={`Оплата: ${offer.title}`} onClick={(e) => e.stopPropagation()}>
        <div className="sheet-grip" />
        <div className="sheet-head">
          <h3>{offer.title}</h3>
          <GlassIcon name="close" label="Закрыть" size="sm" onClick={onClose} />
        </div>
        <p className="muted sheet-note">{offer.note}</p>
        <PaymentForm amount={offer.amount} busy={busy} label="Оплатить" onPaid={onPaid} />
      </div>
    </div>,
    document.body,
  );
}
