<script>
  import { onMount } from 'svelte';
  import { api, deleteEntry } from './api.js';
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
    try {
      if (await deleteEntry(q)) entries = entries.filter((x) => x.id !== q.id);
    } catch (err) { alert(err.message); }
  }

  // Import ADIF : carnet de trafic uniquement (les écoutes SWL:Y sont écartées par le serveur)
  let importInput;
  let importFile = null;
  let preview = $state(null);
  let importMsg = $state('');
  let importing = $state(false);
  const d8 = (d) => (d ? `${d.slice(6)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : '');

  async function pickFile(e) {
    importFile = e.currentTarget.files?.[0] || null;
    e.currentTarget.value = '';
    preview = null;
    importMsg = '';
    if (!importFile) return;
    importing = true;
    try { preview = await api.importAdif(importFile, false); }
    catch (err) { importMsg = err.message; }
    finally { importing = false; }
  }

  async function confirmImport() {
    importing = true;
    try {
      const r = await api.importAdif(importFile, true);
      importMsg = `${r.added} contact${r.added > 1 ? 's' : ''} importé${r.added > 1 ? 's' : ''} dans le carnet de trafic (sauvegarde faite avant : ${r.backup}).`;
      preview = null;
      importFile = null;
      await load();
    } catch (err) { importMsg = err.message; }
    finally { importing = false; }
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
        <button type="button" onclick={() => importInput.click()} disabled={importing}
                title="Ajouter au carnet de trafic les contacts d'un fichier ADIF (.adi) — les écoutes SWL sont écartées">Importer (ADIF)</button>
        <input bind:this={importInput} type="file" accept=".adi,.adif,.txt" hidden onchange={pickFile} />
        <a class="btn" href="api/export/adif" download
           title="Export ADIF du carnet de trafic uniquement (pour QRZ.com, LoTW…)">Exporter le trafic (ADIF)</a>
      {:else}
        <a class="btn" href="api/export/adif-swl" download
           title="Export ADIF du journal d'écoute uniquement (SWL:Y)">Exporter les écoutes (ADIF)</a>
      {/if}
    </div>
    {#if kind === 'QSO' && (preview || importMsg || importing)}
      <div class="import">
        {#if importing && !preview}
          Lecture du fichier…
        {:else if preview}
          <div>
            <b>{importFile?.name}</b> : {preview.records} enregistrement{preview.records > 1 ? 's' : ''} lu{preview.records > 1 ? 's' : ''}.
            <b class="ok">{preview.new} contact{preview.new > 1 ? 's' : ''} à ajouter</b>{#if preview.new} ({d8(preview.first)} → {d8(preview.last)}){/if}
            {#if preview.duplicates} · {preview.duplicates} déjà dans le carnet{/if}
            {#if preview.swl} · {preview.swl} écoute{preview.swl > 1 ? 's' : ''} SWL écartée{preview.swl > 1 ? 's' : ''}{/if}
            {#if preview.invalid} · {preview.invalid} illisible{preview.invalid > 1 ? 's' : ''}
              ({Object.entries(preview.reasons).map(([k, v]) => `${v} ${k}`).join(', ')}){/if}
          </div>
          {#if preview.sample.length}
            <div class="sample">Exemples : {preview.sample.map((q) => `${q.call} ${d8(q.qso_date)} ${q.band || ''} ${q.mode || ''}`).join(' · ')}</div>
          {/if}
          <div class="import-btns">
            <button type="button" onclick={() => { preview = null; importFile = null; }}>Annuler</button>
            <button type="button" class="primary" onclick={confirmImport} disabled={importing || !preview.new}>
              {importing ? 'Import…' : `Importer ${preview.new} contact${preview.new > 1 ? 's' : ''}`}</button>
          </div>
        {:else}
          <span>{importMsg}</span> <button type="button" class="ghost x" onclick={() => (importMsg = '')}>✕</button>
        {/if}
      </div>
    {/if}
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
  .import { border: 1px solid var(--panel-edge); border-radius: 6px; padding: 8px 12px; margin: 0 0 10px;
            background: rgba(207, 181, 59, 0.06); font-size: 0.86rem; }
  .import .ok { color: var(--ok); }
  .import .sample { color: var(--muted); font-size: 0.78rem; margin-top: 4px; }
  .import-btns { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }
  .import .x { padding: 0 4px; color: var(--muted); }
  .hint { color: var(--muted); font-size: 0.76rem; margin: 8px 0 0; }
</style>
