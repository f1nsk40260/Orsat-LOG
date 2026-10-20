<script>
  import { onMount } from 'svelte';
  import { api } from './api.js';
  import EntriesTable from './EntriesTable.svelte';

  let { onopenday } = $props();

  let entries = $state([]);
  let filter = $state('');
  let kind = $state('');   // '' = tout, 'QSO', 'SWL'
  let searchInput;

  const shown = $derived.by(() => {
    const f = filter.trim().toUpperCase();
    return entries.filter((q) =>
      (!kind || q.kind === kind) &&
      (!f || [q.call, q.band, q.mode, q.submode, q.gridsquare, q.name, q.qth, q.comment]
        .some((v) => v && String(v).toUpperCase().includes(f))));
  });

  async function load() { entries = await api.qsos(100000).catch(() => []); }

  async function removeEntry(q) {
    if (!confirm(`Supprimer l'entrée ${q.call} ?`)) return;
    await api.deleteQso(q.id);
    entries = entries.filter((x) => x.id !== q.id);
  }

  onMount(() => { load(); searchInput?.focus(); });
</script>

<div class="logbook">
  <section class="panel full">
    <div class="head">
      <h2 class="panel-title">Carnet de trafic complet
        <span class="count">{shown.length}{shown.length !== entries.length ? ` / ${entries.length}` : ''} entrées</span>
      </h2>
      <input class="search" bind:this={searchInput} bind:value={filter}
             placeholder="Rechercher : indicatif, bande, mode, locator, nom…" />
      <select bind:value={kind} class="kind">
        <option value="">QSO + SWL</option><option value="QSO">QSO</option><option value="SWL">SWL</option>
      </select>
    </div>
    <EntriesTable entries={shown} ondelete={removeEntry} ondate={onopenday} onchanged={load} empty="Aucune entrée dans le carnet." />
    <p class="hint">Cliquez sur une date pour ouvrir la page du jour correspondante.</p>
  </section>
</div>

<style>
  .logbook { padding: 14px; height: calc(100vh - 62px); }
  .full { height: 100%; display: flex; flex-direction: column; min-height: 0; }
  .head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  .head .panel-title { margin: 0; white-space: nowrap; }
  .count { color: var(--muted); font-weight: 400; margin-left: 8px; text-transform: none; letter-spacing: 0; }
  .search { max-width: 420px; margin-left: auto; }
  .kind { width: auto; }
  .hint { color: var(--muted); font-size: 0.76rem; margin: 8px 0 0; }
</style>
