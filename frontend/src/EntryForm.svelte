<script>
  import EibiPick from './EibiPick.svelte';
  import { qrzFiller } from './qrzfill.js';
  const qrzFill = qrzFiller();
  import { untrack, tick } from 'svelte';
  import { api } from './api.js';
  import { MODES, defaultRst, dayOf, timeOf, fmtDate } from './util.js';
  import GroupSession from './GroupSession.svelte';

  let { radio, websdr = null, onlogged, sessions = [] } = $props();

  let kind = $state('QSO');        // QSO = contact réalisé, SWL = écoute, GRP = QSO de groupe

  const KINDS = [
    { id: 'QSO', label: 'QSO', sub: 'contact réalisé', icon: '⇄', help: 'Contact bilatéral réalisé avec le transceiver' },
    { id: 'SWL', label: 'SWL', sub: 'écoute', icon: '◉', help: "Écoute d'une station (Short Wave Listening), avec le WebSDR ORSAT" },
    { id: 'GRP', label: 'Groupe', sub: 'table ronde', icon: '⁂', help: 'QSO de groupe / table ronde : nom, créneau horaire, stations participantes' },
  ];

  // Bandeau de suggestion quand le contexte contredit le mode choisi (jamais de bascule automatique)
  let hintDismissed = $state('');
  const hint = $derived.by(() => {
    const webOn = !!(websdr?.connected && websdr.freq);
    let h = null;
    if (kind === 'SWL' && radio.ptt) {
      h = { key: 'ptt', to: 'QSO', text: 'AetherSDR est en émission.', action: 'Passer en QSO' };
    } else if (kind === 'SWL' && !webOn && radio.connected) {
      h = { key: 'noweb', to: 'QSO', text: "Le WebSDR n'est pas relié, le transceiver l'est.", action: 'Passer en QSO' };
    } else if (kind !== 'SWL' && !radio.connected && webOn) {
      h = { key: 'notx', to: 'SWL', text: "L'émetteur est éteint, le WebSDR écoute.", action: 'Passer en SWL' };
    }
    return h && h.key !== hintDismissed ? h : null;
  });
  let followTci = $state(true);
  let form = $state(blank());
  let worked = $state([]);
  let error = $state('');
  let startTime = null;            // heure UTC figée dès la frappe de l'indicatif
  let callInput = $state();
  let lastRadioMode = null;
  let lastSource = null;           // 'radio' (AetherSDR) ou 'web' (page WebSDR)

  function blank(prev = {}) {
    const label = prev.modeLabel ?? 'SSB';
    return {
      call: '', name: '', qth: '', gridsquare: '', comment: '',
      freqMHz: prev.freqMHz ?? '', modeLabel: label, submode: prev.submode ?? '',
      rst_sent: defaultRst(label, kind), rst_rcvd: defaultRst(label, kind),
    };
  }

  // Source suivie selon le mode d'exploitation : SWL = la page WebSDR ORSAT,
  // QSO et groupe = le transceiver (AetherSDR). Pas de repli de l'un sur l'autre.
  const offline = { connected: false, freq: 0, mode: '', submode: '' };
  const src = $derived(kind === 'SWL' ? (websdr?.connected && websdr.freq ? websdr : offline) : radio);

  // Suivi de la radio : ne réagit qu'aux changements de la radio (un mode choisi à la main est respecté)
  $effect(() => {
    const { freq, mode, submode, connected } = src;
    const source = kind === 'SWL' ? 'web' : 'radio';
    if (!followTci || !connected) return;
    untrack(() => {
      if (freq) form.freqMHz = (freq / 1e6).toFixed(6);
      // Changement de mode de la source, ou passage QSO <-> SWL (autre source) :
      // on reprend son mode, même s'il porte le même nom que celui de l'autre source.
      if (mode !== lastRadioMode || source !== lastSource) {
        lastRadioMode = mode;
        lastSource = source;
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
    if (kind === 'QSO') qrzFill(form);          // locator, nom, QTH depuis l'annuaire QRZ
  }

  async function onCallBlur() {
    worked = kind === 'QSO' && form.call.length >= 3 ? await api.worked(form.call).catch(() => []) : [];
  }

  // Écoute SWL : fréquence notée (Hz) pour la grille EiBi, et ligne de la grille retenue
  const swlFreqHz = $derived.by(() => {
    const f = parseFloat(String(form.freqMHz).replace(',', '.'));
    return Number.isFinite(f) && f > 0 ? Math.round(f * 1e6) : null;
  });
  function pickEibi(c) {
    if (!form.call.trim()) form.call = c.station;
    if (c.site) form.qth = `${c.site} (${c.site_country})`;
    if (c.locator) form.gridsquare = c.locator;
    const info = [c.lang, c.target ? `→ ${c.target}` : ''].filter(Boolean).join(' ');
    if (!form.comment.trim() && info) form.comment = `EiBi : ${info}`;
    if (!startTime) startTime = new Date();
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

  // Ouvre une session de groupe existante dans l'onglet Groupe (pastille ✎ de la page du jour)
  let group = $state();
  export async function openGroup(id) {
    setKind('GRP');
    await tick();
    await group?.show(id);
  }
</script>

<section class="panel entry" class:swl={kind === 'SWL'} class:grp={kind === 'GRP'}>
  <!-- Mode d'exploitation : trois grands onglets, le formulaire entier prend la couleur du mode -->
  <div class="kinds" role="tablist" aria-label="Mode d'exploitation">
    {#each KINDS as k}
      <button type="button" role="tab" class="ktab k-{k.id}" class:active={kind === k.id}
              aria-selected={kind === k.id} onclick={() => setKind(k.id)} title={k.help}>
        <span class="kicon">{k.icon}</span>
        <span class="ktext"><b>{k.label}</b><small>{k.sub}</small></span>
      </button>
    {/each}
  </div>

  <div class="head">
    <h2 class="ktitle">{kind === 'SWL' ? 'Nouvelle écoute' : kind === 'GRP' ? 'QSO de groupe' : 'Nouveau QSO'}</h2>
    <label class="follow" title={kind === 'SWL' ? 'Fréquence et mode repris de la page WebSDR ORSAT (CAT Sync)' : 'Fréquence et mode repris du transceiver (AetherSDR, TCI)'}>
      <input type="checkbox" bind:checked={followTci} /> Suivre {kind === 'SWL' ? 'le WebSDR' : 'la radio'}
    </label>
  </div>

  {#if hint}
    <div class="hint-bar">
      <span>{hint.text}</span>
      <button type="button" class="hint-go k-{hint.to}" onclick={() => setKind(hint.to)}>{hint.action}</button>
      <button type="button" class="ghost hint-x" title="Ignorer" onclick={() => (hintDismissed = hint.key)}>✕</button>
    </div>
  {/if}

  {#if kind === 'GRP'}
    <GroupSession bind:this={group} radio={src} follow={followTci} {sessions} onchanged={() => onlogged?.()} />
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
        <input id="freq" class="mono" bind:value={form.freqMHz} disabled={followTci && src.connected} />
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
    {#if kind === 'SWL'}
      <EibiPick freq={swlFreqHz} onpick={pickEibi} />
    {/if}
    <div class="actions">
      {#if error}<span class="error">{error}</span>{/if}
      <button type="button" onclick={clear}>Effacer</button>
      <button type="submit" class="primary">{kind === 'SWL' ? "Enregistrer l'écoute" : 'Enregistrer le QSO'}</button>
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
  /* Couleur du mode d'exploitation : QSO = vieil or, SWL = bleu, Groupe = vert */
  .entry { --kc: 207, 181, 59; border: 2px solid rgba(var(--kc), 0.55); box-shadow: 0 0 18px rgba(var(--kc), 0.12); }
  .entry.swl { --kc: 110, 170, 230; }
  .entry.grp { --kc: 95, 191, 107; }
  .k-QSO { --tc: 207, 181, 59; }
  .k-SWL { --tc: 110, 170, 230; }
  .k-GRP { --tc: 95, 191, 107; }

  .kinds { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
  .ktab {
    display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 8px;
    background: rgba(0, 0, 0, 0.35); border: 1px solid rgba(var(--tc), 0.35); color: rgba(var(--tc), 0.75);
    text-align: left; cursor: pointer; transition: background 0.15s, border-color 0.15s;
  }
  .ktab:hover { border-color: rgba(var(--tc), 0.8); color: rgb(var(--tc)); box-shadow: none; }
  .ktab.active {
    background: linear-gradient(180deg, rgba(var(--tc), 0.95), rgba(var(--tc), 0.7));
    border-color: rgb(var(--tc)); color: #111; box-shadow: 0 0 12px rgba(var(--tc), 0.45);
  }
  .kicon { font-size: 1.5rem; line-height: 1; width: 1.6rem; text-align: center; }
  .ktext { display: flex; flex-direction: column; line-height: 1.15; }
  .ktext b { font-size: 1.05rem; letter-spacing: 0.06em; }
  .ktext small { font-size: 0.72rem; opacity: 0.85; text-transform: none; }

  .head { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
  .ktitle { margin: 0; font-size: 1.15rem; letter-spacing: 0.12em; text-transform: uppercase; color: rgb(var(--kc)); }
  .follow { display: flex; align-items: center; gap: 6px; margin: 0 0 0 auto; text-transform: none; font-size: 0.82rem; }
  .follow input { width: auto; }

  .hint-bar {
    display: flex; align-items: center; gap: 10px; margin: 0 0 10px; padding: 6px 10px; border-radius: 6px;
    border: 1px solid rgba(224, 160, 48, 0.55); background: rgba(224, 160, 48, 0.1); color: var(--warn); font-size: 0.86rem;
  }
  .hint-go { margin-left: auto; padding: 3px 12px; border-color: rgb(var(--tc)); color: rgb(var(--tc)); }
  .hint-x { padding: 0 4px; color: var(--muted); }
  /* bouton d'enregistrement à la couleur du mode (y compris dans l'onglet Groupe) */
  .entry :global(button.primary) {
    background: linear-gradient(180deg, rgba(var(--kc), 1), rgba(var(--kc), 0.75)); border-color: rgb(var(--kc)); color: #111;
  }

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
