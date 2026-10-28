// Bilan de liaison d'un rayon (fenêtre Trajet) : SNR estimé et chances de réception par mode.
//
// Signal reçu S (dBW) = P + Gt + Gr − Lbf − La − Lg − Lz
//   P   : puissance d'émission (100 W par défaut) · Gt : antenne d'en face choisie (txantennas.js), à l'angle du rayon
//   Gr  : loop du WebSDR (NEC, moyenne en azimut) à l'élévation du rayon
//   Lbf : affaiblissement d'espace libre sur la longueur réelle parcourue = 32,45 + 20 log f + 20 log d
//   La  : absorption D par saut, George & Bradley (comme le calcul des bandes) :
//         677,2 · sec i · (1 + 0,0037 R) · cos(0,881 χ)^1,3 / ((f + 1,2)^1,98 + 10,2)
//         × facteur fmin mesuré par les ionosondes, + éruption en cours (D-RAP, 2 traversées)
//   Lg  : 3 dB par réflexion sur le sol (2e et 3e sauts) · Lz : 9 dB de pertes diverses (UIT-R P.533)
// Bruit N (dBW) = Fa − 204 + 10 log B : modèle UIT-R P.372, bruit artificiel « zone rurale » et bruit
//   galactique (seulement si f > foF2), + l'écart du bruit mesuré par ORSAT à son niveau habituel s'il est plus fort
//   (orages, QRM du moment).
// Chances : le signal fluctue (fading, variations d'heure en heure) : loi normale d'écart type 7 dB autour
//   du SNR calculé ; chance = probabilité que le SNR dépasse le seuil du mode.

export const MODES = [
  { id: 'SSB', bw: 2400, req: 10, label: 'SSB' },
  { id: 'CW', bw: 500, req: 0, label: 'CW' },
  { id: 'FT8', bw: 2500, req: -21, label: 'FT8' },
  { id: 'WSPR', bw: 2500, req: -28, label: 'WSPR' },
];
const SIGMA = 7, GT = 2, LG = 3, LZ = 9, DLAYER_KM = 100, R = 6371;

const log10 = Math.log10;

/** sec de l'angle d'incidence à la traversée de la couche D pour une élévation de départ (°) */
export function secD(elevDeg) {
  const s = (R * Math.cos((elevDeg * Math.PI) / 180)) / (R + DLAYER_KM);
  return 1 / Math.sqrt(Math.max(1e-4, 1 - s * s));
}

/** Absorption D d'un saut (dB) */
export function absorption(f, elevDeg, ctx) {
  const chi = ctx?.chi ?? 90, sec = secD(elevDeg);
  if (chi >= 90) return 0;
  const i = (1 + 0.0037 * (ctx.ssn ?? 80)) * Math.cos((0.881 * chi * Math.PI) / 180) ** 1.3;
  let a = (677.2 * sec * i) / ((f + 1.2) ** 1.98 + 10.2) * (ctx.dfactor ?? 1);
  if (ctx.haf0) a += 2 * sec * ((ctx.haf0 * Math.cos((chi * Math.PI) / 180) ** 0.75) / f) ** 1.5;
  return a;
}

/** Bruit (dBW dans 1 Hz) */
export function noise1Hz(f, foF2, excess) {
  const man = 67.2 - 27.7 * log10(f);
  const gal = f > (foF2 || 0) ? 52 - 23 * log10(f) : -99;
  const fa = 10 * log10(10 ** (man / 10) + 10 ** (gal / 10)) + Math.max(0, excess || 0);
  return fa - 204;
}

// loi normale : P(X > -m) avec X ~ N(0, σ)
function phi(x) {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989423 * Math.exp((-x * x) / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}

/**
 * f (MHz), elev (°), len1 (km, longueur d'un saut), hops (nombre de sauts), grDbi (gain loop),
 * ctx (contexte /api/linkctx), band (pour l'écart de bruit mesuré), foF2, pW (W)
 * -> { snr1Hz, la, modes: [{id, snr, p}] }
 */
export function budget({ f, elev, len1, hops = 1, grDbi = 0, gtDbi = GT, ctx, band, foF2, pW = 100 }) {
  const la = hops * absorption(f, elev, ctx);
  const lbf = 32.45 + 20 * log10(f) + 20 * log10(Math.max(1, hops * len1));
  const s = 10 * log10(pW) + gtDbi + grDbi - lbf - la - LG * (hops - 1) - LZ;   // dBW
  const n = noise1Hz(f, foF2, ctx?.noise?.[band]);
  const snr1 = s - n;
  return {
    snr1Hz: snr1, la, lbf,
    modes: MODES.map((m) => {
      const snr = snr1 - 10 * log10(m.bw);
      return { id: m.id, snr, p: phi((snr - m.req) / SIGMA) };
    }),
  };
}

export const pct = (p) => (p >= 0.995 ? '> 99 %' : p < 0.01 ? '< 1 %' : `${Math.round(p * 100)} %`);
export const pCls = (p) => (p >= 0.9 ? 'p9' : p >= 0.5 ? 'p5' : p >= 0.1 ? 'p1' : 'p0');
