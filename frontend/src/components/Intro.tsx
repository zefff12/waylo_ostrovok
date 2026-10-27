import { useEffect, useState } from "react";
import { GlassIcon, Icon, type IconName } from "./Icons";

/* Первый запуск: заставка с оригинальным логотипом → онбординг из трёх экранов.
   Флаг в localStorage: при обычных открытиях заставка не показывается. */

const SEEN_KEY = "waylo_intro_v1";

export function introSeen(): boolean {
  try { return localStorage.getItem(SEEN_KEY) === "1"; } catch { return true; }
}

function markSeen() {
  try { localStorage.setItem(SEEN_KEY, "1"); } catch { /* приватный режим — покажем ещё раз, не страшно */ }
}

function reduced() {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Заставка: проявление логотипа, проход света, мягкий подъём и растворение в главном экране. */
export function Splash({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState<"in" | "out">("in");
  // ?intro=hold — заставка ждёт клика (для презентации)
  const hold = new URLSearchParams(location.search).get("intro") === "hold";
  const leave = () => {
    setPhase("out");
    setTimeout(() => { performance.mark("waylo-splash-end"); onDone(); }, 650);
  };
  useEffect(() => {
    performance.mark("waylo-splash-start");  // метки видны в DevTools → Performance
    if (hold) return;
    const t = setTimeout(leave, reduced() ? 400 : 2300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className={`splash ${phase}`} onClick={() => phase === "in" && leave()} role="presentation">
      <div className="splash-logo">
        <img src="/logo-dark.png" alt="waylo" />
        <span className="splash-shine" aria-hidden="true" />
      </div>
      <p className="splash-tag">One prompt. Your whole journey.</p>
    </div>
  );
}

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: "spark", title: "Понимает обычный текст", text: "Город, даты, бюджет, кто едет, питомцы и интересы — из одной фразы. Если город не назван, предложит направления." },
  { icon: "plane", title: "Дорога и отель", text: "Сравнивает поезд и самолёт, подбирает реальные отели рядом с местами прогулок и объясняет выбор." },
  { icon: "route", title: "Прогулки по дням", text: "Маршрут от отеля на карте с учётом погоды, времени и того, сколько хочется ходить." },
  { icon: "wallet", title: "Бюджет и проверки", text: "Считает каждую статью, проверяет состыковки и честно помечает, где реальные данные, а где оценка." },
  { icon: "chat", title: "Правки словами", text: "«Сделай дешевле», «дождь на второй день» — меняет только нужное и показывает, что изменилось." },
];

const STEPS = 3;

export function Onboarding({ onFinish, onTry }: { onFinish: () => void; onTry: (prompt: string) => void }) {
  const [step, setStep] = useState(0);
  const finish = () => { markSeen(); onFinish(); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
      if (e.key === "ArrowRight") setStep((s) => Math.min(STEPS - 1, s + 1));
      if (e.key === "ArrowLeft") setStep((s) => Math.max(0, s - 1));
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="onb-wrap">
      <section className="onb glass-modal" role="dialog" aria-modal="true" aria-label="Знакомство с Waylo">
        <header className="onb-head">
          <div className="onb-dots" aria-label={`Шаг ${step + 1} из ${STEPS}`}>
            {Array.from({ length: STEPS }, (_, i) => <button key={i} className={i === step ? "on" : ""} aria-label={`Шаг ${i + 1}`} onClick={() => setStep(i)} />)}
          </div>
          <button className="link onb-skip" onClick={finish}>Пропустить</button>
        </header>

        <div className="onb-body" key={step}>
          {step === 0 && (
            <div className="onb-step onb-hello">
              <img src="/logo-dark.png" alt="waylo" className="onb-logo" />
              <h2>Одно сообщение — <br />вся поездка</h2>
              <p>Опишите, куда и как хотите поехать. Waylo подберёт направление, дорогу, отель и прогулки по дням, посчитает бюджет и доведёт до оформления.</p>
              <div className="onb-preview">
                <span className="onb-bubble">Хочу на 5 дней в Петербург в ноябре, бюджет 45 000 на двоих, любим музеи и кафе</span>
                <span className="onb-arrow"><Icon name="spark" size={16} /> план за несколько секунд</span>
              </div>
            </div>
          )}
          {step === 1 && (
            <div className="onb-step">
              <h2>Что умеет Waylo</h2>
              <ul className="onb-features">
                {FEATURES.map((f) => (
                  <li key={f.title}>
                    <span className="gicon gicon-md as-icon"><Icon name={f.icon} size={19} /></span>
                    <div><b>{f.title}</b><span>{f.text}</span></div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {step === 2 && (
            <div className="onb-step onb-start">
              <h2>С чего начать</h2>
              <ol className="onb-howto">
                <li><b>Напишите запрос</b> в поле поиска: куда, когда, с кем и что любите. Можно коротко — недостающее агент возьмёт допущением и покажет его.</li>
                <li><b>Посмотрите план:</b> дорогу, отели, прогулки и бюджет. Выберите вариант кнопкой или попросите изменить словами.</li>
                <li><b>Оформите демо-заказ</b> — без реальной оплаты.</li>
              </ol>
              <button className="onb-example glass-light" onClick={() => { markSeen(); onTry("Трёхдневная поездка в Казань, бюджет 40 тысяч, архитектура и местная кухня"); }}>
                <Icon name="search" size={16} /> Попробовать: «Три дня в Казани, бюджет 40 тысяч»
              </button>
            </div>
          )}
        </div>

        <footer className="onb-foot">
          {step > 0 ? <GlassIcon name="back" label="Назад" onClick={() => setStep(step - 1)} /> : <span />}
          {step < STEPS - 1
            ? <button className="btn primary onb-next" onClick={() => setStep(step + 1)}>Далее</button>
            : <button className="btn primary onb-next" onClick={finish}>Спланировать поездку</button>}
        </footer>
      </section>
    </div>
  );
}
