<script>
  import { untrack } from 'svelte';
  import { api } from './api.js';
  import { fmtFreq } from './util.js';
  import EntryForm from './EntryForm.svelte';
  import EntriesTable from './EntriesTable.svelte';
  import PropagationPanel from './PropagationPanel.svelte';
  import WeatherPanel from './WeatherPanel.svelte';

  let { day, isToday, radio, websdr, settings } = $props();

  let page = $state(null);
  let note = $state('');
  let noteState = $state('');   // '', 'modifié', 'enregistré'
  let noteTimer = null;
  let noteDay = null;           // jour auquel appartient la note en cours d'édition
  let form = $state();

  async function load(d) {
    const p = await api.day(d).catch(() => null);
    if (p && p.day === day) {
      page = p;
      if (noteState !== 'modifié') note = p.note;
    }
  }

  // changement de jour : on recharge la page et on repart d'une note propre
  $effect(() => {
    const d = day;                 // seule dépendance : le jour affiché
    untrack(() => {
      flushNote();
      noteDay = d;
      page = null;
      note = '';
      noteState = '';
      load(d);
    });
  });

  // enregistre tout de suite une note encore en attente (changement de jour, fermeture)
  function flushNote() {
    if (noteTimer) {
      clearTimeout(noteTimer);
      noteTimer = null;
      api.saveNote(noteDay, note);
    }
  }

  // page du jour : rafraîchissement régulier (nouveaux relevés de propagation)
  $effect(() => {
    if (!isToday) return;
    const d = day;
    const t = setInterval(() => load(d), 5 * 60 * 1000);
    return () => clearInterval(t);
  });

  function onNoteInput() {
    noteState = 'modifié';
    clearTimeout(noteTimer);
    const d = noteDay, text = note;
    noteTimer = setTimeout(async () => {
      noteTimer = null;
      await api.saveNote(d, text);
      if (d === noteDay) noteState = 'enregistré';
    }, 800);
  }

  async function removeEntry(q) {
    if (!confirm(`Supprimer l'entrée ${q.call} ?`)) return;
    await api.deleteQso(q.id);
    load(day);
  }

  export function clearForm() { form?.clear(); }

  const bandsList = $derived(page ? Object.entries(page.stats.bands).sort((a, b) => b[1] - a[1]) : []);
</script>

<svelte:window onbeforeunload={flushNote} />

<div class="day" class:archive={!isToday}>
  <!-- colonne gauche : radio + propagation -->
  <div class="col left">
    {#if isToday}
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
        {#if !radio.connected && radio.error}
          <div class="tci-error">{radio.error}</div>
        {/if}
        <div class="freq mono">{fmtFreq(radio.freq)}<small> MHz</small></div>
        <div class="radio-mode">{radio.modulation ? radio.modulation.toUpperCase() : '—'}</div>
      </section>
      {#if websdr?.listening || websdr?.error}
        <section class="panel radio">
          <h2 class="panel-title">WebSDR ORSAT</h2>
          <div class="tci-status">
            <span class="dot" class:on={websdr.connected}></span>
            {#if websdr.connected}
              Page connectée
            {:else}
              En attente de la page (CAT Sync)
            {/if}
          </div>
          {#if websdr.error}<div class="tci-error">{websdr.error}</div>{/if}
          {#if websdr.connected && !websdr.freq}
            <div class="tci-error">Touchez la fréquence sur la page pour synchroniser.</div>
          {/if}
          <div class="freq mono">{fmtFreq(websdr.freq)}<small> MHz</small></div>
          <div class="radio-mode">{websdr.modulation ? websdr.modulation.toUpperCase() : '—'}</div>
        </section>
      {/if}
    {/if}
    <PropagationPanel snapshots={page?.propagation ?? []} {isToday} />
  </div>

  <!-- colonne centrale : saisie + activité du jour -->
  <div class="col center">
    {#if isToday}
      <EntryForm bind:this={form} {radio} {websdr} sessions={page?.sessions ?? []} onlogged={() => load(day)} />
    {:else}
      <div class="panel archived">Page archivée — la saisie se fait sur la page du jour.</div>
    {/if}
    <section class="panel activity">
      <h2 class="panel-title">
        Activité du jour
        {#if page}<span class="count">{page.stats.qso} QSO · {page.stats.swl} SWL</span>{/if}
      </h2>
      {#if page?.sessions?.length}
        <div class="sessions">
          {#each page.sessions as s}
            <span class="sess" title="QSO de groupe">
              <b>{s.name}</b>
              {s.time_start.slice(0, 2)}:{s.time_start.slice(2)}–{s.time_end ? `${s.time_end.slice(0, 2)}:${s.time_end.slice(2)}` : 'en cours'}
              · {s.count} station{s.count > 1 ? 's' : ''}{s.animator ? ` · anim. ${s.animator}` : ''}
            </span>
          {/each}
        </div>
      {/if}
      <EntriesTable entries={page?.entries ?? []} showDate={false} ondelete={removeEntry}
                    empty={isToday ? 'Aucune activité pour l’instant aujourd’hui.' : 'Aucune activité ce jour-là.'} />
    </section>
  </div>

  <!-- colonne droite : notes, résumé, météo -->
  <div class="col right">
    <section class="panel notes">
      <h2 class="panel-title">Notes du jour <span class="count">{noteState}</span></h2>
      <textarea bind:value={note} oninput={onNoteInput}
                placeholder="Conditions observées, ouvertures, matériel, antenne, événements…"></textarea>
    </section>

    <section class="panel summary">
      <h2 class="panel-title">Bilan</h2>
      {#if page && (page.stats.qso || page.stats.swl)}
        <div class="sum-line"><span>Entrées</span><b>{page.stats.qso + page.stats.swl}</b></div>
        {#if page.stats.max_km}
          <div class="sum-line"><span>Plus longue distance</span><b>{page.stats.max_km} km</b></div>
        {/if}
        <div class="bands">
          {#each bandsList as [b, n]}<span class="chip">{b} <b>{n}</b></span>{/each}
        </div>
      {:else}
        <p class="muted">Rien encore.</p>
      {/if}
    </section>

    <WeatherPanel snapshots={page?.weather ?? []} {isToday} />
  </div>
</div>

<style>
  .day {
    display: grid; grid-template-columns: 320px minmax(0, 1fr) 290px; gap: 14px;
    padding: 14px; height: calc(100vh - 62px); min-height: 0;
  }
  .col { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
  .activity { flex: 1; display: flex; flex-direction: column; min-height: 0; }
  .count { color: var(--muted); font-weight: 400; margin-left: 8px; text-transform: none; letter-spacing: 0; }
  .archived { color: var(--muted); font-style: italic; }
  .sessions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .sess { font-size: 0.8rem; border: 1px solid rgba(95, 191, 107, 0.5); border-radius: 12px; padding: 2px 10px; }
  .sess b { color: var(--ok); }

  .tci-status { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--muted); }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--bad); box-shadow: 0 0 6px var(--bad); }
  .dot.on { background: var(--ok); box-shadow: 0 0 6px var(--ok); }
  .tci-error { color: var(--warn); font-size: 0.78rem; margin-top: 6px; }
  .tx { margin-left: auto; color: #fff; background: var(--bad); padding: 1px 8px; border-radius: 4px; font-weight: 700; }
  .freq { font-size: 2rem; color: var(--gold); margin: 12px 0 2px; text-shadow: 0 0 10px rgba(207, 181, 59, 0.35); }
  .freq small { font-size: 0.9rem; color: var(--gold-soft); }
  .radio-mode { color: var(--text); letter-spacing: 0.1em; }

  .notes { flex: 1; display: flex; flex-direction: column; min-height: 160px; }
  textarea {
    flex: 1; resize: none; font: inherit; font-size: 0.9rem; color: var(--text);
    background: rgba(0, 0, 0, 0.45); border: 1px solid rgba(207, 181, 59, 0.3); border-radius: 5px; padding: 8px;
  }
  textarea:focus { outline: none; border-color: var(--gold); box-shadow: 0 0 0 2px var(--gold-faint); }
  .sum-line { display: flex; justify-content: space-between; font-size: 0.88rem; padding: 2px 0; }
  .sum-line span { color: var(--muted); }
  .bands { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
  .chip { border: 1px solid var(--panel-edge); border-radius: 12px; padding: 1px 8px; font-size: 0.8rem; }
  .chip b { color: var(--gold); }
  .muted { color: var(--muted); font-size: 0.85rem; margin: 0; }
</style>
