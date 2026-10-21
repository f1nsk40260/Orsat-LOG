// Client TCI exécuté dans le navigateur.
//
// Le carnet tourne sur le PC ORSAT (serveur), mais AetherSDR tourne sur le PC de
// l'opérateur : c'est donc l'interface, ouverte dans le navigateur de ce PC, qui
// se connecte à ws://127.0.0.1:50001. Les navigateurs l'autorisent vers localhost,
// même depuis une page https. 

// modulation TCI -> [mode ADIF, sous-mode ADIF]
const TCI_MODES = {
  usb: ['SSB', 'USB'], lsb: ['SSB', 'LSB'], cw: ['CW', ''], cwr: ['CW', ''], rtty: ['RTTY', ''],
  am: ['AM', ''], sam: ['AM', ''], dsb: ['AM', ''], fm: ['FM', ''], nfm: ['FM', ''], wfm: ['FM', ''],
  digu: ['', ''], digl: ['', ''], drm: ['DRM', ''],
};

const empty = () => ({
  connected: false, ready: false, device: '', protocol: '', freq: 0,
  modulation: '', mode: '', submode: '', ptt: false, error: '',
});

let ws = null;
let timer = null;
let cfg = null;
let state = empty();
let onChange = () => {};

function set(changes) {
  let changed = false;
  for (const [k, v] of Object.entries(changes)) {
    if (state[k] !== v) { state[k] = v; changed = true; }
  }
  if (changed) onChange({ ...state });
}

function handle(cmd) {
  const i = cmd.indexOf(':');
  const name = (i < 0 ? cmd : cmd.slice(0, i)).trim().toLowerCase();
  const parts = i < 0 ? [] : cmd.slice(i + 1).split(',').map((a) => a.trim());
  if (name === 'ready') set({ ready: true });
  else if (name === 'device' && parts.length) set({ device: parts[0] });
  else if (name === 'protocol' && parts.length) set({ protocol: parts.join(',') });
  else if (name === 'vfo' && parts.length >= 3) {
    // vfo:récepteur,canal,fréquence — récepteur choisi, canal A
    if (parts[0] === cfg.trx && parts[1] === '0') {
      const f = Math.round(Number(parts[2]));
      if (Number.isFinite(f)) set({ freq: f });
    }
  } else if (name === 'modulation' && parts.length >= 2 && parts[0] === cfg.trx) {
    const mod = parts[1].toLowerCase();
    const [mode, submode] = TCI_MODES[mod] ?? [mod.toUpperCase(), ''];
    set({ modulation: mod, mode, submode });
  } else if (name === 'trx' && parts.length >= 2 && parts[0] === cfg.trx) {
    set({ ptt: parts[1].toLowerCase() === 'true' });
  }
}

function connect() {
  if (!cfg) return;
  const url = `ws://${cfg.host}:${cfg.port}`;
  let opened = false;
  try {
    ws = new WebSocket(url);
  } catch (e) {
    set({ error: String(e).slice(0, 120) });
    timer = setTimeout(connect, 5000);
    return;
  }
  ws.onopen = () => { opened = true; set({ connected: true, error: '' }); };
  ws.onmessage = (ev) => {
    if (typeof ev.data !== 'string') return;            // audio / IQ ignorés
    for (const c of ev.data.split(';')) if (c.trim()) handle(c.trim());
  };
  ws.onclose = () => {
    ws = null;
    set({
      connected: false, ready: false,
      error: opened ? 'liaison TCI coupée' : `pas de serveur TCI sur ${cfg.host}:${cfg.port} (ce PC)`,
    });
    if (cfg) timer = setTimeout(connect, 5000);
  };
}

/** Démarre (ou redémarre) la liaison. onState reçoit l'état complet à chaque changement. */
export function startTci({ host = '127.0.0.1', port = 50001, trx = 0 } = {}, onState) {
  stopTci();
  cfg = { host, port: Number(port), trx: String(trx) };
  onChange = onState || (() => {});
  connect();
}

export function stopTci() {
  clearTimeout(timer);
  const old = ws;
  cfg = null;
  ws = null;
  if (old) { old.onclose = null; old.close(); }
  state = empty();
  onChange({ ...state });
}

export const tciActive = () => !!cfg;

/** Règle le transceiver (récepteur suivi, VFO A). Faux si la liaison n'est pas ouverte. */
export function tciTune(freq, modulation) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  let text = `vfo:${cfg.trx},0,${Math.round(freq)};`;
  if (modulation) text += `modulation:${cfg.trx},${modulation.toLowerCase()};`;
  ws.send(text);
  return true;
}

/** Mode du carnet (ADIF) -> modulation TCI, comme /api/tune côté serveur. */
export function tciModeFor(q) {
  const m = (q.submode || q.mode || '').toUpperCase();
  const direct = { USB: 'usb', LSB: 'lsb', CW: 'cw', AM: 'am', FM: 'nfm' }[m];
  if (direct) return direct;
  if (m === 'SSB') return q.freq < 10_000_000 ? 'lsb' : 'usb';
  return m ? 'usb' : '';             // modes numériques : écoute en USB
}
