// Antennes types de la station d'en face (émission) : gain dans la direction du WebSDR selon l'angle de départ.
// Calcul classique « élément + image dans le sol » (méthode des logiciels de type HFTA), sol moyen
// (εr = 13, σ = 5 mS/m) :
//   G(Δ) = G_espace_libre + 20·log10 |E(Δ)| + 20·log10 |1 + Γ(Δ)·exp(−j·2k·h·sinΔ)| − pertes
// Verticales posées au sol : diagramme sur sol parfait corrigé par le sol réel |1 + Γv| / 2.
// Les antennes directives sont supposées pointées vers le WebSDR. Valeurs absolues approchées (quelques dB).

const EPS_R = 13, SIGMA = 0.005;

const flat = () => 1;
const loopH = (d) => Math.cos((Math.PI / 4) * Math.cos(d));     // loop horizontale : maximum vers le zénith
const loopV = (d) => Math.cos((Math.PI / 4) * Math.sin(d));     // delta-loop / quad verticale : angle bas
function vert(lenL) {                                            // monopôle de longueur lenL (en λ)
  const k = Math.PI * 2 * lenL;
  return (d) => { const c = Math.cos(d); return c < 1e-3 ? 0 : Math.abs((Math.cos(k * Math.sin(d)) - Math.cos(k)) / c) / Math.abs(1 - Math.cos(k)); };
}
const beam = (q) => (d) => Math.max(0, Math.cos(d)) ** q;

// id, groupe, libellé, polarisation, hauteur (m) ou [fraction de λ, base m], gain espace libre, diagramme, pertes, [fmin, fmax]
export const TX_ANTENNAS = [
  ['dip6', 'Dipôles', 'Dipôle à 6 m', 'H', 6, 2.15, flat, 0.3, [1.8, 54]],
  ['dip10', 'Dipôles', 'Dipôle à 10 m', 'H', 10, 2.15, flat, 0.3, [1.8, 54]],
  ['dip15', 'Dipôles', 'Dipôle à 15 m', 'H', 15, 2.15, flat, 0.3, [1.8, 54]],
  ['dip25', 'Dipôles', 'Dipôle à 25 m', 'H', 25, 2.15, flat, 0.3, [1.8, 54]],
  ['invv12', 'Dipôles', 'V inversé, sommet à 12 m', 'H', 9.5, 1.6, flat, 0.4, [1.8, 54]],
  ['efhw10', 'Dipôles', 'Long fil / EFHW à 10 m', 'H', 10, 2.0, flat, 0.8, [1.8, 54]],
  ['nvis3', 'Dipôles', 'Dipôle NVIS à 3 m', 'H', 3, 2.15, flat, 0.8, [1.8, 11]],
  ['loop7', 'Loops', 'Loop onde entière horizontale à 7 m', 'H', 7, 3.1, loopH, 0.3, [1.8, 54]],
  ['loop15', 'Loops', 'Loop onde entière horizontale à 15 m', 'H', 15, 3.1, loopH, 0.3, [1.8, 54]],
  ['delta', 'Loops', 'Delta-loop verticale (base à 2 m)', 'H', [0.12, 2], 3.1, loopV, 0.3, [3.5, 54]],
  ['magloop', 'Loops', 'Loop magnétique (petite, verticale)', 'V', 2, 1.76, beam(1), 4.0, [3.5, 30]],
  ['vert14', 'Verticales', 'Verticale λ/4 au sol (radians)', 'Vg', 0, 5.15, vert(0.25), 1.5, [1.8, 54]],
  ['vert58', 'Verticales', 'Verticale 5/8 λ au sol (radians)', 'Vg', 0, 8.0, vert(0.625), 1.5, [3.5, 54]],
  ['gp', 'Verticales', 'Ground-plane surélevée (base à 10 m)', 'V', [0.125, 10], 2.15, vert(0.25), 0.5, [7, 54]],
  ['hexbeam', 'Directives (pointées vers le WebSDR)', 'Hexbeam 2 él. à 10 m', 'H', 10, 5.5, beam(1.2), 0.3, [14, 54]],
  ['yagi3_12', 'Directives (pointées vers le WebSDR)', 'Yagi 3 él. à 12 m', 'H', 12, 7.5, beam(1.5), 0.2, [14, 54]],
  ['yagi3_20', 'Directives (pointées vers le WebSDR)', 'Yagi 3 él. à 20 m', 'H', 20, 7.5, beam(1.5), 0.2, [14, 54]],
  ['yagi5_20', 'Directives (pointées vers le WebSDR)', 'Yagi 5 él. à 20 m', 'H', 20, 10.0, beam(2.5), 0.2, [14, 54]],
  ['quad2', 'Directives (pointées vers le WebSDR)', 'Quad cubique 2 él. à 15 m', 'H', 15, 7.0, beam(1.4), 0.2, [14, 30]],
].map(([id, group, name, pol, h, g0, e, loss, range]) => ({ id, group, name, pol, h, g0, e, loss, range }));

export const usable = (a, f) => f >= a.range[0] && f <= a.range[1];

// petits complexes [re, im]
const cadd = (a, b) => [a[0] + b[0], a[1] + b[1]];
const csub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const cmul = (a, b) => [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]];
const cdiv = (a, b) => { const d = b[0] * b[0] + b[1] * b[1]; return [(a[0] * b[0] + a[1] * b[1]) / d, (a[1] * b[0] - a[0] * b[1]) / d]; };
const cabs = (a) => Math.hypot(a[0], a[1]);
function csqrt([x, y]) { const r = Math.hypot(x, y); const re = Math.sqrt((r + x) / 2); const im = Math.sign(y || 1) * Math.sqrt((r - x) / 2); return [re, im]; }

/** Coefficient de réflexion de Fresnel du sol moyen */
function gamma(d, lam, pol) {
  const eps = [EPS_R, -60 * SIGMA * lam];
  const s = Math.sin(d), c2 = Math.cos(d) ** 2;
  const root = csqrt(csub(eps, [c2, 0]));
  if (pol === 'H') return cdiv(csub([s, 0], root), cadd([s, 0], root));
  const es = cmul(eps, [s, 0]);
  return cdiv(csub(es, root), cadd(es, root));
}

/** Gain (dBi) de l'antenne a à f MHz et à l'élévation elev (°) ; null hors de ses bandes */
export function txGain(a, f, elevDeg) {
  if (!usable(a, f)) return null;
  const lam = 299.792458 / f;
  const d = (Math.max(0.5, elevDeg) * Math.PI) / 180;
  const h = Array.isArray(a.h) ? a.h[0] * lam + a.h[1] : a.h;
  const e = a.e(d, lam);
  let ground;
  if (a.pol === 'Vg') ground = cabs(cadd([1, 0], gamma(d, lam, 'V'))) / 2;
  else {
    const ph = (-4 * Math.PI * h / lam) * Math.sin(d);
    ground = cabs(cadd([1, 0], cmul(gamma(d, lam, a.pol), [Math.cos(ph), Math.sin(ph)])));
  }
  if (e <= 1e-6 || ground <= 1e-6) return -40;
  return a.g0 + 20 * Math.log10(e) + 20 * Math.log10(ground) - a.loss;
}
