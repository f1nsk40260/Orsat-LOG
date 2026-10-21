// Astronomie pour la fiche QSO : position du Soleil, hauteur en un lieu, éclairement de la
// carte (ligne grise) et trajet orthodromique. Formules du NOAA Solar Calculator (précision de
// l'ordre de la minute d'arc, largement suffisante pour la propagation).

const rad = Math.PI / 180;
const deg = 180 / Math.PI;

/** Date UTC du QSO : qso_date « AAAAMMJJ », time_on « HHMMSS ». */
export function qsoInstant(qsoDate, timeOn) {
  const t = (timeOn || '000000').padEnd(6, '0');
  return new Date(Date.UTC(+qsoDate.slice(0, 4), +qsoDate.slice(4, 6) - 1, +qsoDate.slice(6, 8),
    +t.slice(0, 2), +t.slice(2, 4), +t.slice(4, 6)));
}

/** Point subsolaire : déclinaison et longitude (degrés) où le Soleil est au zénith. */
export function subsolar(date) {
  const jd = date.getTime() / 86400000 + 2440587.5;
  const T = (jd - 2451545) / 36525;
  const L0 = (280.46646 + T * (36000.76983 + 0.0003032 * T)) % 360;
  const M = 357.52911 + T * (35999.05029 - 0.0001537 * T);
  const e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T);
  const C = Math.sin(M * rad) * (1.914602 - T * (0.004817 + 0.000014 * T))
    + Math.sin(2 * M * rad) * (0.019993 - 0.000101 * T) + Math.sin(3 * M * rad) * 0.000289;
  const trueLong = L0 + C;
  const omega = 125.04 - 1934.136 * T;
  const lambda = trueLong - 0.00569 - 0.00478 * Math.sin(omega * rad);
  const eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60;
  const eps = eps0 + 0.00256 * Math.cos(omega * rad);
  const decl = Math.asin(Math.sin(eps * rad) * Math.sin(lambda * rad)) * deg;
  const y = Math.tan((eps / 2) * rad) ** 2;
  const eqTime = 4 * deg * (y * Math.sin(2 * L0 * rad) - 2 * e * Math.sin(M * rad)
    + 4 * e * y * Math.sin(M * rad) * Math.cos(2 * L0 * rad)
    - 0.5 * y * y * Math.sin(4 * L0 * rad) - 1.25 * e * e * Math.sin(2 * M * rad));   // minutes
  const minutes = date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
  let lon = -((minutes + eqTime) / 4 - 180);
  lon = ((lon + 540) % 360) - 180;
  return { decl, lon };
}

/** Hauteur du Soleil (degrés) au-dessus de l'horizon en (lat, lon). */
export function sunElevation(date, lat, lon) {
  const { decl, lon: slon } = subsolar(date);
  const H = (lon - slon) * rad;
  const s = Math.sin(lat * rad) * Math.sin(decl * rad) + Math.cos(lat * rad) * Math.cos(decl * rad) * Math.cos(H);
  return Math.asin(Math.max(-1, Math.min(1, s))) * deg;
}

/** Jour / nuit en clair à partir de la hauteur du Soleil. */
export function daylight(el) {
  if (el > 6) return 'jour';
  if (el > -6) return 'ligne grise';
  if (el > -12) return 'crépuscule';
  return 'nuit';
}

/**
 * Image (data URL) de l'éclairement pour une carte Web Mercator (±85,05° de latitude) :
 * chaque pixel reçoit la hauteur du Soleil en ce point. Transparent de jour, bande dorée pour
 * la ligne grise (Soleil entre +6° et -6°, autour du lever et du coucher), sombre la nuit.
 */
export const MERCATOR_LAT = 85.0511;
export function shadeImage(date, width = 720, height = 600) {
  const { decl, lon: slon } = subsolar(date);
  const sd = Math.sin(decl * rad), cd = Math.cos(decl * rad);
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(width, height);
  const cosH = new Float32Array(width);
  for (let x = 0; x < width; x++) cosH[x] = Math.cos((-180 + (x + 0.5) * 360 / width - slon) * rad);
  for (let y = 0; y < height; y++) {
    const lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * (y + 0.5) / height))) ;   // Mercator inverse
    const sl = Math.sin(lat) * sd, cl = Math.cos(lat) * cd;
    for (let x = 0; x < width; x++) {
      const el = Math.asin(Math.max(-1, Math.min(1, sl + cl * cosH[x]))) * deg;
      const o = (y * width + x) * 4;
      if (el > 6) continue;                                   // jour : transparent
      if (el > -6) {                                          // ligne grise (±6°) : or ORSAT
        img.data[o] = 207; img.data[o + 1] = 181; img.data[o + 2] = 59;
        img.data[o + 3] = 70;
      } else {                                                // nuit, de plus en plus profonde
        img.data[o] = 4; img.data[o + 1] = 6; img.data[o + 2] = 20;
        img.data[o + 3] = el > -12 ? 120 : el > -18 ? 150 : 170;
      }
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL('image/png');
}

/** Points du grand cercle de A vers B (chemin court), coupés au passage de l'antiméridien. */
export function greatCircle(a, b, n = 128) {
  const [la1, lo1, la2, lo2] = [a[0] * rad, a[1] * rad, b[0] * rad, b[1] * rad];
  const dd = 2 * Math.asin(Math.sqrt(Math.sin((la2 - la1) / 2) ** 2
    + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2));
  if (dd === 0) return [[a]];
  const segs = [[]];
  let prev = null;
  for (let i = 0; i <= n; i++) {
    const f = i / n;
    const A = Math.sin((1 - f) * dd) / Math.sin(dd);
    const B = Math.sin(f * dd) / Math.sin(dd);
    const x = A * Math.cos(la1) * Math.cos(lo1) + B * Math.cos(la2) * Math.cos(lo2);
    const y = A * Math.cos(la1) * Math.sin(lo1) + B * Math.cos(la2) * Math.sin(lo2);
    const z = A * Math.sin(la1) + B * Math.sin(la2);
    const p = [Math.atan2(z, Math.hypot(x, y)) * deg, Math.atan2(y, x) * deg];
    if (prev && Math.abs(p[1] - prev[1]) > 180) segs.push([]);
    segs[segs.length - 1].push(p);
    prev = p;
  }
  return segs;
}
