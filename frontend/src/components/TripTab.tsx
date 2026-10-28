import type { Explanation, Trip } from "../types";
import { fmtDT, KIND_LABEL, rub } from "../api";
import { HotelList } from "./HotelList";
import { Icon, type IconName } from "./Icons";

export function KindBadge({ kind, source }: { kind: string; source?: string }) {
  return <span className={`badge k-${kind}`} title={source}>{KIND_LABEL[kind] ?? kind}</span>;
}

export function Why({ e }: { e: Explanation }) {
  return (
    <div className="why">
      {e.why.length > 0 && <div><b>Почему:</b> {e.why.join("; ")}</div>}
      {e.tradeoffs.length > 0 && <div><b>Чем жертвуем:</b> {e.tradeoffs.join("; ")}</div>}
      {e.risks.length > 0 && <div className="risk"><b>Риски:</b> {e.risks.join("; ")}</div>}
    </div>
  );
}

/** Заголовок раздела: подложка из стекла, чтобы надпись читалась на любом кадре видео. */
export function SectionTitle({ icon, title, hint }: { icon: IconName; title: string; hint?: string }) {
  return (
    <div className="section-title">
      <span className="gicon gicon-sm as-icon"><Icon name={icon} size={16} /></span>
      <div><h3>{title}</h3>{hint && <p>{hint}</p>}</div>
    </div>
  );
}

export function TripTab({ trip, busy, city, onDestination, onTransport, onHotel, onSend }: {
  trip: Trip; busy: boolean; city: string;
  onDestination: (city: string) => void; onTransport: (id: string) => void; onHotel: (id: string) => void;
  onSend: (text: string) => void;
}) {
  if (trip.status === "choose_destination" || (!trip.days.length && trip.destination_options.length)) {
    return (
      <section className="screen">
        <SectionTitle icon="pin" title="Куда поехать" hint="Город не указан — агент подобрал направления. Климат — архив Open-Meteo, стоимость — оценка." />
        <div className="cards3">
          {trip.destination_options.map((o, i) => (
            <article key={o.city_id} className="card-solid dest" style={{ animationDelay: `${i * 50}ms` }}>
              <div className="dest-top"><h4>{o.name}</h4><span className="muted">{o.country}</span></div>
              <div className="stat-big">~{rub(o.est_total_rub)}<small>за поездку, оценка</small></div>
              <div className="facts">
                <span><Icon name={o.travel_mode === "поезд" ? "train" : "plane"} size={15} /> {o.travel_hours} ч, {o.travel_mode}</span>
                {o.climate?.tmax != null && <span title={o.climate.source}><Icon name="sun" size={15} /> днём {o.climate.tmax > 0 ? "+" : ""}{Math.round(o.climate.tmax)}°C</span>}
                {o.climate && <span><Icon name="wave" size={15} /> {o.climate.rainy_days} дожд. дн.</span>}
              </div>
              <Why e={o.explanation} />
              <button className="btn primary" disabled={busy} onClick={() => onDestination(o.city_id)}>Выбрать {o.name}</button>
            </article>
          ))}
        </div>
      </section>
    );
  }
  if (trip.budget_gap) return <NotFound gap={trip.budget_gap} city={city} busy={busy} onSend={onSend} />;
  if (!trip.days.length) return <section className="state card-solid"><Icon name="chat" size={26} /><b>План ещё не собран</b><span className="muted">Уточните запрос в чате — агент соберёт поездку.</span></section>;

  const t = trip.transport_options.find((o) => o.id === trip.selected_transport_id);
  const h = trip.hotel_options.find((o) => o.id === trip.selected_hotel_id);
  const p = trip.params;
  const start = new Date(p.start_date + "T00:00");
  const end = new Date(start.getTime() + (p.nights ?? 0) * 864e5);
  const issues = trip.connections.filter((c) => c.level !== "ok");
  const fmt = (d: Date) => d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  const b = trip.budget;

  return (
    <section className="screen trip">
      <div className="hero card-solid">
        <div className="hero-main">
          <span className="eyebrow-dark">Ваша поездка</span>
          <h2>{city || "—"}</h2>
          <div className="facts">
            <span><Icon name="calendar" size={15} /> {fmt(start)} – {fmt(end)}</span>
            <span><Icon name="guests" size={15} /> {p.adults} взр.{p.children ? ` + ${p.children} реб.` : ""}{p.pets ? " + питомец" : ""}</span>
            {t && <span><Icon name={t.mode === "train" ? "train" : "plane"} size={15} /> {t.mode === "train" ? "поезд" : "самолёт"}</span>}
            {h && <span><Icon name="hotel" size={15} /> {h.name}</span>}
          </div>
        </div>
        <div className="hero-stats">
          <div className="stat"><small>Ночей</small><b>{p.nights}</b></div>
          <div className="stat"><small>Дней прогулок</small><b>{trip.days.length}</b></div>
          <div className={`stat total ${b.over_by ? "over" : ""}`}>
            <small>Итого</small><b>{rub(b.total)}</b>
            <span>{b.limit ? (b.over_by ? `выше бюджета на ${rub(b.over_by)}` : `запас ${rub(b.limit - b.total)}`) : "лимит не задан"}</span>
          </div>
        </div>
        {p.assumptions.length > 0 && <div className="assume"><Icon name="info" size={15} /> <span><b>Допущения:</b> {p.assumptions.join(" · ")}</span></div>}
      </div>

      {issues.length > 0 && (
        <div className={`card-solid checks ${issues.some((c) => c.level === "critical") ? "critical" : ""}`}>
          <h4 className="with-ic"><Icon name="alert" size={18} /> Проверка состыковок</h4>
          {issues.map((c) => (
            <div key={c.code} className={`check ${c.level}`}>
              <span className={`level ${c.level}`}>{c.level === "critical" ? "Критично" : "Важно"}</span>
              <div>{c.text}{c.fix && <div className="fix">{c.fix}</div>}</div>
            </div>
          ))}
        </div>
      )}

      <SectionTitle icon="route" title="Дорога туда и обратно" hint="Сравнение по цене и времени от двери до двери." />
      <div className="cards2">
        {trip.transport_options.map((o, i) => (
          <article key={o.id} className={`card-solid opt ${o.id === t?.id ? "sel" : ""}`} style={{ animationDelay: `${i * 50}ms` }}>
            <div className="opt-head">
              <b className="with-ic"><Icon name={o.mode === "train" ? "train" : "plane"} size={18} /> {o.title}</b>
              <KindBadge kind={o.kind} source={o.source} />
            </div>
            <div className="legs">
              <div><span className="leg-k">Туда</span> {fmtDT(o.outbound.depart)} — {fmtDT(o.outbound.arrive)} · {Math.round(o.outbound.duration_min / 6) / 10} ч</div>
              <div><span className="leg-k">Обратно</span> {fmtDT(o.inbound.depart)} — {fmtDT(o.inbound.arrive)}</div>
              <div className="muted">{o.outbound.from_name} — {o.outbound.to_name} · от двери до двери ~{o.door_to_door_hours} ч{o.pets_allowed ? " · можно с животными" : ""}</div>
            </div>
            <div className="price-row">
              <span className="price-main">{rub(o.price_total)}</span>
              <span className="muted">{rub(o.price_per_person)} / чел.</span>
              {o.id === t?.id ? <span className="badge sel-badge"><Icon name="check" size={13} /> выбрано</span>
                : <button className="btn" disabled={busy} onClick={() => onTransport(o.id)}>Выбрать</button>}
            </div>
            <Why e={o.explanation} />
          </article>
        ))}
      </div>

      <HotelList hotels={trip.hotel_options} selectedId={trip.selected_hotel_id} busy={busy} onSelect={onHotel}
        pets={p.pets} kids={p.children > 0} />
      {h && <div className="card-solid note-card"><Icon name="hotel" size={18} /><div><b>{h.name}</b> — заезд с {h.checkin}, выезд до {h.checkout}. {h.cancellation_text}.</div></div>}

      <SectionTitle icon="wallet" title="Бюджет" hint="Каждая статья посчитана кодом. Наведите на бейдж, чтобы увидеть источник." />
      <div className="card-solid">
        <BudgetBar trip={trip} />
        <table className="budget">
          <tbody>
            {b.items.map((i) => (
              <tr key={i.id}>
                <td><i className="cat-dot" style={{ background: CAT_COLORS[i.category] }} />{i.title}{i.note && <div className="muted small">{i.note}</div>}</td>
                <td><KindBadge kind={i.kind} source={i.source} /></td>
                <td className="num">{rub(i.amount)}</td>
              </tr>
            ))}
            <tr className="sum"><td>Итого</td><td /><td className="num">{rub(b.total)}</td></tr>
          </tbody>
        </table>
        {b.over_by > 0 && (
          <div className="savings"><b>Как уложиться в бюджет</b><ul>{b.savings.map((s) => <li key={s}>{s}</li>)}</ul></div>
        )}
      </div>

      {trip.changes.length > 0 && (
        <>
          <SectionTitle icon="sort" title="История изменений" hint="Что агент поменял по вашим правкам." />
          <div className="card-solid changes">
            {trip.changes.slice().reverse().map((c, i) => (
              <div key={i} className="change"><span className="change-time">{c.at}</span><div><b>{c.summary}</b><ul>{c.details.map((d) => <li key={d}>{d}</li>)}</ul></div></div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

const CAT_COLORS: Record<string, string> = {
  transport: "#0645F5", hotel: "#27C8F5", transfer: "#7B61FF", food: "#00A86B", tickets: "#FF8A00", local_transport: "#9AA6C1", extras: "#E5484D",
};

function BudgetBar({ trip }: { trip: Trip }) {
  const max = Math.max(trip.budget.total, trip.budget.limit ?? 0);
  return (
    <div className="bbar">
      {trip.budget.items.map((i) => (
        <i key={i.id} title={`${i.title}: ${rub(i.amount)}`} style={{ width: `${(i.amount / max) * 100}%`, background: CAT_COLORS[i.category] }} />
      ))}
      {trip.budget.limit && <b className="limit" style={{ left: `${(trip.budget.limit / max) * 100}%` }} title="Лимит" />}
    </div>
  );
}


/** В бюджет не поместился ни один вариант: план не показываем, предлагаем, что поменять. */
function NotFound({ gap, city, busy, onSend }: {
  gap: NonNullable<Trip["budget_gap"]>; city: string; busy: boolean; onSend: (text: string) => void;
}) {
  const up = Math.ceil(gap.min_total / 1000) * 1000;
  return (
    <section className="state card-solid not-found">
      <span className="gicon gicon-md as-icon"><Icon name="search" size={19} /></span>
      <h2>С бюджетом {rub(gap.limit)} ничего не найдено</h2>
      <p className="muted">Самый дешёвый вариант поездки{city ? ` в направлении «${city}»` : ""} — дорога, отель, питание и билеты — стоит {rub(gap.min_total)},
        на {rub(gap.over_by)} больше бюджета.</p>
      <div className="clarify-actions">
        <button className="btn primary" disabled={busy} onClick={() => onSend(`бюджет ${up}`)}>Увеличить бюджет до {rub(up)}</button>
        {gap.fewer_nights && (
          <button className="btn" disabled={busy} onClick={() => onSend(`сократи поездку до ${gap.fewer_nights!.nights} ночей`)}>
            Сократить до {gap.fewer_nights.nights} ноч. · около {rub(gap.fewer_nights.total)}
          </button>
        )}
        <button className="btn" disabled={busy} onClick={() => onSend("бюджет не ограничен")}>Без ограничения бюджета</button>
      </div>
      <small className="muted">Можно и по-другому: напишите агенту другие даты или город.</small>
    </section>
  );
}
