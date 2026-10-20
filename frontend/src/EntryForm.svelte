<script>
  import { untrack } from 'svelte';
  import { api } from './api.js';
  import { MODES, defaultRst, dayOf, timeOf, fmtDate } from './util.js';
  import GroupSession from './GroupSession.svelte';

  let { radio, onlogged, sessions = [] } = $props();

  let kind = $state('QSO');        // QSO = contact réalisé, SWL = écoute, GRP = QSO de groupe
  let followTci = $state(true);
  let form = $state(blank());
  let worked = $state([]);
  let error = $state('');
  let startTime = null;            // heure UTC figée dès la frappe de l'indicatif
  let callInput = $state();
  let lastRadioMode = null;

  function blank(prev = {}) {
    const label = prev.modeLabel ?? 'SSB';
    return {
      call: '', name: '', qth: '', gridsquare: '', comment: '',
      freqMHz: prev.freqMHz ?? '', modeLabel: label, submode: prev.submode ?? '',
      rst_sent: defaultRst(label, kind), rst_rcvd: defaultRst(label, kind),
    };
  }

  // Suivi de la radio : ne réagit qu'aux changements de la radio (un mode choisi à la main est respecté)
  $effect(() => {
    const { freq, mode, submode, connected } = radio;
    if (!followTci || !connected) return;
    untrack(() => {
      if (freq) form.freqMHz = (freq / 1e6).toFixed(6);
      if (mode !== lastRadioMode) {
        lastRadioMode = mode;
        if (mode && MODES.some((m) => m.label === mode)) setMode(mode);
      }
      form.submode = submode || '';
    });
  });

  function setMode(label) {
    form.modeLabel = label;
    form.rst_sent = defaultRst(label, kind);
    form.rst_rcvd = defaultRst(label, kind);
  }

  function setKind(k) {
    kind = k;
    if (k === 'GRP') return;
    form.rst_sent = defaultRst(form.modeLabel, k);
    form.rst_rcvd = defaultRst(form.modeLabel, k);
    worked = [];
    callInput?.focus();
  }

  function onCallInput() {
    if (kind === 'QSO') form.call = form.call.toUpperCase();
    if (form.call && !startTime) startTime = new Date();
    if (!form.call) startTime = null;
  }

  async function onCallBlur() {
    worked = kind === 'QSO' && form.call.length >= 3 ? await api.worked(form.call).catch(() => []) : [];
  }

  async function submit(e) {
    e?.preventDefault();
    error = '';
    if (!form.call.trim()) { error = kind === 'SWL' ? 'Station entendue obligatoire' : 'Indicatif obligatoire'; return; }
    const m = MODES.find((x) => x.label === form.modeLabel) ?? { mode: form.modeLabel, sub: '' };
    const t = startTime ?? new Date();
    const freq = parseFloat(String(form.freqMHz).replace(',', '.'));
    try {
      const q = await api.addQso({
        kind, call: form.call, qso_date: dayOf(t), time_on: timeOf(t),
        freq: Number.isFinite(freq) ? Math.round(freq * 1e6) : null,
        mode: m.mode, submode: m.sub || (m.mode === 'SSB' ? form.submode : ''),
        rst_sent: form.rst_sent, rst_rcvd: form.rst_rcvd,
        name: form.name, qth: form.qth, gridsquare: form.gridsquare, comment: form.comment,
      });
      form = blank(form);
      startTime = null;
      worked = [];
      onlogged?.(q);
      callInput?.focus();
    } catch (err) {
      error = err.message;
    }
  }

  export function clear() {
    if (kind === 'GRP') return;
    form = blank(form);
    startTime = null;
    worked = [];
    error = '';
    callInput?.focus();
  }

  export function focus() { callInput?.focus(); }
</script>

<section class="panel entry" class:swl={kind === 'SWL'} class:grp={kind === 'GRP'}>
  <div class="head">
    <h2 class="panel-title">{kind === 'SWL' ? 'Nouvelle écoute' : kind === 'GRP' ? 'QSO de groupe' : 'Nouveau QSO'}</h2>
    <div class="kind" role="group" aria-label="Type d'entrée">
      <button type="button" class:active={kind === 'QSO'} onclick={() => setKind('QSO')}
              title="Contact bilatéral réalisé">QSO</button>
      <button type="button" class:active={kind === 'SWL'} onclick={() => setKind('SWL')}
              title="Écoute d'une station (Short Wave Listening)">SWL</button>
      <button type="button" class:active={kind === 'GRP'} onclick={() => setKind('GRP')}
              title="QSO de groupe / table ronde : nom, créneau horaire, stations participantes">Groupe</button>
    </div>
    {#if kind !== 'GRP'}
      <label class="follow" title="Fréquence et mode repris automatiquement de la radio (TCI)">
        <input type="checkbox" bind:checked={followTci} /> Suivre la radio
      </label>
    {/if}
  </div>

  {#if kind === 'GRP'}
    <GroupSession {radio} {sessions} onchanged={() => onlogged?.()} />
  {:else}
  <form onsubmit={submit}>
    <div class="grid">
      <div class="f-call">
        <label for="call">{kind === 'SWL' ? 'Station entendue' : 'Indicatif'}</label>
        <input id="call" class="mono call" bind:this={callInput} bind:value={form.call}
               oninput={onCallInput} onblur={onCallBlur} autocomplete="off" spellcheck="false" />
      </div>
      <div>
        <label for="freq">Fréquence (MHz)</label>
        <input id="freq" class="mono" bind:value={form.freqMHz} disabled={followTci && radio.connected} />
      </div>
      <div>
        <label for="mode">Mode</label>
        <select id="mode" value={form.modeLabel} onchange={(e) => setMode(e.currentTarget.value)}>
          {#each MODES as m}<option value={m.label}>{m.label}</option>{/each}
        </select>
      </div>
      {#if kind === 'QSO'}
        <div>
          <label for="rsts">RST envoyé</label>
          <input id="rsts" class="mono" bind:value={form.rst_sent} />
        </div>
        <div>
          <label for="rstr">RST reçu</label>
          <input id="rstr" class="mono" bind:value={form.rst_rcvd} />
        </div>
      {:else}
        <div class="span2">
          <label for="sinpo">SINPO / SIO</label>
          <input id="sinpo" class="mono" bind:value={form.rst_rcvd} maxlength="5"
                 title="Signal, Interférence, Bruit (Noise), Propagation, appréciation globale (Overall) — 1 à 5" />
        </div>
      {/if}
      <div>
        <label for="grid">{kind === 'SWL' ? 'Loc. émetteur' : 'Locator'}</label>
        <input id="grid" class="mono" bind:value={form.gridsquare}
               oninput={() => (form.gridsquare = form.gridsquare.toUpperCase())} maxlength="8" />
      </div>
      {#if kind === 'QSO'}
        <div>
          <label for="name">Nom</label>
          <input id="name" bind:value={form.name} />
        </div>
      {/if}
      <div>
        <label for="qth">{kind === 'SWL' ? 'Émetteur (site)' : 'QTH'}</label>
        <input id="qth" bind:value={form.qth} />
      </div>
      <div class="f-comment" class:wide={kind === 'SWL'}>
        <label for="comment">{kind === 'SWL' ? 'Programme / langue / remarques' : 'Commentaire'}</label>
        <input id="comment" bind:value={form.comment} />
      </div>
    </div>
    <div class="actions">
      {#if error}<span class="error">{error}</span>{/if}
      <span class="hint">Entrée = enregistrer · Échap = effacer</span>
      <button type="button" onclick={clear}>Effacer</button>
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
  {/if}
</section>

<style>
  .head { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
  .head .panel-title { margin: 0; }
  .kind { display: flex; }
  .kind button { border-radius: 0; padding: 3px 14px; font-size: 0.82rem; }
  .kind button:first-child { border-radius: 6px 0 0 6px; }
  .kind button:last-child { border-radius: 0 6px 6px 0; border-left: none; }
  .kind button.active { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); font-weight: 600; }
  .follow { display: flex; align-items: center; gap: 6px; margin: 0 0 0 auto; text-transform: none; font-size: 0.82rem; }
  .follow input { width: auto; }
  .swl { border-color: rgba(120, 170, 220, 0.4); }
  .grp { border-color: rgba(95, 191, 107, 0.45); }

  .grid { display: grid; grid-template-columns: 1.4fr 1fr 0.8fr 0.6fr 0.6fr 0.8fr; gap: 10px; }
  .span2 { grid-column: span 2; }
  .f-comment { grid-column: span 4; }
  .f-comment.wide { grid-column: span 5; }
  .call { font-size: 1.25rem; font-weight: 700; color: var(--gold); letter-spacing: 0.05em; }
  .actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 12px; }
  .hint { color: var(--muted); font-size: 0.78rem; margin-right: auto; }
  .error { color: var(--bad); font-weight: 600; }
  .worked { margin-top: 10px; font-size: 0.85rem; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; color: var(--warn); }
  .chip { border: 1px solid var(--panel-edge); border-radius: 12px; padding: 1px 8px; color: var(--text); }
</style>
