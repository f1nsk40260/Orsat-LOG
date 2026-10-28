// Tracé de rayons HF dans l'ionosphère mesurée (ionosonde) — Terre sphérique, ionosphère stratifiée.
//
// Profil électronique : somme de couches de Chapman (α) construites sur les mesures de l'ionosonde :
//   fp²(h) = Σ foX² · exp(½ · (1 − z − e^(−z))),  z = (h − hmX) / HX
//   F2 : hmF2 mesurée, H = 45 km sous le pic, 70 km au-dessus · F1 : ~200 km, H = 25 km (de jour)
//   E : hmE (~110 km), H = 10 km · Es : couche mince (2 km) à l'altitude de la E, fréquence foEs
// Indice de réfraction (sans champ magnétique ni collisions) : n² = 1 − fp² / f².
// Intégration du rayon (méthode hamiltonienne, régulière au point de réflexion où n → 0) :
//   dr/dτ = p,  dp/dτ = ½ ∇(n²)   (p = n · direction, |p| = n)
// Le rayon part de IN93LR, monte avec l'élévation choisie et est suivi jusqu'au retour au sol
// (distance au sol = R · angle au centre) ou jusqu'à sa sortie par le haut (il traverse : pas de retour).
// Limites : pas de gradient horizontal (même ionosphère sur tout le trajet), pas de champ magnétique
// (ondes O/X confondues), pas d'absorption. C'est la géométrie du saut, pas le bilan de liaison.

export const R = 6371;
const HTOP = 1000;

function chapman(fo, hm, hlo, hhi, h) {
  if (!fo || !hm) return 0;
  const z = (h - hm) / (h < hm ? hlo : hhi);
  if (z < -12) return 0;
  return fo * fo * Math.exp(0.5 * (1 - z - Math.exp(-z)));
}

/** iono = { foF2, hmF2, foF1, hmF1, foE, hmE, foEs } (MHz, km) -> fonction fp²(h) en MHz² */
export function profile(iono) {
  const hE = iono.hmE || 110;
  return (h) => {
    if (h < 75) return 0;          // en dessous : couche D, qui absorbe sans réfléchir
    let v = chapman(iono.foF2, iono.hmF2 || 300, 45, 70, h)
      + chapman(iono.foF1, iono.hmF1 || 200, 25, 25, h)
      + chapman(iono.foE, hE, 10, 10, h);
    if (iono.foEs) {
      const z = (h - (hE - 2)) / 2;
      v = Math.max(v, iono.foEs * iono.foEs * Math.exp(-z * z));
    }
    return v;
  };
}

/** Un rayon : f (MHz), élévation (°). Renvoie { pts: [[θ, h]...], ground (km) | null, apex (km) } */
export function trace(fp2, f, elevDeg, step = 1.5) {
  const f2 = f * f;
  const n2 = (h) => 1 - fp2(h) / f2;
  const dn2 = (h) => (n2(h + 0.25) - n2(h - 0.25)) / 0.5;   // d(n²)/dh
  const e = (elevDeg * Math.PI) / 180;
  // repère plan : centre de la Terre à l'origine, départ au sommet (0, R)
  let x = 0, y = R, px = Math.cos(e), py = Math.sin(e);
  const pts = [[0, 0]];
  let apex = 0, prevH = 0;
  for (let i = 0; i < 20000; i++) {
    // RK2 (point milieu)
    const acc = (X, Y) => {
      const r = Math.hypot(X, Y), h = r - R, g = 0.5 * dn2(h);
      return [g * X / r, g * Y / r];
    };
    const [ax, ay] = acc(x, y);
    const xm = x + 0.5 * step * px, ym = y + 0.5 * step * py;
    const pxm = px + 0.5 * step * ax, pym = py + 0.5 * step * ay;
    const [bx, by] = acc(xm, ym);
    x += step * pxm; y += step * pym; px += step * bx; py += step * by;
    // renormalisation |p| = n (stabilité numérique)
    const r = Math.hypot(x, y), h = r - R, nn = Math.sqrt(Math.max(1e-6, n2(h))), pn = Math.hypot(px, py);
    px *= nn / pn; py *= nn / pn;
    const th = Math.atan2(x, y);
    if (i % 3 === 0) pts.push([th, h]);
    apex = Math.max(apex, h);
    if (h <= 0 && prevH > 0 && i > 5) {
      pts.push([th, 0]);
      return { pts, ground: th * R, apex };
    }
    if (h > HTOP) return { pts, ground: null, apex };
    prevH = h;
  }
  return { pts, ground: null, apex };
}

/** Éventail d'élévations : portée de chaque rayon, zone de silence, portée maxi d'un saut */
export function fan(fp2, f, elevs) {
  const rays = elevs.map((el) => ({ el, ...trace(fp2, f, el, 3) }));
  const back = rays.filter((r) => r.ground != null);
  return {
    rays,
    skip: back.length ? Math.min(...back.map((r) => r.ground)) : null,
    maxHop: back.length ? Math.max(...back.map((r) => r.ground)) : null,
    allBack: back.length === rays.length,
  };
}

/** Fréquence critique verticale (MHz) : plus haute fréquence qui revient à la verticale */
export const foMax = (iono) => Math.max(iono.foF2 || 0, iono.foF1 || 0, iono.foE || 0, iono.foEs || 0);

/** Couche de réflexion d'après l'altitude atteinte */
export function layerName(apex, iono) {
  const hE = iono.hmE || 110;
  if (apex < hE + 15) return iono.foEs && apex > hE - 10 ? 'E / Es' : 'E';
  if (apex < 230 && iono.foF1) return 'F1';
  return 'F2';
}
