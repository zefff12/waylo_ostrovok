import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { Hotel } from "../types";
import { rub } from "../api";
import { GlassIcon, Icon } from "./Icons";
import { KindBadge, SectionTitle, Why } from "./TripTab";

const MEALS = { none: "без питания", breakfast: "завтрак", half_board: "завтрак + ужин" };
const CANCEL = { free: "бесплатная отмена", partial: "отмена −1 ночь", non_refundable: "невозвратный" };
type Sort = "score" | "price" | "distance" | "rating";
const SORT_LABEL: Record<Sort, string> = { score: "Рекомендуем", price: "Дешевле", distance: "Ближе к прогулкам", rating: "Рейтинг" };

// у вымышленных демо-отелей facts пустой — тогда всё в них демо
export const fact = (o: Hotel, field: string) => o.facts?.[field] ?? o.kind;

type Filters = { freeCancel: boolean; breakfast: boolean; pets: boolean; kids: boolean; maxNight: number | null };
const NO_FILTERS: Filters = { freeCancel: false, breakfast: false, pets: false, kids: false, maxNight: null };

function loadFavs(): string[] {
  try { return JSON.parse(localStorage.getItem("waylo_favs") ?? "[]"); } catch { return []; }
}

/** Фрагмент карты OSM вокруг отеля 2×2 тайла, отель — в центре миниатюры. */
function Thumb({ h }: { h: Hotel }) {
  const z = 16, n = 2 ** z;
  const fx = (h.lon + 180) / 360 * n;
  const lat = h.lat * Math.PI / 180;
  const fy = (1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 * n;
  const x0 = Math.floor(fx - 0.5), y0 = Math.floor(fy - 0.5);
  const off = { left: `calc(50% - ${(fx - x0) * 256}px)`, top: `calc(50% - ${(fy - y0) * 256}px)` };
  return (
    <div className="hthumb" aria-hidden="true">
      <div className="tiles" style={off}>
        {[0, 1].flatMap((dy) => [0, 1].map((dx) => (
          <img key={`${dx}${dy}`} src={`https://tile.openstreetmap.org/${z}/${x0 + dx}/${y0 + dy}.png`} alt="" loading="lazy" />
        )))}
      </div>
      <span className="hpin"><Icon name="hotel" size={15} /></span>
      <span className="osm-attr">© OSM</span>
    </div>
  );
}

export function HotelList({ hotels, selectedId, busy, onSelect, pets, kids }: {
  hotels: Hotel[]; selectedId: string | null; busy: boolean; onSelect: (id: string) => void; pets: boolean; kids: boolean;
}) {
  const [sort, setSort] = useState<Sort>("score");
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sheet, setSheet] = useState(false);
  const [favs, setFavs] = useState<string[]>(loadFavs);
  const [onlyFavs, setOnlyFavs] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => { try { localStorage.setItem("waylo_favs", JSON.stringify(favs)); } catch { /* приватный режим */ } }, [favs]);
  useEffect(() => {
    if (!sheet) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSheet(false); };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [sheet]);

  const maxPrice = Math.max(...hotels.map((h) => h.price_per_night), 0);
  const shown = useMemo(() => {
    const f = hotels.filter((h) =>
      (!filters.freeCancel || h.cancellation === "free") && (!filters.breakfast || h.meals !== "none")
      && (!filters.pets || h.pets_allowed) && (!filters.kids || h.kids_friendly)
      && (!filters.maxNight || h.price_per_night <= filters.maxNight) && (!onlyFavs || favs.includes(h.id)));
    const key: Record<Sort, (h: Hotel) => number> = {
      score: (h) => -h.score, price: (h) => h.total, distance: (h) => h.distance_center_km, rating: (h) => -h.rating,
    };
    return f.sort((a, b) => key[sort](a) - key[sort](b));
  }, [hotels, filters, sort, onlyFavs, favs]);

  const active = Object.entries(filters).filter(([k, v]) => k !== "maxNight" ? v : v !== null).length;
  const real = hotels.some((h) => h.kind === "estimate");
  const toggleFav = (id: string) => setFavs((f) => f.includes(id) ? f.filter((x) => x !== id) : [...f, id]);

  return (
    <section className="hotels">
      <div className="hotels-head">
        <SectionTitle icon="hotel" title={`Отели · ${shown.length} из ${hotels.length}`} hint={real
          ? "Реальные отели из OpenStreetMap. Цена — оценка Waylo; отмена, питание, рейтинг и допуск детей — демо."
          : "Синтетические демо-отели; критерии сравнения реальные."} />
        <div className="hotels-tools">
          <label className="sort glass-light">
            <Icon name="sort" size={16} />
            <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Сортировка">
              {Object.entries(SORT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <GlassIcon name="heart" label={onlyFavs ? "Показать все" : "Только избранное"} active={onlyFavs} onClick={() => setOnlyFavs((v) => !v)} />
          <button className={`filter-btn glass-light ${active ? "on" : ""}`} onClick={() => setSheet(true)}>
            <Icon name="filter" size={17} /> Фильтры{active ? <b>{active}</b> : null}
          </button>
        </div>
      </div>

      {shown.length === 0 ? (
        <div className="state card-solid">
          <Icon name="search" size={26} />
          <b>Ничего не нашлось</b>
          <span className="muted">Смягчите фильтры — сейчас под них не подходит ни один отель.</span>
          <button className="btn" onClick={() => { setFilters(NO_FILTERS); setOnlyFavs(false); }}>Сбросить фильтры</button>
        </div>
      ) : (
        <div className="hlist">
          {shown.map((o, i) => {
            const sel = o.id === selectedId;
            return (
              <article key={o.id} className={`hcard card-solid ${sel ? "sel" : ""}`} style={{ animationDelay: `${Math.min(i, 6) * 40}ms` }}>
                <Thumb h={o} />
                <div className="hbody">
                  <div className="htop">
                    <div className="hname">
                      <h4>{o.website || o.osm_url
                        ? <a href={o.website ?? o.osm_url ?? ""} target="_blank" rel="noopener noreferrer">{o.name}</a> : o.name}</h4>
                      <div className="hmeta">
                        <span className="stars" aria-label={`${o.stars} звезды`}>{Array.from({ length: o.stars }, (_, k) => <Icon key={k} name="star" size={13} className="star" />)}{fact(o, "stars") !== "confirmed" ? <i title="Звёзды не указаны в OSM — оценка по типу отеля">?</i> : null}</span>
                        <span><Icon name="pin" size={13} /> {o.district}</span>
                      </div>
                    </div>
                    <GlassIcon name="heart" size="sm" label={favs.includes(o.id) ? "Убрать из избранного" : "В избранное"}
                      active={favs.includes(o.id)} className="fav" onClick={() => toggleFav(o.id)} />
                  </div>
                  <div className="htags">
                    <span className="tag"><Icon name="route" size={13} /> {o.distance_center_km} км до мест</span>
                    <span className={`tag ${o.cancellation === "free" ? "good" : o.cancellation === "non_refundable" ? "bad" : ""}`}>{CANCEL[o.cancellation]}<sup>демо</sup></span>
                    <span className="tag">{MEALS[o.meals]}<sup>демо</sup></span>
                    {o.pets_allowed && <span className="tag">можно с животными{fact(o, "pets") !== "confirmed" && <sup>демо</sup>}</span>}
                    {kids && o.kids_friendly && <span className="tag">для детей<sup>демо</sup></span>}
                    {pets && !o.pets_allowed && <span className="tag bad">без животных</span>}
                  </div>
                  <div className="hfoot">
                    <div className="rating" title={fact(o, "rating") === "demo" ? "Рейтинг демо: в открытых данных его нет" : ""}>
                      <b>{o.rating.toFixed(1)}</b><span>рейтинг{fact(o, "rating") === "demo" ? " · демо" : ""}</span>
                    </div>
                    <div className="score-chip" title="Насколько вариант подходит под ваш запрос">совпадение {Math.round(o.score)}%</div>
                    <div className="price">
                      <b>{rub(o.total)}</b>
                      <span>{rub(o.price_per_night)} / ночь · <KindBadge kind={fact(o, "price")} source={o.source} /></span>
                    </div>
                    {sel ? <span className="badge sel-badge"><Icon name="check" size={13} /> выбран</span>
                      : <button className="btn primary" disabled={busy} onClick={() => onSelect(o.id)}>Выбрать</button>}
                  </div>
                  <button className="link why-toggle" onClick={() => setOpen(open === o.id ? null : o.id)}>
                    {open === o.id ? "Скрыть объяснение" : "Почему этот вариант"}
                  </button>
                  {open === o.id && <Why e={o.explanation} />}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {sheet && createPortal(  // поверх шапки и чата: у списка свой контекст наложения
        <div className="sheet-wrap" onClick={() => setSheet(false)}>
          <div className="sheet glass-modal" role="dialog" aria-modal="true" aria-label="Фильтры отелей" onClick={(e) => e.stopPropagation()}>
            <div className="sheet-grip" />
            <div className="sheet-head">
              <h3>Фильтры</h3>
              <GlassIcon name="close" label="Закрыть" size="sm" onClick={() => setSheet(false)} />
            </div>
            {([
              ["freeCancel", "Бесплатная отмена"], ["breakfast", "Есть питание"],
              ["pets", "Можно с животными"], ["kids", "Подходит детям"],
            ] as [keyof Filters, string][]).map(([k, label]) => (
              <label key={k} className="switch-row">
                <span>{label}</span>
                <input type="checkbox" role="switch" checked={Boolean(filters[k])}
                  onChange={(e) => setFilters((f) => ({ ...f, [k]: e.target.checked }))} />
                <i className="switch" />
              </label>
            ))}
            <label className="range-row">
              <span>Цена за ночь: {filters.maxNight ? `до ${rub(filters.maxNight)}` : "любая"}</span>
              <input type="range" min={1000} max={Math.max(2000, Math.ceil(maxPrice / 1000) * 1000)} step={500}
                value={filters.maxNight ?? Math.ceil(maxPrice / 1000) * 1000}
                onChange={(e) => setFilters((f) => ({ ...f, maxNight: Number(e.target.value) >= maxPrice ? null : Number(e.target.value) }))} />
            </label>
            <div className="sheet-actions">
              <button className="btn" onClick={() => setFilters(NO_FILTERS)}>Сбросить</button>
              <button className="btn primary" onClick={() => setSheet(false)}>Показать {shown.length}</button>
            </div>
          </div>
        </div>, document.body,
      )}
    </section>
  );
}
