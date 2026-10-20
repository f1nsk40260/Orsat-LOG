async function req(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

export const api = {
  settings: () => req('GET', '/api/settings'),
  saveSettings: (s) => req('PUT', '/api/settings', s),
  solar: () => req('GET', '/api/solar'),
  weather: () => req('GET', '/api/weather'),
  qsos: (limit = 200) => req('GET', `/api/qsos?limit=${limit}`),
  addQso: (q) => req('POST', '/api/qsos', q),
  deleteQso: (id) => req('DELETE', `/api/qsos/${id}`),
  worked: (call) => req('GET', `/api/worked/${encodeURIComponent(call)}`),
  // QSO de groupe
  sessionNames: () => req('GET', '/api/sessions/names'),
  regulars: (name) => req('GET', `/api/sessions/regulars?name=${encodeURIComponent(name)}`),
  createSession: (s) => req('POST', '/api/sessions', s),
  session: (id) => req('GET', `/api/sessions/${id}`),
  updateSession: (id, s) => req('PUT', `/api/sessions/${id}`, s),
  deleteSession: (id) => req('DELETE', `/api/sessions/${id}`),
  // agenda
  today: () => req('GET', '/api/today'),
  day: (day) => req('GET', `/api/day/${day}`),
  saveNote: (day, text) => req('PUT', `/api/day/${day}/note`, { text }),
  month: (month) => req('GET', `/api/month/${month}`),
};

/** WebSocket temps réel avec reconnexion automatique. */
export function liveSocket(onMessage) {
  let ws;
  let closed = false;
  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch {} };
    ws.onclose = () => { if (!closed) setTimeout(open, 2000); };
  };
  open();
  return () => { closed = true; ws?.close(); };
}
