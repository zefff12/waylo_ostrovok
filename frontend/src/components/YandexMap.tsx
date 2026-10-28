import { useEffect, useRef } from "react";
import type { DayPlan, Hotel } from "../types";
import { DAY_COLORS, HOTEL_SVG } from "./MapView";

declare global { interface Window { ymaps3?: any } }

export const YANDEX_HOSTS = ["localhost"];

let loading: Promise<any> | null = null;

export function loadYmaps(key: string): Promise<any> {
  if (window.ymaps3) return window.ymaps3.ready.then(() => window.ymaps3);
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `https://api-maps.yandex.ru/v3/?apikey=${encodeURIComponent(key)}&lang=ru_RU`;
    const timer = setTimeout(() => reject(new Error("timeout")), 8000);
    s.onload = () => window.ymaps3.ready.then(() => { clearTimeout(timer); resolve(window.ymaps3); }, reject);
    s.onerror = () => { clearTimeout(timer); reject(new Error("load")); };
    document.head.appendChild(s);
  }).catch((e) => { loading = null; throw e; });
  return loading;
}

export function YandexMap({ days, hotel, activeDay, onSelectStop }: {
  days: DayPlan[]; hotel: Hotel | null; activeDay: number | null; onSelectStop?: (day: number, idx: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<any>(null);
  const layer = useRef<any[]>([]);
  const lastSig = useRef("");

  useEffect(() => {
    const y = window.ymaps3;
    if (!box.current || !y) return;
    const m = new y.YMap(box.current, { location: { center: [30.33, 59.93], zoom: 12 }, margin: [48, 48, 48, 48] });
    m.addChild(new y.YMapDefaultSchemeLayer({}));
    m.addChild(new y.YMapDefaultFeaturesLayer({}));
    map.current = m;
    lastSig.current = "";
    draw();
    return () => { m.destroy(); map.current = null; };
  }, []);

  useEffect(() => { draw(); });

  function draw() {
    const y = window.ymaps3;
    const m = map.current;
    if (!m || !y) return;
    const sig = JSON.stringify([activeDay, hotel?.id, days.map((d) => d.stops.map((s) => s.place.id + s.arrive))]);
    if (sig === lastSig.current) return;
    lastSig.current = sig;
    layer.current.forEach((o) => m.removeChild(o));
    layer.current = [];
    const add = (o: any) => { m.addChild(o); layer.current.push(o); };
    const shown = days.filter((d) => activeDay === null || d.day === activeDay);
    const pts: [number, number][] = [];

    shown.forEach((d) => {
      const coords: [number, number][] = [];
      if (hotel) coords.push([hotel.lon, hotel.lat]);
      d.stops.forEach((s) => coords.push([s.place.lon, s.place.lat]));
      add(new y.YMapFeature({
        geometry: { type: "LineString", coordinates: coords },
        style: { stroke: [{ color: DAY_COLORS[(d.day - 1) % DAY_COLORS.length], width: 4, opacity: 0.75, dash: [8, 5] }] },
      }));
    });
    if (hotel) {
      const el = document.createElement("div");
      el.className = "pin pin-hotel ypin";
      el.innerHTML = HOTEL_SVG;
      el.title = `${hotel.name} — ${hotel.kind === "estimate" ? "реальный отель, цена — оценка" : "демо-отель"}`;
      add(new y.YMapMarker({ coordinates: [hotel.lon, hotel.lat] }, el));
      pts.push([hotel.lon, hotel.lat]);
    }
    shown.forEach((d) => d.stops.forEach((s, i) => {
      const el = document.createElement("div");
      el.className = "pin ypin";
      el.style.background = DAY_COLORS[(d.day - 1) % DAY_COLORS.length];
      el.textContent = activeDay === null ? `${d.day}·${i + 1}` : String(i + 1);
      el.title = `${s.place.name}, ${s.arrive}–${s.depart}`;
      el.onclick = () => onSelectStop?.(d.day, i);
      add(new y.YMapMarker({ coordinates: [s.place.lon, s.place.lat] }, el));
      pts.push([s.place.lon, s.place.lat]);
    }));
    if (pts.length === 1) m.setLocation({ center: pts[0], zoom: 15, duration: 400 });
    else if (pts.length > 1) {
      const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
      m.setLocation({ bounds: [[Math.min(...lons), Math.max(...lats)], [Math.max(...lons), Math.min(...lats)]], duration: 400 });
    }
  }

  return <div ref={box} className="map" />;
}
