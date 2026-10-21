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
  settings: () => req('GET', 'api/settings'),
  solar: () => req('GET', 'api/solar'),
  weather: () => req('GET', 'api/weather'),
  qsos: (limit = 200) => req('GET', `api/qsos?limit=${limit}`),
  addQso: (q) => req('POST', 'api/qsos', q),
  updateQso: (id, q) => req('PUT', `api/qsos/${id}`, q),
  deleteQso: (id) => req('DELETE', `api/qsos/${id}`),
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
