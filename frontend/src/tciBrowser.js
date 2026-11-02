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

// Pourquoi la liaison tardait (alors qu'un logiciel natif comme Orsat SDR se relie
// aussitôt) : les navigateurs freinent eux-mêmes les WebSocket qui échouent.
//  - Firefox retarde chaque nouvel essai vers la même adresse + chemin
//    (×1,5 à chaque échec, jusqu'à 60 s) ;
//  - Chromium retarde toutes les WebSocket de l'onglet de 1 à 5 s dès qu'il compte
//    plus d'une quinzaine d'échecs sur les 2 à 4 dernières minutes.
// Carnet ouvert avant l'applet TCI d'AetherSDR = des dizaines d'échecs, puis jusqu'à
// une minute d'attente une fois AetherSDR prêt. Parades :
//  - chaque nouvel essai vise un chemin différent (AetherSDR ignore le chemin), ce qui
//    évite le frein de Firefox ;
//  - essais rapprochés (2 s) pendant 20 s après une coupure ou au démarrage, puis
//    espacés (20 s) pour rester sous le seuil de Chromium ;
//  - essai immédiat dès que l'opérateur revient sur le carnet (onglet, fenêtre,
//    souris), ou sur le bouton « Réessayer ».
const FAST_MS = 2000;                  // intervalle des essais rapprochés
const FAST_FOR_MS = 20000;             // durée de la phase d'essais rapprochés
const SLOW_MS = 20000;                 // intervalle ensuite
let attempt = 0;                       // essais ratés depuis la dernière liaison réussie
let lostAt = 0;                        // début de la phase d'essais rapprochés
let lastTry = 0;                       // heure du dernier essai lancé

function nextDelay() {
  return Date.now() - lostAt < FAST_FOR_MS ? FAST_MS : SLOW_MS;
}

function schedule(ms) {
  clearTimeout(timer);
  timer = setTimeout(connect, ms);
}

function connect() {
  clearTimeout(timer);
  timer = null;
  if (!cfg || ws) return;               // arrêté, ou un essai est déjà en cours
  lastTry = Date.now();
  // 1er essai à la racine ; les suivants sur /orsat-log/N (voir plus haut)
  const path = attempt ? `/orsat-log/${attempt}` : '';
  const url = `ws://${cfg.host}:${cfg.port}${path}`;
  let opened = false;
  let sock;
  try {
    sock = new WebSocket(url);
  } catch (e) {
    set({ error: String(e).slice(0, 120) });
    schedule(nextDelay());
    return;
  }
  ws = sock;
  sock.onopen = () => { opened = true; attempt = 0; set({ connected: true, error: '' }); };
  sock.onmessage = (ev) => {
    if (typeof ev.data !== 'string') return;            // audio / IQ ignorés
    for (const c of ev.data.split(';')) if (c.trim()) handle(c.trim());
  };
  sock.onclose = () => {
    if (ws !== sock) return;
    ws = null;
    if (!opened) attempt += 1;
    set({
      connected: false, ready: false,
      error: opened ? 'liaison TCI coupée' : `pas de serveur TCI sur ${cfg.host}:${cfg.port} (ce PC)`,
    });
    // coupure franche (AetherSDR relancé) : on réessaie presque tout de suite
    if (opened) lostAt = Date.now();
    if (cfg) schedule(opened ? 300 : nextDelay());
  };
}

/** Réessaie tout de suite si la liaison est coupée (bouton « Réessayer »). */
export function tciRetryNow() {
  if (cfg && !ws) connect();
}

// L'opérateur revient sur le carnet : essai immédiat (au plus un toutes les 2 s)
function onBack() {
  if (document.visibilityState === 'visible' && Date.now() - lastTry >= FAST_MS) tciRetryNow();
}
const BACK_EVENTS = [[window, 'focus'], [document, 'visibilitychange'], [document, 'pointermove'],
                     [document, 'pointerdown'], [document, 'wheel']];

/** Démarre (ou redémarre) la liaison. onState reçoit l'état complet à chaque changement. */
export function startTci({ host = '127.0.0.1', port = 50001, trx = 0 } = {}, onState) {
  stopTci();
  cfg = { host, port: Number(port), trx: String(trx) };
  onChange = onState || (() => {});
  attempt = 0;
  lostAt = Date.now();
  for (const [t, e] of BACK_EVENTS) t.addEventListener(e, onBack, { passive: true });
  connect();
}

export function stopTci() {
  clearTimeout(timer);
  for (const [t, e] of BACK_EVENTS) t.removeEventListener(e, onBack);
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
