import { useCallback, useEffect, useRef, useState } from "react";
import { YouTubeLayer } from "./YouTubeLayer";
import type { Health, Trip } from "../types";

/* Слои 1–3 дизайн-системы: фоновое видео, атмосферное наложение, градиентная маска.
   Видео одно на всё приложение и не перехватывает нажатия (pointer-events: none). */

export type Scene = "field" | "wheat" | "sea" | "rain";

const SCENES: Record<Scene, { label: string; pos: string }> = {
  field: { label: "Поле на закате", pos: "50% 40%" },
  wheat: { label: "Пшеничное поле", pos: "50% 60%" },
  sea: { label: "Тёмное море", pos: "50% 50%" },
  rain: { label: "Дождь за окном", pos: "40% 40%" },
};

/** Сцена под поездку: море — для морских направлений, дождь — если прогноз дождливый. */
export function sceneFor(trip: Trip | null, health: Health | null): Scene {
  if (!trip?.params.destination) return "field";
  const rainy = trip.days.filter((d) => (d.weather?.precip_mm ?? 0) >= 3).length;
  if (trip.days.length && rainy >= Math.ceil(trip.days.length / 2)) return "rain";
  const tags = health?.cities.find((c) => c.id === trip.params.destination)?.tags ?? [];
  if (tags.includes("sea") || tags.includes("beach")) return "sea";
  return tags.includes("warm") ? "wheat" : "field";
}

function reducedMotion() {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function Backdrop({ scene, mode, paused, youtubeId }: {
  scene: Scene; mode: "home" | "results"; paused: boolean; youtubeId?: string | null;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [shown, setShown] = useState<Scene>(scene);
  const [fading, setFading] = useState(false);
  const [canPlay, setCanPlay] = useState(false);
  const still = paused || reducedMotion();
  const [ytFailed, setYtFailed] = useState(false);
  const onYtFail = useCallback(() => setYtFailed(true), []);
  // главный экран — видео из ссылки YouTube; локальная сцена остаётся под ним как запасной вариант
  const useYoutube = mode === "home" && Boolean(youtubeId) && !ytFailed && !reducedMotion();

  useEffect(() => {  // мягкая смена сцены: затемняем, меняем источник, проявляем
    if (scene === shown) return;
    setFading(true);
    const t = setTimeout(() => { setShown(scene); setCanPlay(false); setFading(false); }, 450);
    return () => clearTimeout(t);
  }, [scene, shown]);

  useEffect(() => {
    const v = video.current;
    if (!v) return;
    if (still) { v.pause(); return; }
    v.play().catch(() => undefined);  // автозапуск запрещён — остаётся постер
  }, [still, shown]);

  return (
    <div className={`backdrop bd-${mode} ${fading ? "fading" : ""}`} aria-hidden="true">
      <img className="bd-poster" src={`/media/${shown}.jpg`} alt="" style={{ objectPosition: SCENES[shown].pos }} />
      {!reducedMotion() && (
        <video ref={video} key={shown} className={`bd-video ${canPlay ? "ready" : ""}`} src={`/media/${shown}.mp4`}
          poster={`/media/${shown}.jpg`} autoPlay={!still} muted loop playsInline preload="metadata"
          style={{ objectPosition: SCENES[shown].pos }} onCanPlay={() => setCanPlay(true)} />
      )}
      {useYoutube && <YouTubeLayer id={youtubeId!} paused={still} onFail={onYtFail} />}
      <div className="bd-ambient" />
      <div className="bd-mask" />
    </div>
  );
}

export const SCENE_LABEL = Object.fromEntries(Object.entries(SCENES).map(([k, v]) => [k, v.label])) as Record<Scene, string>;
