<script>
  import { onMount, untrack } from 'svelte';
  import { api, liveSocket } from './api.js';
  import Settings from './Settings.svelte';

  // Modes proposés : libellé affiché -> mode / sous-mode ADIF
  const MODES = [
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
  ];
  const DIGITAL = ['FT8', 'FT4', 'JS8'];

  let settings = $state({});
  let radio = $state({ connected: false, freq: 0, mode: '', submode: '', ptt: false, device: '' });
  let solar = $state(null);
  let qsos = $state([]);
  let worked = $state([]);
  let showSettings = $state(false);
  let error = $state('');
  let utc = $state(new Date());

  let followTci = $state(true);
  let form = $state(blankForm());
  let startTime = null; // heure UTC figée dès la saisie de l'indicatif
  let callInput;

  function blankForm(prev = {}) {
    return {
      call: '', name: '', qth: '', gridsquare: '', comment: '',
      freqMHz: prev.freqMHz ?? '', modeLabel: prev.modeLabel ?? 'SSB',
      submode: prev.submode ?? '',
      rst_sent: defaultRst(prev.modeLabel ?? 'SSB'), rst_rcvd: defaultRst(prev.modeLabel ?? 'SSB'),
    };
  }

  function defaultRst(label) {
    if (label === 'CW' || label === 'RTTY' || label === 'PSK31') return '599';
    if (DIGITAL.includes(label)) return '';
    return '59';
  }

  // Suivi automatique de la radio via TCI.
  // Ne réagit qu'aux changements de la radio : un mode choisi à la main (ex. FT8 en USB) est respecté.
  $effect(() => {
    const { freq, mode, submode, connected } = radio;
    if (!followTci || !connected) return;
    untrack(() => {
      if (freq) form.freqMHz = (freq / 1e6).toFixed(6);
      if (mode !== lastRadioMode) {
        lastRadioMode = mode;
        if (mode && MODES.some((m) => m.label === mode)) {
          form.modeLabel = mode;
          form.rst_sent = defaultRst(mode);
          form.rst_rcvd = defaultRst(mode);
        }
      }
      form.submode = submode || '';
    });
  });
  let lastRadioMode = null;

  const pad = (n) => String(n).padStart(2, '0');
  const utcDate = (d) => `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;
  const utcTime = (d) => `${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}`;

  function fmtFreq(hz) {
    if (!hz) return '—.———.———';
    const s = String(Math.round(hz)).padStart(7, '0');
    return `${s.slice(0, -6)}.${s.slice(-6, -3)}.${s.slice(-3)}`;
  }
  const fmtDate = (d) => (d ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : '');
  const fmtTime = (t) => (t ? `${t.slice(0, 2)}:${t.slice(2, 4)}` : '');

  function onCallInput() {
    form.call = form.call.toUpperCase();
    if (form.call && !startTime) startTime = new Date();
    if (!form.call) startTime = null;
  }

  async function onCallBlur() {
    worked = form.call.length >= 3 ? await api.worked(form.call).catch(() => []) : [];
  }

  async function logQso(e) {
    e?.preventDefault();
    error = '';
    if (!form.call.trim()) { error = 'Indicatif obligatoire'; return; }
    const m = MODES.find((x) => x.label === form.modeLabel) ?? { mode: form.modeLabel, sub: '' };
    const t = startTime ?? new Date();
    const freq = parseFloat(String(form.freqMHz).replace(',', '.'));
    try {
      const q = await api.addQso({
        call: form.call, qso_date: utcDate(t), time_on: utcTime(t),
        freq: Number.isFinite(freq) ? Math.round(freq * 1e6) : null,
        mode: m.mode, submode: m.sub || (m.mode === 'SSB' ? form.submode : ''),
        rst_sent: form.rst_sent, rst_rcvd: form.rst_rcvd,
        name: form.name, qth: form.qth, gridsquare: form.gridsquare, comment: form.comment,
      });
      qsos = [q, ...qsos];
      form = blankForm(form);
      startTime = null;
      worked = [];
      callInput?.focus();
    } catch (err) {
      error = err.message;
    }
  }

  function clearForm() {
    form = blankForm(form);
    startTime = null;
    worked = [];
    callInput?.focus();
  }

  async function removeQso(q) {
    if (!confirm(`Supprimer le QSO avec ${q.call} ?`)) return;
    await api.deleteQso(q.id);
    qsos = qsos.filter((x) => x.id !== q.id);
  }

  function onKey(e) {
    if (e.key === 'Escape') clearForm();
  }

  async function refreshSolar() {
    solar = await api.solar().catch(() => solar);
  }

  onMount(() => {
    api.settings().then((s) => {
      settings = s;
      if (!s.callsign || !s.locator) showSettings = true;
    });
    api.qsos().then((q) => (qsos = q));
    refreshSolar();
    const stop = liveSocket((msg) => { if (msg.type === 'radio') radio = msg.data; });
    const clock = setInterval(() => (utc = new Date()), 1000);
    const sol = setInterval(refreshSolar, 15 * 60 * 1000);
    callInput?.focus();
    return () => { stop(); clearInterval(clock); clearInterval(sol); };
  });

  const kClass = (k) => (k == null ? '' : k >= 5 ? 'bad' : k >= 4 ? 'warn' : 'ok');
</script>

<svelte:window onkeydown={onKey} />

<header class="topbar">
  <div class="brand">
    <span class="logo">ORSAT</span><span class="logo-sub">-LOG</span>
    {#if settings.callsign}
      <span class="station mono">{settings.callsign}{settings.locator ? ` · ${settings.locator}` : ''}</span>
    {/if}
  </div>

  <div class="solar" title="Données solaires (hamqsl.com)">
    {#if solar}
      <span>SFI <b>{solar.sfi ?? '—'}</b></span>
      <span>A <b>{solar.a_index ?? '—'}</b></span>
      <span>K <b class={kClass(solar.k_index)}>{solar.k_index ?? '—'}</b></span>
      {#if solar.xray}<span>X-ray <b>{solar.xray}</b></span>{/if}
    {:else}
      <span class="muted">Données solaires indisponibles</span>
    {/if}
  </div>

  <div class="right">
    <span class="clock mono" title="Heure UTC">{pad(utc.getUTCHours())}:{pad(utc.getUTCMinutes())}:{pad(utc.getUTCSeconds())} UTC</span>
    <a class="btn" href="/api/export/adif" title="Exporter tout le carnet au format ADIF">Export ADIF</a>
    <button onclick={() => (showSettings = true)} title="Réglages de la station et de la connexion TCI">Réglages</button>
  </div>
</header>

<main class="layout">
  <section class="panel radio">
    <h2 class="panel-title">Transceiver</h2>
    <div class="tci-status">
      <span class="dot" class:on={radio.connected}></span>
      {#if radio.connected}
        TCI connecté {radio.device ? `· ${radio.device}` : ''}
      {:else}
        TCI déconnecté ({settings.tci_host}:{settings.tci_port})
      {/if}
      {#if radio.ptt}<span class="tx">TX</span>{/if}
    </div>
    <div class="freq mono">{fmtFreq(radio.freq)}<small> MHz</small></div>
    <div class="radio-mode">
      {radio.modulation ? radio.modulation.toUpperCase() : '—'}
    </div>
    <label class="follow">
      <input type="checkbox" bind:checked={followTci} /> Suivre la radio
    </label>
  </section>

  <section class="panel entry">
    <h2 class="panel-title">Nouveau QSO</h2>
    <form onsubmit={logQso}>
      <div class="grid">
        <div class="f-call">
          <label for="call">Indicatif</label>
          <input id="call" class="mono call" bind:this={callInput} bind:value={form.call}
                 oninput={onCallInput} onblur={onCallBlur} autocomplete="off" spellcheck="false" />
        </div>
        <div>
          <label for="freq">Fréquence (MHz)</label>
          <input id="freq" class="mono" bind:value={form.freqMHz} disabled={followTci && radio.connected} />
        </div>
        <div>
          <label for="mode">Mode</label>
          <select id="mode" bind:value={form.modeLabel}
                  onchange={() => { form.rst_sent = defaultRst(form.modeLabel); form.rst_rcvd = defaultRst(form.modeLabel); }}>
            {#each MODES as m}<option value={m.label}>{m.label}</option>{/each}
          </select>
        </div>
        <div>
          <label for="rsts">RST envoyé</label>
          <input id="rsts" class="mono" bind:value={form.rst_sent} />
        </div>
        <div>
          <label for="rstr">RST reçu</label>
          <input id="rstr" class="mono" bind:value={form.rst_rcvd} />
        </div>
        <div>
          <label for="grid">Locator</label>
          <input id="grid" class="mono" bind:value={form.gridsquare}
                 oninput={() => (form.gridsquare = form.gridsquare.toUpperCase())} maxlength="8" />
        </div>
        <div>
          <label for="name">Nom</label>
          <input id="name" bind:value={form.name} />
        </div>
        <div>
          <label for="qth">QTH</label>
          <input id="qth" bind:value={form.qth} />
        </div>
        <div class="f-comment">
          <label for="comment">Commentaire</label>
          <input id="comment" bind:value={form.comment} />
        </div>
      </div>
      <div class="actions">
        {#if error}<span class="error">{error}</span>{/if}
        <span class="hint">Entrée = enregistrer · Échap = effacer</span>
        <button type="button" onclick={clearForm}>Effacer</button>
        <button type="submit" class="primary">Enregistrer</button>
      </div>
    </form>

    {#if worked.length}
      <div class="worked">
        <b>Déjà contacté {worked.length} fois :</b>
        {#each worked.slice(0, 6) as w}
          <span class="chip">{fmtDate(w.qso_date)} {w.band} {w.mode}</span>
        {/each}
      </div>
    {/if}
  </section>

  <section class="panel log">
    <h2 class="panel-title">Carnet de trafic <span class="count">{qsos.length} QSO</span></h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th><th>UTC</th><th>Indicatif</th><th>Bande</th><th>Fréq.</th><th>Mode</th>
            <th>Env.</th><th>Reçu</th><th>Locator</th><th>Dist.</th><th>Az.</th>
            <th title="Flux solaire / indice K au moment du QSO">SFI / K</th><th>Nom</th><th></th>
          </tr>
        </thead>
        <tbody>
          {#each qsos as q (q.id)}
            <tr>
              <td>{fmtDate(q.qso_date)}</td>
              <td class="mono">{fmtTime(q.time_on)}</td>
              <td class="mono call-cell">{q.call}</td>
              <td>{q.band}</td>
              <td class="mono">{q.freq ? (q.freq / 1e6).toFixed(3) : ''}</td>
              <td>{q.submode || q.mode}</td>
              <td class="mono">{q.rst_sent}</td>
              <td class="mono">{q.rst_rcvd}</td>
              <td class="mono">{q.gridsquare}</td>
              <td>{q.distance_km != null ? `${q.distance_km} km` : ''}</td>
              <td>{q.bearing != null ? `${q.bearing}°` : ''}</td>
              <td>{q.sfi ?? ''}{q.k_index != null ? ` / ${q.k_index}` : ''}</td>
              <td>{q.name}</td>
              <td><button class="ghost del" title="Supprimer ce QSO" onclick={() => removeQso(q)}>✕</button></td>
            </tr>
          {:else}
            <tr><td colspan="14" class="muted empty">Aucun QSO pour l'instant.</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
</main>

{#if showSettings}
  <Settings {settings} onclose={() => (showSettings = false)}
            onsaved={(s) => { settings = s; showSettings = false; }} />
{/if}

<style>
  .topbar {
    display: flex; align-items: center; gap: 24px;
    padding: 10px 18px;
    border-bottom: 1px solid var(--panel-edge);
    background: linear-gradient(180deg, rgba(207, 181, 59, 0.1), transparent);
  }
  .brand { display: flex; align-items: baseline; gap: 4px; }
  .logo { color: var(--gold); font-size: 1.5rem; font-weight: 700; letter-spacing: 0.1em; }
  .logo-sub { color: var(--gold-soft); font-size: 1.1rem; font-weight: 600; }
  .station { margin-left: 14px; color: var(--text); }
  .solar { display: flex; gap: 16px; font-size: 0.9rem; color: var(--muted); }
  .solar b { color: var(--text); }
  .right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
  .clock { color: var(--gold); font-size: 1.05rem; margin-right: 6px; }
  .ok { color: var(--ok) !important; } .warn { color: var(--warn) !important; } .bad { color: var(--bad) !important; }
  .muted { color: var(--muted); }

  .layout {
    display: grid;
    grid-template-columns: 300px 1fr;
    grid-template-rows: auto 1fr;
    gap: 14px; padding: 14px;
    height: calc(100vh - 60px);
  }
  .radio { grid-row: 1; }
  .entry { grid-row: 1; }
  .log { grid-column: 1 / -1; display: flex; flex-direction: column; min-height: 0; }

  .tci-status { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--muted); }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--bad); box-shadow: 0 0 6px var(--bad); }
  .dot.on { background: var(--ok); box-shadow: 0 0 6px var(--ok); }
  .tx { margin-left: auto; color: #fff; background: var(--bad); padding: 1px 8px; border-radius: 4px; font-weight: 700; }
  .freq { font-size: 2rem; color: var(--gold); margin: 14px 0 4px; text-shadow: 0 0 10px rgba(207, 181, 59, 0.35); }
  .freq small { font-size: 0.9rem; color: var(--gold-soft); }
  .radio-mode { color: var(--text); font-size: 1rem; letter-spacing: 0.1em; }
  .follow { display: flex; align-items: center; gap: 8px; margin-top: 16px; text-transform: none; font-size: 0.85rem; }
  .follow input { width: auto; }

  .grid { display: grid; grid-template-columns: 1.4fr 1fr 0.8fr 0.6fr 0.6fr 0.8fr; gap: 10px; }
  .f-comment { grid-column: span 4; }
  .call { font-size: 1.25rem; font-weight: 700; color: var(--gold); letter-spacing: 0.05em; }
  .actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 12px; }
  .hint { color: var(--muted); font-size: 0.78rem; margin-right: auto; }
  .error { color: var(--bad); font-weight: 600; }
  .worked { margin-top: 10px; font-size: 0.85rem; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; color: var(--warn); }
  .chip { border: 1px solid var(--panel-edge); border-radius: 12px; padding: 1px 8px; color: var(--text); }

  .count { color: var(--muted); font-weight: 400; margin-left: 8px; }
  .table-wrap { overflow: auto; flex: 1; min-height: 0; }
  .call-cell { color: var(--gold); font-weight: 600; }
  .del { padding: 0 6px; color: var(--muted); }
  .del:hover { color: var(--bad); }
  .empty { text-align: center; padding: 30px; }
</style>
