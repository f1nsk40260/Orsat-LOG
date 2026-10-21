<script>
  import { onMount } from 'svelte';
  import { api } from './api.js';
  import EntriesTable from './EntriesTable.svelte';

  let { onopenday } = $props();

  let entries = $state([]);
  let filter = $state('');
  // Deux carnets distincts : 'QSO' = carnet de trafic (contacts, destiné à QRZ.com),
  // 'SWL' = journal d'écoute (jamais exporté avec le trafic).
  let kind = $state('QSO');
  let searchInput;

  const shown = $derived.by(() => {
    const f = filter.trim().toUpperCase();
    return entries.filter((q) =>
      q.kind === kind &&
      (!f || [q.call, q.band, q.mode, q.submode, q.gridsquare, q.name, q.qth, q.comment]
        .some((v) => v && String(v).toUpperCase().includes(f))));
  });

  async function load() { entries = await api.qsos(100000).catch(() => []); }

  async function removeEntry(q) {
    if (!confirm(`Supprimer l'entrée ${q.call} ?`)) return;
    await api.deleteQso(q.id);
    entries = entries.filter((x) => x.id !== q.id);
  }

  const nTraffic = $derived(entries.filter((q) => q.kind === 'QSO').length);
  const nListen = $derived(entries.filter((q) => q.kind === 'SWL').length);

  onMount(() => { load(); searchInput?.focus(); });
</script>

<div class="logbook">
  <section class="panel full">
    <div class="head">
      <div class="books" role="tablist" aria-label="Carnet affiché">
        <button type="button" role="tab" class="book trafic" class:on={kind === 'QSO'} aria-selected={kind === 'QSO'}
                onclick={() => (kind = 'QSO')} title="Contacts réalisés (QSO et QSO de groupe) : le carnet destiné à QRZ.com">
          ⇄ Carnet de trafic <span class="n">{nTraffic}</span></button>
        <button type="button" role="tab" class="book ecoute" class:on={kind === 'SWL'} aria-selected={kind === 'SWL'}
                onclick={() => (kind = 'SWL')} title="Écoutes (SWL) : journal séparé, jamais envoyé vers QRZ.com">
          ◉ Journal d'écoute <span class="n">{nListen}</span></button>
      </div>
      <input class="search" bind:this={searchInput} bind:value={filter}
             placeholder="Rechercher : indicatif, bande, mode, locator, nom…" />
      {#if kind === 'QSO'}
        <a class="btn" href="api/export/adif" download
           title="Export ADIF du carnet de trafic uniquement (pour QRZ.com, LoTW…)">Exporter le trafic (ADIF)</a>
      {:else}
        <a class="btn" href="api/export/adif-swl" download
           title="Export ADIF du journal d'écoute uniquement (SWL:Y)">Exporter les écoutes (ADIF)</a>
      {/if}
    </div>
    {#if filter.trim()}<p class="filtered">{shown.length} résultat{shown.length > 1 ? 's' : ''}</p>{/if}
    <EntriesTable entries={shown} ondelete={removeEntry} ondate={onopenday} onchanged={load}
                  empty={kind === 'QSO' ? 'Aucun contact dans le carnet de trafic.' : "Aucune écoute dans le journal."} />
    <p class="hint">Cliquez sur une date pour ouvrir la page du jour correspondante.</p>
  </section>
</div>

<style>
  .logbook { padding: 14px; height: calc(100vh - 62px); }
  .full { height: 100%; display: flex; flex-direction: column; min-height: 0; }
  .head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  .head .panel-title { margin: 0; white-space: nowrap; }
  .books { display: flex; gap: 8px; }
  .book { padding: 6px 14px; border-radius: 7px; background: rgba(0, 0, 0, 0.35); font-weight: 600; letter-spacing: 0.04em; }
  .book.trafic { --bc: 207, 181, 59; }
  .book.ecoute { --bc: 110, 170, 230; }
  .book { border: 1px solid rgba(var(--bc), 0.4); color: rgba(var(--bc), 0.8); }
  .book:hover { border-color: rgb(var(--bc)); color: rgb(var(--bc)); box-shadow: none; }
  .book.on { background: linear-gradient(180deg, rgba(var(--bc), 0.95), rgba(var(--bc), 0.7)); color: #111; border-color: rgb(var(--bc)); }
  .book .n { font-weight: 400; opacity: 0.8; margin-left: 4px; }
  .search { max-width: 380px; margin-left: auto; }
  .filtered { color: var(--muted); font-size: 0.78rem; margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 0.76rem; margin: 8px 0 0; }
</style>
