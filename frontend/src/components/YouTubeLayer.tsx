import { useEffect, useRef, useState } from "react";

const ORIGIN = "https://www.youtube-nocookie.com";
const PLAYING = 1;
const ENDED = 0;

export function YouTubeLayer({ id, paused, onFail }: { id: string; paused: boolean; onFail?: () => void }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [visible, setVisible] = useState(false);
  const playing = useRef(false);

  const command = (func: string, args: unknown[] = []) =>
    frame.current?.contentWindow?.postMessage(JSON.stringify({ event: "command", func, args }), ORIGIN);

  useEffect(() => {
    let reveal: ReturnType<typeof setTimeout> | undefined;
    const giveUp = setTimeout(() => { if (!playing.current) onFail?.(); }, 15000);
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== ORIGIN || e.source !== frame.current?.contentWindow) return;
      let msg: { event?: string; info?: unknown };
      try { msg = typeof e.data === "string" ? JSON.parse(e.data) : e.data; } catch { return; }
      const state = msg.event === "onStateChange" ? msg.info
        : msg.event === "infoDelivery" ? (msg.info as { playerState?: number } | undefined)?.playerState : undefined;
      if (msg.event === "onReady") { command("mute"); command("playVideo"); }
      if (msg.event === "onError") { setVisible(false); onFail?.(); }
      if (state === PLAYING && !playing.current) {
        playing.current = true;
        reveal = setTimeout(() => setVisible(true), 2800);
      }
      if (state === ENDED) { command("seekTo", [0, true]); command("playVideo"); }
    };
    addEventListener("message", onMessage);
    return () => { removeEventListener("message", onMessage); clearTimeout(giveUp); clearTimeout(reveal); };
  }, [id, onFail]);

  useEffect(() => { command(paused ? "pauseVideo" : "playVideo"); }, [paused]);

  const params = new URLSearchParams({
    autoplay: "1", mute: "1", controls: "0", loop: "1", playlist: id, playsinline: "1", rel: "0",
    modestbranding: "1", iv_load_policy: "3", disablekb: "1", fs: "0", cc_load_policy: "0",
    enablejsapi: "1", origin: location.origin, widget_referrer: location.origin,
  });

  return (
    <div className={`bd-youtube ${visible ? "ready" : ""}`} aria-hidden="true">
      <iframe ref={frame} src={`${ORIGIN}/embed/${id}?${params}`} title="Фоновое видео" tabIndex={-1}
        allow="autoplay; encrypted-media; picture-in-picture" referrerPolicy="strict-origin-when-cross-origin"
        onLoad={() => frame.current?.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: "waylo-bg", channel: "widget" }), ORIGIN)} />
    </div>
  );
}
