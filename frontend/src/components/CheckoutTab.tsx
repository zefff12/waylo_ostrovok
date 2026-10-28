import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { ExtraOffer, Trip } from "../types";
import { rub } from "../api";
import { KindBadge, SectionTitle } from "./TripTab";
import { GlassIcon, Icon } from "./Icons";
import { PaymentForm } from "./PaymentForm";
import { GuestsForm, type GuestDraft, type GuestOut } from "./GuestsForm";
import type { Auth } from "../api";
import type { SavedGuest } from "../types";

export function CheckoutTab({ trip, busy, abroad, auth, saved, onLogin, onCheckout, onExtra }: {
  trip: Trip; busy: boolean; abroad: boolean; auth: Auth | null; saved: SavedGuest[]; onLogin: () => void;
  onCheckout: (guests: GuestOut[], card: string, toSave: (GuestDraft & { doc_kind: string })[]) => void;
  onExtra: (kind: string, card: string) => void;
}) {
  const [guests, setGuests] = useState<GuestOut[] | null>(null);
  const [drafts, setDrafts] = useState<{ list: (GuestDraft & { doc_kind: string })[]; remember: boolean }>({ list: [], remember: true });
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
          {o.guests?.length > 0 && <ul className="order-lines">{o.guests.map((g) => <li key={g.full_name + g.document}><Icon name="user" size={15} /> {g.full_name} · {g.document}</li>)}</ul>}
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

      {!auth ? (
        <>
          <SectionTitle icon="user" title="3. Профиль" hint="Оплатить поездку можно только из профиля — в нём сохранятся заказ и пассажиры." />
          <div className="card-solid login-gate">
            <span className="gicon gicon-md as-icon"><Icon name="user" size={19} /></span>
            <div><b>Войдите или зарегистрируйтесь</b><span className="muted">Это займёт минуту. Собранный план никуда не денется.</span></div>
            <button className="btn primary" onClick={onLogin}>Войти</button>
          </div>
        </>
      ) : (
        <>
          <SectionTitle icon="user" title="3. Путешественники" hint={`Данные всех ${trip.params.adults + trip.params.children} гостей — как в документах.`} />
          <div className="card-solid form">
            <GuestsForm adults={trip.params.adults} kids={trip.params.children} abroad={abroad} saved={saved}
              tripStart={trip.params.start_date ?? new Date().toISOString().slice(0, 10)}
              onValid={(g, list, remember) => { setGuests(g); setDrafts({ list, remember }); }} />
          </div>

          <SectionTitle icon="card" title="4. Оплата" hint="Данные банковской карты." />
          <div className="card-solid form">
            {crit.length > 0
              ? <p className="form-error">Оплата недоступна: сначала исправьте критичные проблемы в шаге 1 — например, попросите агента в чате.</p>
              : !guests
                ? <p className="form-warn"><Icon name="alert" size={15} /> Заполните данные всех путешественников в шаге 3 — после этого откроется оплата.</p>
                : <PaymentForm amount={b.total} busy={busy} label="Оплатить" onPaid={(card) => onCheckout(guests, card, drafts.remember ? drafts.list : [])} />}
          </div>
        </>
      )}
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
