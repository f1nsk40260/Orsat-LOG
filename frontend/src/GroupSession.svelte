<script>
  import { onMount } from 'svelte';
  import { api } from './api.js';
  import { MODES, pad, dayOf, timeOf, fmtTime } from './util.js';

  // sessions = QSO de groupe déjà ouverts aujourd'hui (pour les reprendre)
  let { radio, sessions = [], onchanged } = $props();

  const hhmm = (d = new Date()) => `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  const showHHMM = (v) => (v ? `${v.slice(0, 2)}:${v.slice(2, 4)}` : '');
  // mode / sous-mode ADIF -> libellé (FT4 = MFSK/FT4, SSB/LSB = SSB…)
  const modeLabel = (mode, sub) =>
    (MODES.find((m) => m.mode === mode && m.sub && m.sub === sub) ?? MODES.find((m) => m.mode === mode && !m.sub))?.label ?? mode ?? 'SSB';

  let names = $state([]);          // noms déjà utilisés + réglages de la dernière fois
  let active = $state(null);       // session en cours (avec participants)
  let regulars = $state([]);
  let editing = $state(false);
  let error = $state('');
  let lastTime = $state(null);     // réglages repris d'une session précédente

  // formulaire d'ouverture / de modification
  let setup = $state(blankSetup());
  // saisie rapide d'un participant
  let p = $state(blankP());
  let callInput = $state();

  function blankSetup() {
    return {
      name: '', start: hhmm(), end: '',
      freqMHz: radio?.freq ? (radio.freq / 1e6).toFixed(6) : '',
      modeLabel: radio?.mode && MODES.some((m) => m.label === radio.mode) ? radio.mode : 'SSB',
      submode: radio?.submode || '',
    };
  }
  function blankP() {
    const rst = defaultRst();
    return { call: '', rst_sent: rst, rst_rcvd: rst, name: '', qth: '', gridsquare: '', comment: '' };
  }
  function defaultRst() {
    const l = active ? modeLabel(active.mode, active.submode) : 'SSB';
    return l === 'CW' ? '599' : ['FT8', 'FT4', 'JS8'].includes(l) ? '' : '59';
  }

  onMount(async () => { names = await api.sessionNames().catch(() => []); });

  // nom déjà connu -> on reprend l'horaire, la fréquence et le mode de la dernière fois
  function onNameChange() {
    const n = names.find((x) => x.name.toLowerCase() === setup.name.trim().toLowerCase());
    if (!n || editing) return;
    setup.name = n.name;
    // QSO quotidien : même créneau horaire que la dernière fois
    setup.start = showHHMM(n.time_start);
    setup.end = n.time_end ? showHHMM(n.time_end) : '';
    lastTime = n;
    if (n.freq) setup.freqMHz = (n.freq / 1e6).toFixed(6);
    setup.modeLabel = modeLabel(n.mode, n.submode);
    setup.submode = n.mode === 'SSB' ? n.submode : '';
  }

  function takeRadio() {
    if (radio?.freq) setup.freqMHz = (radio.freq / 1e6).toFixed(6);
    if (radio?.mode && MODES.some((m) => m.label === radio.mode)) setup.modeLabel = radio.mode;
    setup.submode = radio?.submode || '';
  }

  function setupPayload() {
    const m = MODES.find((x) => x.label === setup.modeLabel) ?? { mode: setup.modeLabel, sub: '' };
    const f = parseFloat(String(setup.freqMHz).replace(',', '.'));
    return {
      name: setup.name, time_start: setup.start, time_end: setup.end,
      freq: Number.isFinite(f) ? Math.round(f * 1e6) : null,
      mode: m.mode, submode: m.sub || (m.mode === 'SSB' ? setup.submode : ''),
    };
  }

  async function openSession(e) {
    e?.preventDefault();
    error = '';
    try {
      const s = await api.createSession(setupPayload());
      await load(s.id);
      onchanged?.();
    } catch (err) { error = err.message; }
  }

  async function load(id) {
    active = await api.session(id);
    regulars = await api.regulars(active.name).catch(() => []);
    p = blankP();
    editing = false;
    setTimeout(() => callInput?.focus(), 0);
  }

  function startEdit() {
    setup = {
      name: active.name, start: showHHMM(active.time_start), end: showHHMM(active.time_end),
      freqMHz: active.freq ? (active.freq / 1e6).toFixed(6) : '',
      modeLabel: modeLabel(active.mode, active.submode), submode: active.submode || '',
    };
    editing = true;
  }

  async function saveEdit(e) {
    e?.preventDefault();
    error = '';
    try {
      await api.updateSession(active.id, setupPayload());
      await load(active.id);
      onchanged?.();
    } catch (err) { error = err.message; }
  }

  async function closeSession() {
    await api.updateSession(active.id, { time_end: hhmm() });
    await load(active.id);
    onchanged?.();
  }

  async function deleteSession() {
    if (!confirm(`Supprimer « ${active.name} » et ses ${active.participants.length} QSO ?`)) return;
    await api.deleteSession(active.id);
    active = null;
    editing = false;
    setup = blankSetup();
    onchanged?.();
  }

  function leave() {
    active = null;
    editing = false;
    setup = blankSetup();
    error = '';
  }

  // heure du passage : maintenant si la session est en cours, sinon l'heure de début (saisie après coup)
  function passTime() {
    const now = new Date();
    const end = active.time_end;
    const nowHHMM = `${pad(now.getUTCHours())}${pad(now.getUTCMinutes())}`;
    if (active.day === dayOf(now) && nowHHMM >= active.time_start && (!end || nowHHMM <= end)) {
      return { qso_date: dayOf(now), time_on: timeOf(now) };
    }
    return { qso_date: active.day, time_on: `${active.time_start}00` };
  }

  async function addParticipant(data) {
    error = '';
    const call = (data.call || '').trim().toUpperCase();
    if (!call) { error = 'Indicatif obligatoire'; return; }
    if (active.participants.some((x) => x.call === call) &&
        !confirm(`${call} est déjà dans ce QSO de groupe. L'ajouter quand même ?`)) return;
    try {
      await api.addQso({
        session_id: active.id, ...passTime(), call,
        freq: active.freq, mode: active.mode, submode: active.submode,
        rst_sent: data.rst_sent ?? '', rst_rcvd: data.rst_rcvd ?? '',
        name: data.name || '', qth: data.qth || '', gridsquare: (data.gridsquare || '').toUpperCase(),
        comment: data.comment || '',
      });
      active = await api.session(active.id);
      p = blankP();
      callInput?.focus();
      onchanged?.();
    } catch (err) { error = err.message; }
  }

  function addQuick(e) {
    e.preventDefault();
    addParticipant(p);
  }

  // indicatif d'un habitué -> nom / QTH / locator préremplis
  function onCallInput() {
    p.call = p.call.toUpperCase();
    const r = regulars.find((x) => x.call === p.call);
    if (r) {
      if (!p.name) p.name = r.name || '';
      if (!p.qth) p.qth = r.qth || '';
      if (!p.gridsquare) p.gridsquare = r.gridsquare || '';
    }
  }

  function addRegular(r) {
    const rst = defaultRst();
    addParticipant({ call: r.call, rst_sent: rst, rst_rcvd: rst, name: r.name, qth: r.qth, gridsquare: r.gridsquare });
  }

  async function removeParticipant(q) {
    if (!confirm(`Retirer ${q.call} de ce QSO de groupe ?`)) return;
    await api.deleteQso(q.id);
    active = await api.session(active.id);
    onchanged?.();
  }

  const present = $derived(new Set(active?.participants.map((x) => x.call) ?? []));
  const missing = $derived(regulars.filter((r) => !present.has(r.call)));
  const running = $derived(active && !active.time_end);
</script>

{#if !active || editing}
  <!-- ouverture (ou modification) d'un QSO de groupe -->
  <form class="setup" onsubmit={editing ? saveEdit : openSession}>
    <div class="grid">
      <div class="f-name">
        <label for="g-name">Nom du QSO de groupe</label>
        <input id="g-name" bind:value={setup.name} list="g-names" onchange={onNameChange}
               placeholder="ex. QSO des Copains" autocomplete="off" />
        <datalist id="g-names">{#each names as n}<option value={n.name}></option>{/each}</datalist>
      </div>
      <div>
        <label for="g-start">Début (UTC)</label>
        <input id="g-start" class="mono" bind:value={setup.start} placeholder="HH:MM" maxlength="5" />
      </div>
      <div>
        <label for="g-end">Fin (UTC)</label>
        <input id="g-end" class="mono" bind:value={setup.end} placeholder="en cours" maxlength="5" />
      </div>
      <div>
        <label for="g-freq">Fréquence (MHz)</label>
        <input id="g-freq" class="mono" bind:value={setup.freqMHz} />
      </div>
      <div>
        <label for="g-mode">Mode</label>
        <select id="g-mode" bind:value={setup.modeLabel}>
          {#each MODES as m}<option value={m.label}>{m.label}</option>{/each}
        </select>
      </div>
    </div>
    {#if lastTime && !editing}
      <p class="hint">Créneau, fréquence et mode repris du {lastTime.day.slice(6)}/{lastTime.day.slice(4, 6)}
        ({lastTime.cnt} session{lastTime.cnt > 1 ? 's' : ''} sous ce nom) — modifiables.</p>
    {/if}
    <div class="actions">
      {#if error}<span class="error">{error}</span>{/if}
      {#if !editing && sessions.length}
        <span class="resume">
          Reprendre :
          {#each sessions as s}
            <button type="button" class="chip-btn" onclick={() => load(s.id)}
                    title="Rouvrir ce QSO de groupe pour ajouter des stations">
              {s.name} {showHHMM(s.time_start)}{s.time_end ? `–${showHHMM(s.time_end)}` : ' (en cours)'} · {s.count}
            </button>
          {/each}
        </span>
      {/if}
      <span class="spacer"></span>
      {#if radio?.connected}<button type="button" onclick={takeRadio} title="Reprendre fréquence et mode de la radio">← Radio</button>{/if}
      {#if editing}
        <button type="button" class="danger" onclick={deleteSession}>Supprimer</button>
        <button type="button" onclick={() => (editing = false)}>Annuler</button>
        <button type="submit" class="primary">Enregistrer</button>
      {:else}
        <button type="submit" class="primary">Ouvrir le QSO de groupe</button>
      {/if}
    </div>
  </form>
{:else}
  <!-- QSO de groupe ouvert -->
  <div class="bar">
    <span class="g-title">{active.name}</span>
    <span class="g-info mono">
      {showHHMM(active.time_start)} – {active.time_end ? showHHMM(active.time_end) : '…'} UTC
      · {active.freq ? (active.freq / 1e6).toFixed(3) : '—'} MHz · {modeLabel(active.mode, active.submode)}
    </span>
    {#if running}<span class="live">en cours</span>{/if}
    <span class="spacer"></span>
    <button class="small" onclick={startEdit} title="Modifier nom, horaires, fréquence">Modifier</button>
    {#if running}<button class="small" onclick={closeSession} title="Fixer l'heure de fin à maintenant">Clôturer</button>{/if}
    <button class="small" onclick={leave} title="Fermer cette fenêtre (le QSO de groupe reste enregistré)">Fermer</button>
  </div>

  <form class="quick" onsubmit={addQuick}>
    <div class="qgrid">
      <div><label for="p-call">Indicatif</label>
        <input id="p-call" class="mono call" bind:this={callInput} bind:value={p.call} oninput={onCallInput}
               autocomplete="off" spellcheck="false" /></div>
      <div><label for="p-rs">Env.</label><input id="p-rs" class="mono" bind:value={p.rst_sent} /></div>
      <div><label for="p-rr">Reçu</label><input id="p-rr" class="mono" bind:value={p.rst_rcvd} /></div>
      <div><label for="p-name">Nom</label><input id="p-name" bind:value={p.name} /></div>
      <div><label for="p-qth">QTH</label><input id="p-qth" bind:value={p.qth} /></div>
      <div><label for="p-loc">Locator</label>
        <input id="p-loc" class="mono" bind:value={p.gridsquare} maxlength="8"
               oninput={() => (p.gridsquare = p.gridsquare.toUpperCase())} /></div>
      <div class="qbtn"><button type="submit" class="primary">Ajouter</button></div>
    </div>
    {#if error}<div class="error">{error}</div>{/if}
  </form>

  {#if missing.length}
    <div class="regulars">
      <span class="lbl">Habitués absents — clic = ajouté :</span>
      {#each missing as r}
        <button class="chip-btn" onclick={() => addRegular(r)}
                title="{r.name || ''} {r.qth || ''} — présent {r.times} fois sur les dernières sessions">
          {r.call}{r.name ? ` · ${r.name}` : ''}
        </button>
      {/each}
    </div>
  {/if}

  <div class="plist">
    <span class="lbl">{active.participants.length} station{active.participants.length > 1 ? 's' : ''} :</span>
    {#each active.participants as q (q.id)}
      <span class="pchip" title="{fmtTime(q.time_on)} UTC · {q.rst_sent}/{q.rst_rcvd} {q.qth || ''}">
        <b>{q.call}</b>{q.name ? ` ${q.name}` : ''}
        <button class="ghost x" onclick={() => removeParticipant(q)} title="Retirer">✕</button>
      </span>
    {:else}
      <span class="muted">aucune station pour l'instant</span>
    {/each}
  </div>
{/if}

<style>
  .grid { display: grid; grid-template-columns: 2fr 0.7fr 0.7fr 1fr 0.8fr; gap: 10px; }
  .actions { display: flex; align-items: center; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
  .spacer { flex: 1; }
  .resume { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 0.8rem; color: var(--muted); }
  .chip-btn { padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; }
  .hint { color: var(--muted); font-size: 0.78rem; margin: 8px 0 0; }
  .danger { color: var(--bad); border-color: rgba(214, 80, 80, 0.6); }
  .error { color: var(--bad); font-weight: 600; font-size: 0.85rem; margin-top: 6px; }

  .bar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
  .g-title { color: var(--gold); font-size: 1.15rem; font-weight: 700; }
  .g-info { color: var(--text); font-size: 0.88rem; }
  .live { font-size: 0.7rem; color: #0d1a0d; background: var(--ok); border-radius: 10px; padding: 1px 8px; font-weight: 700; }
  .small { padding: 3px 10px; font-size: 0.82rem; }

  .qgrid { display: grid; grid-template-columns: 1.3fr 0.5fr 0.5fr 1fr 1.1fr 0.7fr auto; gap: 8px; align-items: end; }
  .call { font-size: 1.15rem; font-weight: 700; color: var(--gold); letter-spacing: 0.05em; }
  .regulars, .plist { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 10px; font-size: 0.82rem; }
  .lbl { color: var(--muted); }
  .pchip { display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--panel-edge);
           border-radius: 12px; padding: 1px 4px 1px 10px; background: rgba(207, 181, 59, 0.08); }
  .pchip b { color: var(--gold); }
  .x { padding: 0 4px; font-size: 0.7rem; color: var(--muted); }
  .x:hover { color: var(--bad); }
  .muted { color: var(--muted); }
</style>
