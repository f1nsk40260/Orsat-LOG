<script>
  // Formulaire d'édition complet d'une entrée du carnet (QSO, écoute SWL, passage de QSO de groupe).
  // Bande, distance et azimut sont recalculés par le serveur à l'enregistrement.
  import { onMount, untrack } from 'svelte';
  import { api, deleteEntry } from './api.js';
  import { MODES } from './util.js';

  let { entry, onclose, onsaved, ondeleted } = $props();

  // Libellé du sélecteur Mode à partir du mode / sous-mode ADIF enregistrés
  function labelOf(q) {
    const exact = MODES.find((m) => m.mode === q.mode && m.sub && m.sub === q.submode);
    if (exact) return exact.label;
    const byMode = MODES.find((m) => m.mode === q.mode && !m.sub);
    return byMode ? byMode.label : (q.mode || 'SSB');
  }

  // L'entrée est copiée une fois à l'ouverture : le formulaire travaille sur sa copie
  const e = untrack(() => entry);
  const fmtDate = (d) => (d && d.length === 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}` : '');
  const fmtTime = (t) => (t && t.length >= 4 ? `${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4, 6) || '00'}` : '');
  const num = (v) => (v === null || v === undefined ? '' : String(v));

  let f = $state({
    kind: e.kind === 'SWL' ? 'SWL' : 'QSO',
    call: e.call || '',
    date: fmtDate(e.qso_date),
    time: fmtTime(e.time_on),
    freqMHz: e.freq ? (e.freq / 1e6).toFixed(6) : '',
    modeLabel: labelOf(e),
    submode: e.submode || '',
    rst_sent: e.rst_sent || '',
    rst_rcvd: e.rst_rcvd || '',
    name: e.name || '',
    qth: e.qth || '',
    gridsquare: e.gridsquare || '',
    comment: e.comment || '',
    sfi: num(e.sfi), a_index: num(e.a_index), k_index: num(e.k_index),
    keepSession: e.session_id != null,
  });
  let error = $state('');
  let saving = $state(false);
  let callInput;

  // Mode hors liste (importé ou ancien) : proposé quand même dans le sélecteur
  const modeOptions = $derived(
    MODES.some((m) => m.label === f.modeLabel) ? MODES : [{ label: f.modeLabel, mode: f.modeLabel, sub: '' }, ...MODES]
  );
  const swl = $derived(f.kind === 'SWL');
  const ssb = $derived(f.modeLabel === 'SSB');

  onMount(() => callInput?.focus());

  function optNum(v, field) {
    const s = String(v).trim().replace(',', '.');
    if (s === '') return null;
    const n = Number(s);
    if (!Number.isFinite(n)) throw new Error(`${field} invalide`);
    return n;
  }

  async function save(ev) {
    ev?.preventDefault();
    error = '';
    try {
      const freq = optNum(f.freqMHz, 'Fréquence');
      const m = MODES.find((x) => x.label === f.modeLabel) ?? { mode: f.modeLabel, sub: '' };
      saving = true;
      const q = await api.updateQso(e.id, {
        kind: f.kind,
        session_id: f.kind === 'QSO' && f.keepSession ? e.session_id : null,
        call: f.call, qso_date: f.date, time_on: f.time,
        freq: freq === null ? null : Math.round(freq * 1e6),
        // sous-mode : imposé par le mode (FT4, PSK31...), USB/LSB en SSB, libre pour un mode hors liste
        mode: m.mode, submode: m.sub || (m.mode === 'SSB' || !MODES.some((x) => x.label === f.modeLabel) ? f.submode : ''),
        rst_sent: f.rst_sent, rst_rcvd: f.rst_rcvd,
        name: f.name, qth: f.qth, gridsquare: f.gridsquare, comment: f.comment,
        sfi: optNum(f.sfi, 'SFI'), a_index: optNum(f.a_index, 'Indice A'), k_index: optNum(f.k_index, 'Indice K'),
      });
      onsaved?.(q);
    } catch (err) {
      error = err.message;
    } finally {
      saving = false;
    }
  }

  async function remove() {
    try {
      if (!(await deleteEntry(e, `Supprimer définitivement l'entrée ${e.call} ?`))) return;
      ondeleted?.(e);
    } catch (err) {
      error = err.message;
    }
  }

  function onkey(ev) {
    if (ev.key === 'Escape') { ev.preventDefault(); onclose?.(); }
  }
</script>

<svelte:window onkeydown={onkey} />

<div class="backdrop" onclick={onclose} role="presentation"></div>
<form class="panel dialog" onsubmit={save}>
  <div class="head">
    <h2 class="panel-title">Modifier {swl ? "l'écoute" : 'le QSO'}</h2>
    <div class="kind" role="group" aria-label="Type d'entrée">
      <button type="button" class:on={f.kind === 'QSO'} onclick={() => (f.kind = 'QSO')}>QSO</button>
      <button type="button" class:on={f.kind === 'SWL'} onclick={() => (f.kind = 'SWL')}>SWL</button>
    </div>
  </div>

  {#if e.session_id != null}
    <label class="check session">
      <input type="checkbox" bind:checked={f.keepSession} disabled={swl} />
      Passage du QSO de groupe <b>{e.session_name || `n° ${e.session_id}`}</b>
      {#if !f.keepSession || swl}<span class="warn">— sera détaché de la session</span>{/if}
    </label>
  {/if}

  <fieldset>
    <legend>{swl ? 'Station entendue' : 'Contact'}</legend>
    <div class="grid g3">
      <div class="wide">
        <label for="e-call">{swl ? 'Station entendue' : 'Indicatif'}</label>
        <input id="e-call" class="mono call" bind:this={callInput} bind:value={f.call}
               oninput={() => { if (!swl) f.call = f.call.toUpperCase(); }} />
      </div>
      <div>
        <label for="e-date">Date (UTC)</label>
        <input id="e-date" class="mono" bind:value={f.date} placeholder="AAAA-MM-JJ" />
      </div>
      <div>
        <label for="e-time">Heure UTC</label>
        <input id="e-time" class="mono" bind:value={f.time} placeholder="HH:MM:SS" />
      </div>
    </div>
  </fieldset>

  <fieldset>
    <legend>Fréquence et mode</legend>
    <div class="grid g3">
      <div>
        <label for="e-freq">Fréquence (MHz)</label>
        <input id="e-freq" class="mono" bind:value={f.freqMHz} />
      </div>
      <div>
        <label for="e-mode">Mode</label>
        <select id="e-mode" bind:value={f.modeLabel}>
          {#each modeOptions as m}<option value={m.label}>{m.label}</option>{/each}
        </select>
      </div>
      <div>
        <label for="e-sub">Sous-mode</label>
        {#if ssb}
          <select id="e-sub" value={f.submode} onchange={(ev) => (f.submode = ev.currentTarget.value)}>
            <option value="">—</option><option value="USB">USB</option><option value="LSB">LSB</option>
          </select>
        {:else}
          <input id="e-sub" class="mono" bind:value={f.submode}
                 disabled={MODES.some((m) => m.label === f.modeLabel && m.sub)} />
        {/if}
      </div>
    </div>
    <p class="note">Bande{e.band ? ` actuelle : ${e.band}` : ''} — recalculée à l'enregistrement.</p>
  </fieldset>

  <fieldset>
    <legend>{swl ? 'Réception' : 'Reports'}</legend>
    <div class="grid g3">
      {#if !swl}
        <div>
          <label for="e-rsts">RST envoyé</label>
          <input id="e-rsts" class="mono" bind:value={f.rst_sent} />
        </div>
      {/if}
      <div>
        <label for="e-rstr">{swl ? 'SINPO / SIO' : 'RST reçu'}</label>
        <input id="e-rstr" class="mono" bind:value={f.rst_rcvd} />
      </div>
      <div>
        <label for="e-grid">{swl ? 'Loc. émetteur' : 'Locator'}</label>
        <input id="e-grid" class="mono" bind:value={f.gridsquare}
               oninput={() => (f.gridsquare = f.gridsquare.toUpperCase())} />
      </div>
    </div>
    <p class="note">
      {#if e.distance_km != null}Distance actuelle : {e.distance_km} km, azimut {e.bearing}° — {/if}recalculés depuis le locator.
    </p>
  </fieldset>

  <fieldset>
    <legend>{swl ? 'Émetteur et programme' : 'Correspondant'}</legend>
    <div class="grid g2">
      {#if !swl}
        <div>
          <label for="e-name">Nom</label>
          <input id="e-name" bind:value={f.name} />
        </div>
      {/if}
      <div class:wide2={swl}>
        <label for="e-qth">{swl ? 'Émetteur (site)' : 'QTH'}</label>
        <input id="e-qth" bind:value={f.qth} />
      </div>
      <div class="wide2">
        <label for="e-comment">{swl ? 'Programme / langue / remarques' : 'Commentaire'}</label>
        <input id="e-comment" bind:value={f.comment} />
      </div>
    </div>
  </fieldset>

  <fieldset>
    <legend>Propagation au moment de l'entrée</legend>
    <div class="grid g3">
      <div><label for="e-sfi">SFI</label><input id="e-sfi" class="mono" bind:value={f.sfi} /></div>
      <div><label for="e-a">Indice A</label><input id="e-a" class="mono" bind:value={f.a_index} /></div>
      <div><label for="e-k">Indice K</label><input id="e-k" class="mono" bind:value={f.k_index} /></div>
    </div>
  </fieldset>

  <div class="actions">
    <button type="button" class="ghost del" onclick={remove} title="Supprimer cette entrée">Supprimer</button>
    {#if error}<span class="error">{error}</span>{/if}
    <button type="button" onclick={onclose}>Annuler</button>
    <button type="submit" class="primary" disabled={saving}>{saving ? 'Enregistrement…' : 'Enregistrer'}</button>
  </div>
  <p class="keys">Entrée = enregistrer · Échap = annuler</p>
</form>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); z-index: 30; }
  .dialog {
    position: fixed; z-index: 31; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 640px; max-width: calc(100vw - 32px); max-height: calc(100vh - 32px); overflow-y: auto;
  }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
  .head .panel-title { margin: 0; }
  .kind { display: flex; border: 1px solid var(--gold-soft); border-radius: 6px; overflow: hidden; }
  .kind button { border: none; border-radius: 0; padding: 3px 14px; background: transparent; color: var(--gold); }
  .kind button.on { background: var(--gold); color: #111; font-weight: 600; }
  fieldset { border: 1px solid var(--panel-edge); border-radius: 6px; margin: 0 0 10px; padding: 8px 12px 10px; }
  legend { color: var(--gold); padding: 0 6px; font-size: 0.85rem; }
  .grid { display: grid; gap: 10px; }
  .g3 { grid-template-columns: 1fr 1fr 1fr; }
  .g2 { grid-template-columns: 1fr 1fr; }
  .g3 .wide { grid-column: span 1; }
  .wide2 { grid-column: 1 / -1; }
  .call { text-transform: none; font-size: 1.05rem; }
  .note { color: var(--muted); font-size: 0.78rem; margin: 6px 0 0; }
  .check { display: flex; align-items: center; gap: 8px; text-transform: none; font-size: 0.88rem; margin: 0 0 10px; }
  .check input { width: auto; }
  .session b { color: var(--gold); }
  .warn { color: var(--warn); }
  .actions { display: flex; justify-content: flex-end; align-items: center; gap: 10px; }
  .actions .del { margin-right: auto; color: var(--bad); }
  .error { color: var(--bad); font-size: 0.85rem; }
  .keys { color: var(--muted); font-size: 0.75rem; margin: 8px 0 0; text-align: right; }
  @media (max-width: 560px) { .g3, .g2 { grid-template-columns: 1fr; } }
</style>
