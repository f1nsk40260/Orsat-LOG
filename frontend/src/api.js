// Adresses relatives : le carnet fonctionne à la racine (bureau) comme derrière
// https://orsat.ddns.net/log/.
async function req(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) {              // session expirée : page de connexion
    location.href = 'login';
    throw new Error('Connexion requise');
  }
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

export const api = {
  info: () => req('GET', 'api/info'),
  websdrMirror: (freq, modulation) => req('POST', 'api/websdr/mirror', { freq, modulation }),
  logout: () => req('POST', 'api/logout'),
  qsoContext: (id) => req('GET', `api/qsos/${id}/context`),
  eibi: (freq, date = '', time = '') => req('GET', `api/eibi?freq=${freq}${date ? `&date=${date}&time=${time}` : ''}`),
  qrzLookup: (call) => req('GET', `api/qrz/lookup/${encodeURIComponent(call)}`),
  qsoIono: (id, refresh = false) => req('GET', `api/qsos/${id}/iono${refresh ? '?refresh=true' : ''}`),
  settings: () => req('GET', 'api/settings'),
  solar: () => req('GET', 'api/solar'),
  spacewx: () => req('GET', 'api/spacewx'),
  openBands: () => req('GET', 'api/openbands'),
  skipMap: () => req('GET', 'api/skipmap'),
  listenMap: () => req('GET', 'api/listenmap'),
  publicListenMap: () => req('GET', 'api/public/listenmap'),
  analysisQrn: (days = 90) => req('GET', `api/analysis/qrn?days=${days}`),
  analysis: (kind = 'QSO', band = '') => req('GET', `api/analysis?kind=${kind}&band=${encodeURIComponent(band)}`),
  weather: () => req('GET', 'api/weather'),
  lightning: () => req('GET', 'api/lightning'),
  qsos: (limit = 200) => req('GET', `api/qsos?limit=${limit}`),
  addQso: (q) => req('POST', 'api/qsos', q),
  updateQso: (id, q) => req('PUT', `api/qsos/${id}`, q),
  deleteQso: (id, qrzToo = false) => req('DELETE', `api/qsos/${id}${qrzToo ? '?qrz_too=true' : ''}`),
  tune: (q) => req('POST', 'api/tune', { freq: q.freq, mode: q.mode || '', submode: q.submode || '', kind: q.kind || '' }),
  worked: (call) => req('GET', `api/worked/${encodeURIComponent(call)}`),
  // QSO de groupe
  sessionNames: () => req('GET', 'api/sessions/names'),
  regulars: (name) => req('GET', `api/sessions/regulars?name=${encodeURIComponent(name)}`),
  createSession: (s) => req('POST', 'api/sessions', s),
  saveTemplate: (s) => req('POST', 'api/templates', s),
  deleteTemplate: (name) => req('DELETE', `api/templates/${encodeURIComponent(name)}`),
  session: (id) => req('GET', `api/sessions/${id}`),
  updateSession: (id, s) => req('PUT', `api/sessions/${id}`, s),
  deleteSession: (id) => req('DELETE', `api/sessions/${id}`),
  // agenda
  today: () => req('GET', 'api/today'),
  day: (day) => req('GET', `api/day/${day}`),
  saveNote: (day, text) => req('PUT', `api/day/${day}/note`, { text }),
  month: (month) => req('GET', `api/month/${month}`),
};

/** WebSocket temps réel avec reconnexion automatique. */
export function liveSocket(onMessage) {
  let ws;
  let closed = false;
  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = new URL('ws', location.href);
    url.protocol = proto + ':';
    ws = new WebSocket(url.href);
    ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch {} };
    ws.onclose = (e) => {
      if (e.code === 4401) { location.href = 'login'; return; }   // session expirée
      if (!closed) setTimeout(open, 2000);
    };
  };
  open();
  return () => { closed = true; ws?.close(); };
}

/**
 * Supprime une entrée après confirmation. Pour un contact présent dans le logbook QRZ.com,
 * l'opérateur choisit s'il faut aussi l'y supprimer (définitif chez QRZ). Renvoie vrai si supprimée.
 */
export async function deleteEntry(q, message) {
  if (!confirm(message || `Supprimer l'entrée ${q.call} ?`)) return false;
  let qrzToo = false;
  if (q.kind !== 'SWL' && q.qrz_logid) {
    qrzToo = confirm(`${q.call} est aussi dans ton logbook QRZ.com.\n\n` +
      'OK : le supprimer AUSSI chez QRZ (définitif)\n' +
      'Annuler : le garder chez QRZ (il ne reviendra pas dans le carnet)');
  }
  await api.deleteQso(q.id, qrzToo);
  return true;
}
