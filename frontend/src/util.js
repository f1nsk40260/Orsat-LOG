// Outils communs : dates UTC, formats, modes.

export const pad = (n) => String(n).padStart(2, '0');

/** Date UTC -> AAAAMMJJ */
export const dayOf = (d = new Date()) =>
  `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;
/** Date UTC -> HHMMSS */
export const timeOf = (d = new Date()) =>
  `${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}`;

/** AAAAMMJJ -> Date (minuit UTC) */
export const parseDay = (s) => new Date(Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8)));
/** décale un jour AAAAMMJJ de n jours */
export const addDays = (s, n) => {
  const d = parseDay(s);
  d.setUTCDate(d.getUTCDate() + n);
  return dayOf(d);
};

export const JOURS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
export const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
  'août', 'septembre', 'octobre', 'novembre', 'décembre'];

/** AAAAMMJJ -> « mardi 20 octobre 2026 » */
export function longDay(s) {
  const d = parseDay(s);
  return `${JOURS[d.getUTCDay()]} ${d.getUTCDate()} ${MOIS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export const fmtDate = (d) => (d ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : '');
export const fmtTime = (t) => (t ? `${t.slice(0, 2)}:${t.slice(2, 4)}` : '');

export function fmtFreq(hz) {
  if (!hz) return '—.———.———';
  const s = String(Math.round(hz)).padStart(7, '0');
  return `${s.slice(0, -6)}.${s.slice(-6, -3)}.${s.slice(-3)}`;
}

// Modes proposés : libellé affiché -> mode / sous-mode ADIF
export const MODES = [
  { label: 'SSB', mode: 'SSB', sub: '' },
  { label: 'CW', mode: 'CW', sub: '' },
  { label: 'AM', mode: 'AM', sub: '' },
  { label: 'FM', mode: 'FM', sub: '' },
  { label: 'FT8', mode: 'FT8', sub: '' },
  { label: 'FT4', mode: 'MFSK', sub: 'FT4' },
  { label: 'RTTY', mode: 'RTTY', sub: '' },
  { label: 'PSK31', mode: 'PSK', sub: 'PSK31' },
  { label: 'JS8', mode: 'MFSK', sub: 'JS8' },
  { label: 'SSTV', mode: 'SSTV', sub: '' },
  { label: 'DRM', mode: 'DRM', sub: '' },
];

export function defaultRst(label, kind = 'QSO') {
  if (kind === 'SWL') return '';
  if (label === 'CW' || label === 'RTTY' || label === 'PSK31') return '599';
  if (['FT8', 'FT4', 'JS8', 'DRM'].includes(label)) return '';
  return '59';
}

export const kClass = (k) => (k == null ? '' : k >= 5 ? 'bad' : k >= 4 ? 'warn' : 'ok');
