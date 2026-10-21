<script>
  import { fmtDate, fmtTime } from './util.js';
  import { api } from './api.js';
  import EditEntry from './EditEntry.svelte';
  import { tciActive, tciTune, tciModeFor } from './tciBrowser.js';

  // showDate = false sur la page du jour (la date est déjà en tête de page)
  // onchanged : appelé après une modification ou une suppression faite dans le formulaire d'édition
  let { entries, ondelete, ondate, onchanged, showDate = true, empty = 'Aucune entrée.' } = $props();
  let editing = $state(null);   // entrée ouverte dans le formulaire d'édition

  // Clic sur une fréquence : SWL = la page WebSDR se recale, QSO / groupe = le transceiver
  async function tune(q) {
    try {
      // QSO : AetherSDR, par la liaison TCI de ce navigateur ; SWL : la page du WebSDR
      if (q.kind !== 'SWL') {
        if (!tciActive() || !tciTune(q.freq, tciModeFor(q))) throw new Error('Transceiver TCI non connecté (AetherSDR, sur ce PC)');
        return;
      }
      await api.tune(q);
    } catch (err) {
      alert(err.message);
    }
  }
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        {#if showDate}<th>Date</th>{/if}
        <th>UTC</th><th>Type</th><th>Indicatif / station</th><th>Bande</th><th>Fréq.</th><th>Mode</th>
        <th>Env.</th><th title="RST reçu ou SINPO">Reçu</th><th>Locator</th><th>Dist.</th><th>Az.</th>
        <th title="Flux solaire / indice K au moment de l'entrée">SFI / K</th><th>Nom / émetteur</th><th></th>
      </tr>
    </thead>
    <tbody>
      {#each entries as q (q.id)}
        <tr class:swl={q.kind === 'SWL'} ondblclick={() => (editing = q)} title="Double-clic : modifier">
          {#if showDate}
            <td>
              {#if ondate}
                <button class="ghost datelink" title="Ouvrir la page de ce jour" onclick={() => ondate(q.qso_date)}>{fmtDate(q.qso_date)}</button>
              {:else}{fmtDate(q.qso_date)}{/if}
            </td>
          {/if}
          <td class="mono">{fmtTime(q.time_on)}</td>
          <td>
            {#if q.session_name}
              <span class="tag tag-grp" title={q.session_name}>GRP</span>
            {:else}
              <span class="tag" class:tag-swl={q.kind === 'SWL'}>{q.kind}</span>
            {/if}
          </td>
          <td class="mono call-cell" title={q.comment}>{q.call}{#if q.kind !== 'SWL' && q.qrz_state}<span
              class="qrz q-{q.qrz_state}"
              title={q.qrz_state === 'synced' ? 'Synchronisé avec QRZ.com' : q.qrz_state === 'pending' ? 'En attente d\'envoi vers QRZ.com' : `Refusé par QRZ.com : ${q.qrz_error || ''}`}
              >{q.qrz_state === 'synced' ? '✓' : q.qrz_state === 'pending' ? '⏳' : '⚠'}</span>{/if}</td>
          <td>{q.band}</td>
          <td class="mono">
            {#if q.freq}
              <button class="ghost freqlink" title={q.kind === 'SWL' ? 'Ramener le WebSDR sur cette fréquence' : 'Régler le transceiver sur cette fréquence'} onclick={() => tune(q)}>{(q.freq / 1e6).toFixed(3)}</button>
            {/if}
          </td>
          <td>{q.submode || q.mode}</td>
          <td class="mono">{q.rst_sent}</td>
          <td class="mono">{q.rst_rcvd}</td>
          <td class="mono">{q.gridsquare}</td>
          <td>{q.distance_km != null ? `${q.distance_km} km` : ''}</td>
          <td>{q.bearing != null ? `${q.bearing}°` : ''}</td>
          <td>{q.sfi ?? ''}{q.k_index != null ? ` / ${q.k_index}` : ''}</td>
          <td>{q.kind === 'SWL' ? q.qth : q.name}</td>
          <td>
            <button class="ghost edit" title="Modifier cette entrée" onclick={() => (editing = q)}>✎</button>
            {#if ondelete}
              <button class="ghost del" title="Supprimer cette entrée" onclick={() => ondelete(q)}>✕</button>
            {/if}
          </td>
        </tr>
      {:else}
        <tr><td colspan="15" class="muted empty">{empty}</td></tr>
      {/each}
    </tbody>
  </table>
</div>

{#if editing}
  <EditEntry entry={editing} onclose={() => (editing = null)}
             onsaved={() => { editing = null; onchanged?.(); }}
             ondeleted={() => { editing = null; onchanged?.(); }} />
{/if}

<style>
  .table-wrap { overflow: auto; flex: 1; min-height: 0; }
  td { white-space: nowrap; padding: 5px 6px; }
  th { padding: 6px; }
  td.call-cell { white-space: normal; min-width: 90px; }
  .call-cell { color: var(--gold); font-weight: 600; }
  .tag { font-size: 0.7rem; border: 1px solid var(--gold-soft); color: var(--gold); border-radius: 4px; padding: 0 5px; }
  .tag-grp { border-color: rgba(95, 191, 107, 0.6); color: var(--ok); cursor: help; }
  .tag-swl { border-color: rgba(120, 170, 220, 0.6); color: rgb(140, 185, 230); }
  tr.swl .call-cell { color: rgb(160, 200, 240); }
  .qrz { margin-left: 5px; font-size: 0.72rem; font-weight: 400; cursor: help; }
  .q-synced { color: var(--ok); opacity: 0.7; }
  .q-pending { color: var(--muted); }
  .q-error { color: var(--bad); }
  .datelink { padding: 0; color: var(--text); text-decoration: underline dotted var(--gold-soft); }
  .datelink:hover { color: var(--gold); box-shadow: none; }
  .edit { padding: 0 4px; color: var(--gold-soft); }
  .edit:hover { color: var(--gold); box-shadow: none; }
  .freqlink { padding: 0; color: var(--text); font: inherit; }
  .freqlink:hover { color: var(--gold); box-shadow: none; text-decoration: underline dotted var(--gold-soft); }
  .del { padding: 0 6px; color: var(--muted); }
  .del:hover { color: var(--bad); }
  .empty { text-align: center; padding: 24px; }
  .muted { color: var(--muted); }
</style>
