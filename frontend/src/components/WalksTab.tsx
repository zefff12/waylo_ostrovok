import { useState } from "react";
import type { Trip } from "../types";
import { CAT_LABEL, fmtDate, rub } from "../api";
import { MapView } from "./MapView";
import { KindBadge } from "./TripTab";
import { Icon } from "./Icons";

export function WalksTab({ trip, busy, onDay }: {
  trip: Trip; busy: boolean; onDay: (day: number, action: string, extra?: { category?: string; place_id?: string }) => void;
}) {
  const [active, setActive] = useState<number | null>(1);
  const [focus, setFocus] = useState<string | null>(null);
  const hotel = trip.hotel_options.find((h) => h.id === trip.selected_hotel_id) ?? null;
  if (!trip.days.length) return <section className="state card-solid"><Icon name="map" size={26} /><b>Прогулок пока нет</b><span className="muted">Они появятся, когда агент соберёт поездку.</span></section>;
  const days = active === null ? trip.days : trip.days.filter((d) => d.day === active);

  return (
    <section className="screen walks">
      <div className="daytabs" role="tablist" aria-label="Дни поездки">
        <button className={active === null ? "on" : ""} onClick={() => setActive(null)}>Все дни</button>
        {trip.days.map((d) => (
          <button key={d.day} className={active === d.day ? "on" : ""} onClick={() => setActive(d.day)}>День {d.day}</button>
        ))}
      </div>
      <div className="walks-grid">
        <MapView days={trip.days} hotel={hotel} activeDay={active}
          onSelectStop={(day, i) => { setActive(day); setFocus(`${day}-${i}`); }} />
        <div className="daylist">
          {days.map((d) => (
            <article key={d.day} className="card-solid day">
              <header>
                <div>
                  <h4>{d.title}</h4>
                  <div className="muted small">{fmtDate(d.date)} · окно {d.start_time}–{d.end_limit}</div>
                </div>
                {d.weather && <span className="weather" title={d.weather.source}>{d.weather.label} <KindBadge kind={d.weather.kind} source={d.weather.source} /></span>}
              </header>
              <div className="facts small">
                <span><Icon name="route" size={14} /> {d.walk_km} км пешком</span>
                {d.transit_min > 0 && <span><Icon name="train" size={14} /> {d.transit_min} мин на транспорте</span>}
                <span><Icon name="wallet" size={14} /> {rub(d.cost_rub)} на билеты и проезд</span>
              </div>
              {d.notes.map((n) => <div key={n} className={`note ${n.startsWith("Внимание") || n.startsWith("Не успеваем") ? "warn" : ""}`}>{n}</div>)}
              <ol className="stops">
                {hotel && <li className="stop hotel"><span className="t">{d.start_time}</span><span className="with-ic"><Icon name="hotel" size={15} /> Старт от отеля «{hotel.name.replace(/^.*«|»$/g, "")}»</span></li>}
                {d.stops.map((s, i) => (
                  <li key={s.place.id} className={`stop ${focus === `${d.day}-${i}` ? "focus" : ""}`}>
                    <div className="leg">{s.leg_mode === "transit" ? `на транспорте ${s.leg_min} мин (${s.leg_km} км${s.leg_cost_rub ? `, ${rub(s.leg_cost_rub)}` : ""})` : `пешком ${s.leg_min} мин (${s.leg_km} км)`}</div>
                    <span className="t">{s.arrive}</span>
                    <div className="stop-body">
                      <b>{i + 1}. {s.place.name}</b>
                      <div className="muted small">
                        {s.place.cats.map((c) => CAT_LABEL[c] ?? c).join(" · ")} · {s.place.visit_min} мин
                        {s.place.ticket_rub ? ` · билет ~${rub(s.place.ticket_rub)}` : " · бесплатно"}
                        {s.place.indoor ? " · под крышей" : ""}
                      </div>
                      <div className="muted small">{s.place.description} · <i>{s.place.source}</i></div>
                      {s.note && <div className={`note ${s.note.startsWith("Внимание") ? "warn" : ""}`}>{s.note}</div>}
                    </div>
                    <div className="stop-actions">
                      {!s.place.cats.includes("cafe") && <button className="btn small" disabled={busy} onClick={() => onDay(d.day, "replace_with_cafe", { place_id: s.place.id })} title="Заменить на кафе рядом"><Icon name="cup" size={14} /> На кафе</button>}
                      <button className="btn small ghost" disabled={busy} onClick={() => onDay(d.day, "remove_place", { place_id: s.place.id })}><Icon name="close" size={14} /> Убрать</button>
                    </div>
                  </li>
                ))}
              </ol>
              <div className="day-actions">
                <button className="btn small" disabled={busy || d.less_walking} onClick={() => onDay(d.day, "less_walking")}><Icon name="route" size={14} /> Меньше ходьбы</button>
                <button className="btn small" disabled={busy || d.indoor_only} onClick={() => onDay(d.day, "rain")}><Icon name="hotel" size={14} /> Дождь: под крышу</button>
                <button className="btn small" disabled={busy} onClick={() => onDay(d.day, "add_category", { category: "museum" })}><Icon name="museum" size={14} /> Добавить музей</button>
                <button className="btn small" disabled={busy} onClick={() => onDay(d.day, "add_category", { category: "cafe" })}><Icon name="cup" size={14} /> Добавить кафе</button>
                <button className="btn small" disabled={busy} onClick={() => onDay(d.day, "add_category", { category: "view" })}><Icon name="mountain" size={14} /> Добавить вид</button>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
