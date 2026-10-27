import { useEffect, useRef, useState } from "react";
import maplibregl, { type Map as MLMap, type Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { DayPlan, Hotel } from "../types";
import { healthOnce } from "../api";
import { YANDEX_HOSTS, YandexMap, loadYmaps } from "./YandexMap";

const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© участники OpenStreetMap",
      maxzoom: 19,
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

export const HOTEL_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 20V8.5l8.5-4 8.5 4V20"/><path d="M8 20v-5h8v5"/></svg>';
export const DAY_COLORS = ["#0645F5", "#27C8F5", "#7B61FF", "#00A86B", "#FF8A00", "#E5484D", "#0B1738"];

type MapProps = {
  days: DayPlan[]; hotel: Hotel | null; activeDay: number | null; onSelectStop?: (day: number, idx: number) => void;
};

let yandexFailed = false;  // не ждём таймаут повторно при каждом открытии вкладки

/** Сразу OpenStreetMap; на карту Яндекса переключаемся, только когда она действительно загрузилась. */
export function MapView(props: MapProps) {
  const [engine, setEngine] = useState<"yandex" | "osm">(window.ymaps3 && !yandexFailed ? "yandex" : "osm");
  useEffect(() => {
    if (engine === "yandex" || yandexFailed) return;
    let alive = true;
    healthOnce()
      .then((h) => (h.yandex_js_key && YANDEX_HOSTS.includes(location.hostname) ? loadYmaps(h.yandex_js_key) : Promise.reject()))
      .then(() => { if (alive) setEngine("yandex"); }, () => { yandexFailed = true; });
    return () => { alive = false; };
  }, [engine]);
  return engine === "yandex" ? <YandexMap {...props} /> : <OsmMap {...props} />;
}

function OsmMap({ days, hotel, activeDay, onSelectStop }: MapProps) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const ready = useRef(false);

  useEffect(() => {
    if (!box.current) return;
    const m = new maplibregl.Map({ container: box.current, style: STYLE, center: [30.33, 59.93], zoom: 12, attributionControl: { compact: true } });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => { ready.current = true; draw(); });
    map.current = m;
    return () => { m.remove(); map.current = null; ready.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { draw(); });

  const lastSig = useRef("");

  function draw() {
    const m = map.current;
    if (!m || !ready.current) return;
    const sig = JSON.stringify([activeDay, hotel?.id, days.map((d) => d.stops.map((s) => s.place.id + s.arrive))]);
    if (sig === lastSig.current) return; // не сбрасываем масштаб, если план не менялся
    lastSig.current = sig;
    markers.current.forEach((mk) => mk.remove());
    markers.current = [];
    const shown = days.filter((d) => activeDay === null || d.day === activeDay);
    const bounds = new maplibregl.LngLatBounds();

    const features = shown.map((d) => {
      const coords: [number, number][] = [];
      if (hotel) coords.push([hotel.lon, hotel.lat]);
      d.stops.forEach((s) => coords.push([s.place.lon, s.place.lat]));
      return {
        type: "Feature" as const,
        properties: { color: DAY_COLORS[(d.day - 1) % DAY_COLORS.length] },
        geometry: { type: "LineString" as const, coordinates: coords },
      };
    });
    const data = { type: "FeatureCollection" as const, features };
    const src = m.getSource("routes") as maplibregl.GeoJSONSource | undefined;
    if (src) src.setData(data);
    else {
      m.addSource("routes", { type: "geojson", data });
      m.addLayer({
        id: "routes", type: "line", source: "routes",
        paint: { "line-color": ["get", "color"], "line-width": 4, "line-opacity": 0.75, "line-dasharray": [2, 1.2] },
        layout: { "line-cap": "round", "line-join": "round" },
      });
    }

    if (hotel) {
      const el = document.createElement("div");
      el.className = "pin pin-hotel";
      el.innerHTML = HOTEL_SVG;
      el.title = hotel.name;
      markers.current.push(new maplibregl.Marker({ element: el }).setLngLat([hotel.lon, hotel.lat])
        .setPopup(new maplibregl.Popup({ offset: 14 }).setText(`${hotel.name} — ${hotel.kind === "estimate" ? "реальный отель, цена — оценка" : "демо-отель"}`)).addTo(m));
      bounds.extend([hotel.lon, hotel.lat]);
    }
    shown.forEach((d) => d.stops.forEach((s, i) => {
      const el = document.createElement("div");
      el.className = "pin";
      el.style.background = DAY_COLORS[(d.day - 1) % DAY_COLORS.length];
      el.textContent = activeDay === null ? `${d.day}·${i + 1}` : String(i + 1);
      el.title = s.place.name;
      el.onclick = () => onSelectStop?.(d.day, i);
      const popup = new maplibregl.Popup({ offset: 14 }).setHTML(
        `<b>${escapeHtml(s.place.name)}</b><br/>${s.arrive}–${s.depart}<br/><small>${escapeHtml(s.place.source)}</small>`);
      markers.current.push(new maplibregl.Marker({ element: el }).setLngLat([s.place.lon, s.place.lat]).setPopup(popup).addTo(m));
      bounds.extend([s.place.lon, s.place.lat]);
    }));
    if (!bounds.isEmpty()) m.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 400 });
  }

  return <div ref={box} className="map" />;
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}
