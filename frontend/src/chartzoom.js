// Zoom sur l'axe du temps des graphes 24 h (Météo locale, Orages et QRN), tout à la souris :
//   molette = zoom autour du pointeur, glisser = sélectionner une plage, double-clic = journée entière.
// Au doigt : glisser horizontalement sélectionne aussi une plage.

const MIN_SPAN = 0.5;   // 30 min au plus près

// graduations horaires adaptées à la plage [a, b] (heures)
export function hourTicks(a, b) {
  const span = b - a;
  const step = [6, 3, 2, 1, 0.5, 0.25].reduce((best, st) => (span / st <= 6 ? st : best), 6);
  const ticks = [];
  for (let h = Math.ceil(a / step - 1e-9) * step; h <= b + 1e-9; h += step) {
    const hh = Math.floor(h + 1e-9), mm = Math.round((h - hh) * 60);
    ticks.push({ h, label: span >= 23.99 ? `${hh}h` : `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}` });
  }
  return ticks;
}

// heure (décimale) d'un relevé « HHMM… »
export const hourOf = (t) => +t.slice(0, 2) + +t.slice(2, 4) / 60;

// action Svelte : opts = { x0, x1, view: [a, b], set(a, b), select([h1, h2] | null) }
export function timeZoom(svg, opts) {
  let start = null;
  const hourAt = (e) => {
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse());
    const [a, b] = opts.view;
    const f = Math.min(1, Math.max(0, (p.x - opts.x0) / (opts.x1 - opts.x0)));
    return a + f * (b - a);
  };
  const apply = (a, b) => {
    let span = Math.min(24, Math.max(MIN_SPAN, b - a));
    a = Math.max(0, Math.min(24 - span, a));
    opts.set(a, a + span);
  };
  function wheel(e) {
    const [a, b] = opts.view, h = hourAt(e);
    const k = e.deltaY > 0 ? 1.25 : 0.8;
    if (k > 1 && b - a >= 24) return;   // déjà la journée entière : la page défile normalement
    e.preventDefault();
    apply(h - (h - a) * k, h - (h - a) * k + (b - a) * k);
  }
  function down(e) {
    if (e.button !== 0) return;
    start = hourAt(e);
    svg.setPointerCapture(e.pointerId);
  }
  function move(e) {
    if (start == null) return;
    const h = hourAt(e);
    opts.select([Math.min(start, h), Math.max(start, h)]);
  }
  function up(e) {
    if (start == null) return;
    const h = hourAt(e), lo = Math.min(start, h), hi = Math.max(start, h);
    start = null;
    opts.select(null);
    if (hi - lo >= 0.25) apply(lo, hi);   // plage d'au moins 15 min, sinon simple clic
  }
  const reset = () => opts.set(0, 24);
  svg.addEventListener('wheel', wheel, { passive: false });
  svg.addEventListener('pointerdown', down);
  svg.addEventListener('pointermove', move);
  svg.addEventListener('pointerup', up);
  svg.addEventListener('pointercancel', up);
  svg.addEventListener('dblclick', reset);
  return {
    update(o) { opts = o; },
    destroy() {
      svg.removeEventListener('wheel', wheel);
      svg.removeEventListener('pointerdown', down);
      svg.removeEventListener('pointermove', move);
      svg.removeEventListener('pointerup', up);
      svg.removeEventListener('pointercancel', up);
      svg.removeEventListener('dblclick', reset);
    },
  };
}

let n = 0;
export const uid = (p) => `${p}-${++n}`;
