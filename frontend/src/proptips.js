// Infobulles des valeurs de propagation (attribut title : au survol de la souris).
// Chaque fonction donne ce que mesure l'indice, puis ce que vaut la valeur affichée.

const num = (v) => (v == null || v === '' || Number.isNaN(+v) ? null : +v);

export function tipSfi(v) {
  const x = num(v);
  let w = '';
  if (x != null) {
    w = x < 70 ? 'très faible : bandes hautes (15-10 m) fermées, 40-20 m seulement'
      : x < 90 ? 'faible : 20 m correct, 15 m et au-dessus rarement ouverts'
      : x < 120 ? 'moyen : 20-17 m bons, 15 m ouvert en journée'
      : x < 150 ? 'bon : 15-12 m ouverts, 10 m par moments'
      : x < 200 ? 'très bon : 10 m ouvert en journée, DX facile sur les bandes hautes'
      : 'exceptionnel : toutes les bandes HF ouvertes, MUF élevées';
  }
  return `SFI — flux solaire à 10,7 cm (F10.7), en unités de flux solaire.\n`
    + `Mesure l'activité du Soleil qui ionise la couche F2 : plus il est haut, plus la MUF monte.`
    + (w ? `\n\n${Math.round(x)} : ${w}.` : '');
}

export function tipA(v) {
  const x = num(v);
  let w = '';
  if (x != null) {
    w = x < 8 ? 'calme, bonnes conditions' : x < 16 ? 'instable' : x < 30 ? 'actif : absorption et fading sur les trajets polaires'
      : x < 50 ? 'tempête mineure' : x < 100 ? 'tempête majeure : HF dégradées' : 'tempête sévère : HF très perturbées';
  }
  return `Indice A — agitation du champ magnétique terrestre sur 24 h (0 à 400).\n`
    + `Moyenne quotidienne de l'indice K : il résume la journée, il ne réagit pas vite.`
    + (w ? `\n\n${Math.round(x)} : ${w}.` : '');
}

export function tipK(v) {
  const x = num(v);
  let w = '';
  if (x != null) {
    w = x < 2 ? 'calme : conditions stables'
      : x < 4 ? 'peu agité : légère dégradation possible sur les trajets polaires'
      : x < 5 ? 'actif : absorption accrue, fading, MUF en baisse'
      : `tempête géomagnétique G${Math.min(5, Math.floor(x) - 4)} : HF dégradées, trajets polaires coupés, aurores possibles (VHF)`;
  }
  return `Indice K (Kp) — agitation du champ magnétique terrestre sur 3 h (0 à 9, échelle logarithmique).\n`
    + `C'est l'indice qui réagit le plus vite aux tempêtes ; un K bas est favorable aux HF.`
    + (w ? `\n\n${typeof v === 'number' ? +x.toFixed(1) : v} : ${w}.` : '');
}

export function tipSn(v) {
  const x = num(v);
  return `Nombre de taches solaires (indice SN).\n`
    + `Témoin de l'activité du cycle solaire : il évolue avec le SFI sur des semaines et des années.`
    + (x != null ? `\n\n${Math.round(x)} : ${x < 20 ? 'Soleil calme, minimum de cycle' : x < 80 ? 'activité modérée' : x < 150 ? 'activité forte' : 'activité très forte, proche du maximum de cycle'}.` : '');
}

export function tipXray(v) {
  const c = String(v || '').trim().toUpperCase();
  let w = '';
  if (c) {
    const k = c[0], n = parseFloat(c.slice(1)) || 1;
    w = k === 'A' || k === 'B' ? 'Soleil calme, aucun effet'
      : k === 'C' ? 'faible éruption, sans effet notable'
      : k === 'M' ? (n >= 5 ? 'éruption forte : black-out HF possible côté jour (R2)' : 'éruption moyenne : absorption des bandes basses côté jour possible (R1)')
      : k === 'X' ? 'éruption majeure : black-out HF côté jour (R3 et plus), parfois plus d\'une heure'
      : '';
  }
  return `X-ray — rayonnement X du Soleil (satellites GOES), classes A, B, C, M, X (×10 à chaque classe).\n`
    + `Une éruption ionise la couche D côté jour et absorbe les HF : le « fade-out » (Dellinger).`
    + (w ? `\n\n${c} : ${w}.` : '');
}

export function tipGeomag(v) {
  return `État du champ géomagnétique annoncé par hamqsl.com (calme, instable, actif, tempête…).\n`
    + `Résumé en clair des indices K et A.` + (v ? `\n\nActuellement : ${v}.` : '');
}

export const TIP_BANDS = `État des bandes calculé par hamqsl.com (N0NBH) à partir du SFI et de l'indice K, de jour et de nuit.\n`
  + `C'est une estimation générale, pas une mesure : la fiche d'un QSO donne la MUF mesurée par les ionosondes.`;

export const TIP_FOF2 = `foF2 — fréquence critique de la couche F2, en MHz.\n`
  + `Plus haute fréquence renvoyée par l'ionosphère pour un signal tiré à la verticale (NVIS).\n`
  + `Pour un trajet oblique, la MUF vaut environ 3 à 4 fois foF2.`;
export const TIP_MUF3000 = `MUF(3000) — fréquence maximale utilisable pour un saut de 3000 km, en MHz.\n`
  + `Mesurée par l'ionosonde au point indiqué : au-dessus, le signal traverse la couche F2 et part dans l'espace.`;
export const TIP_MUFHOP = `MUF du saut — la MUF(3000) mesurée ramenée à la longueur réelle de ton saut (loi de la sécante).\n`
  + `Plus le saut est court, plus la MUF est basse. C'est la valeur à comparer avec ta fréquence.`;
export const TIP_FOES = `foEs — fréquence critique de la couche E sporadique, en MHz (vers 100 km d'altitude).\n`
  + `Nuages très ionisés, surtout l'été en journée : au-delà de 5 MHz, ouvertures possibles sur 10 m, 6 m, parfois 2 m (saut d'environ 1000 à 2000 km).`;
