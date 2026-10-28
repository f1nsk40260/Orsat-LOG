// Locator Maidenhead (4, 6 ou 8 caractères) -> centre du carré (lat, lon) ; distance et azimut orthodromiques.
export function locToLatLon(loc) {
  const s = (loc || '').trim().toUpperCase();
  if (!/^[A-R]{2}[0-9]{2}([A-X]{2}([0-9]{2})?)?$/.test(s)) return null;
  let lon = (s.charCodeAt(0) - 65) * 20 - 180, lat = (s.charCodeAt(1) - 65) * 10 - 90;
  lon += +s[2] * 2; lat += +s[3];
  let w = 2, h = 1;
  if (s.length >= 6) { w = 2 / 24; h = 1 / 24; lon += (s.charCodeAt(4) - 65) * w; lat += (s.charCodeAt(5) - 65) * h; }
  if (s.length === 8) { w /= 10; h /= 10; lon += +s[6] * w; lat += +s[7] * h; }
  return [lat + h / 2, lon + w / 2];
}

export function distAz(a, b) {
  const r = Math.PI / 180, [la1, lo1, la2, lo2] = [a[0] * r, a[1] * r, b[0] * r, b[1] * r];
  const c = Math.sin(la1) * Math.sin(la2) + Math.cos(la1) * Math.cos(la2) * Math.cos(lo2 - lo1);
  const d = 6371 * Math.acos(Math.max(-1, Math.min(1, c)));
  const az = Math.atan2(Math.sin(lo2 - lo1) * Math.cos(la2), Math.cos(la1) * Math.sin(la2) - Math.sin(la1) * Math.cos(la2) * Math.cos(lo2 - lo1));
  return [d, (az / r + 360) % 360];
}

const DIRS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSO', 'SO', 'OSO', 'O', 'ONO', 'NO', 'NNO'];
export const dirName = (az) => DIRS[Math.round(az / 22.5) % 16];
