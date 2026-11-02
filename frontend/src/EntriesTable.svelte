<script>
  import { fmtDate, fmtTime } from './util.js';
  import { tipSfi, tipK } from './proptips.js';
  import { api } from './api.js';
  import EditEntry from './EditEntry.svelte';
  import QsoCard from './QsoCard.svelte';
  import { tciActive, tciTune, tciModeFor } from './tciBrowser.js';
  import { traceTarget } from './tracetarget.svelte.js';
  import { locToLatLon } from './locator.js';
  // ouvre la fenêtre Trajet sur le locator de cette entrée
  const toTrace = (q) => { traceTarget.loc = q.gridsquare.toUpperCase(); traceTarget.call = q.call || ''; traceTarget.open = true; };

  // showDate = false sur la page du jour (la date est déjà en tête de page)
  // onchanged : appelé après une modification ou une suppression faite dans le formulaire d'édition
  // syncCols = true : colonnes QRZ et EQSL (carnet de trafic) au lieu des petits repères après l'indicatif
  let { entries, ondelete, ondate, onchanged, showDate = true, syncCols = false, empty = 'Aucune entrée.' } = $props();
  let editing = $state(null);   // entrée ouverte dans le formulaire d'édition
  let card = $state(null);      // entrée ouverte dans la fiche (conditions du QSO)

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
        <th>Env.</th><th title="RST reçu ou SINPO">Reçu</th><th>Locator</th><th>Pays</th><th>Dist.</th><th>Az.</th>
        <th title="Flux solaire / indice K au moment de l'entrée">SFI / K</th><th>Nom / émetteur</th>
        {#if syncCols}<th class="sync" title="Logbook QRZ.com">QRZ</th><th class="sync" title="eQSL.cc (QSO seulement, pas les QSO de groupe)">EQSL</th>{/if}<th></th>
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
          <td class="mono call-cell"><button type="button" class="ghost calllink" onclick={() => (card = q)}
              title={`Fiche du QSO : carte, ligne grise et conditions de propagation${q.comment ? ' — ' + q.comment : ''}`}>{q.call}</button>{#if !syncCols && q.kind !== 'SWL' && q.qrz_state}<span
              class="qrz q-{q.qrz_state}"
              title={q.qrz_state === 'synced' ? 'Synchronisé avec QRZ.com' : q.qrz_state === 'pending' ? 'En attente d\'envoi vers QRZ.com' : `Refusé par QRZ.com : ${q.qrz_error || ''}`}
              >{q.qrz_state === 'synced' ? '✓' : q.qrz_state === 'pending' ? '⏳' : '⚠'}</span>{/if}{#if !syncCols && q.kind !== 'SWL' && (q.eqsl_rcvd || q.eqsl_state === 'synced' || q.eqsl_state === 'error')}<span
              class="eqsl e-{q.eqsl_rcvd ? 'rcvd' : q.eqsl_state}"
              title={q.eqsl_rcvd ? `eQSL reçue du correspondant (${fmtDate(q.eqsl_rcvd)})` : q.eqsl_state === 'synced' ? 'Envoyé à eQSL.cc' : `Refusé par eQSL.cc : ${q.eqsl_error || ''}`}
              >e</span>{/if}</td>
          <td>{q.band}</td>
          <td class="mono">
            {#if q.freq}
              <button class="ghost freqlink" title={q.kind === 'SWL' ? 'Ramener le WebSDR sur cette fréquence' : 'Régler le transceiver sur cette fréquence'} onclick={() => tune(q)}>{(q.freq / 1e6).toFixed(3)}</button>
            {/if}
          </td>
          <td>{q.submode || q.mode}</td>
          <td class="mono">{q.rst_sent}</td>
          <td class="mono">{q.rst_rcvd}</td>
          <td class="mono">
            {#if q.gridsquare && locToLatLon(q.gridsquare)}
              <button class="ghost loclink" title="Voir ce locator sur la courbe des distances (fenêtre Trajet)" onclick={() => toTrace(q)}>{q.gridsquare} <span class="lt">〽</span></button>
            {:else}{q.gridsquare}{/if}
          </td>
          <td class="country" title={q.country ? `${q.country}${q.dxcc ? ` · DXCC ${q.dxcc}` : ''}${q.cont ? ` · ${q.cont}` : ''}${q.cqz ? ` · CQ ${q.cqz}` : ''}${q.ituz ? ` · ITU ${q.ituz}` : ''}` : ''}>
            {q.country || ''}{#if q.confirmed}<span class="conf" title={`Confirmé (${q.confirmed})`}>◆</span>{/if}
          </td>
          <td title={q.my_gridsquare && q.kind !== 'SWL' ? `depuis ${q.my_gridsquare}` : ''}>{q.distance_km != null ? `${q.distance_km} km` : ''}</td>
          <td>{q.bearing != null ? `${q.bearing}°` : ''}</td>
          <td title={q.sfi == null && q.k_index == null ? '' : (q.solar_src === 'GFZ' ? `Archive GFZ Potsdam : SFI du jour, K du créneau de 3 h${q.a_index != null ? `, A ${q.a_index}` : ''}` : (q.solar_src === 'hamqsl' ? 'Relevé hamqsl au moment de la saisie' : 'Relevé NOAA au moment de la saisie'))
                + (q.sfi != null ? '\n\n' + tipSfi(q.sfi) : '') + (q.k_index != null ? '\n\n' + tipK(q.k_index) : '')}
              class:archive={q.solar_src === 'GFZ'}>{q.sfi != null ? Math.round(q.sfi) : ''}{q.k_index != null ? ` / ${+(+q.k_index).toFixed(1)}` : ''}</td>
          <td>{q.kind === 'SWL' ? q.qth : q.name}</td>
          {#if syncCols}
            <td class="sync">{#if q.qrz_state === 'synced'}<span class="ok" title="Synchronisé avec QRZ.com">✓</span>{:else if q.qrz_state === 'pending'}<span
              class="q-pending" title="En attente d'envoi vers QRZ.com">⏳</span>{:else if q.qrz_state === 'error'}<span
              class="q-error" title={`Refusé par QRZ.com : ${q.qrz_error || ''}`}>⚠</span>{/if}</td>
            <td class="sync">{#if q.eqsl_state === 'synced'}<span
              class="ok" title="Envoyé à eQSL.cc">✓</span>{:else if q.session_id}<span class="q-pending" title="QSO de groupe : jamais envoyé à eQSL">—</span>{:else if q.eqsl_state === 'error'}<span
              class="q-error" title={`Refusé par eQSL.cc : ${q.eqsl_error || ''}`}>⚠</span>{/if}{#if q.eqsl_rcvd}<span
              class="conf" title={`eQSL reçue du correspondant (${fmtDate(q.eqsl_rcvd)})`}>◆</span>{/if}</td>
          {/if}
          <td>
            <button class="ghost edit" title="Modifier cette entrée" onclick={() => (editing = q)}>✎</button>
            {#if ondelete}
              <button class="ghost del" title="Supprimer cette entrée" onclick={() => ondelete(q)}>✕</button>
            {/if}
          </td>
        </tr>
      {:else}
        <tr><td colspan={syncCols ? 18 : 16} class="muted empty">{empty}</td></tr>
      {/each}
    </tbody>
  </table>
</div>

{#if card}
  <QsoCard entry={card} onclose={() => (card = null)}
           onedit={(q) => { card = null; editing = q; }} />
{/if}

{#if editing}
  <EditEntry entry={editing} onclose={() => (editing = null)}
             onsaved={() => { editing = null; onchanged?.(); }}
             ondeleted={() => { editing = null; onchanged?.(); }} />
{/if}

<style>
  .loclink { padding: 0 4px; font: inherit; color: inherit; border: 0; background: none; cursor: pointer; white-space: nowrap; }
  .loclink:hover { color: var(--gold); text-decoration: underline; }
  .loclink .lt { color: rgb(90, 200, 255); font-size: 1.15em; }
  .table-wrap { overflow: auto; flex: 1; min-height: 0; }
  td { white-space: nowrap; padding: 5px 6px; }
  th { padding: 6px; }
  td.call-cell { white-space: normal; min-width: 90px; }
  .call-cell { color: var(--gold); font-weight: 600; }
  .tag { font-size: 0.7rem; border: 1px solid var(--gold-soft); color: var(--gold); border-radius: 4px; padding: 0 5px; }
  .tag-grp { border-color: rgba(95, 191, 107, 0.6); color: var(--ok); cursor: help; }
  .tag-swl { border-color: rgba(120, 170, 220, 0.6); color: rgb(140, 185, 230); }
  tr.swl .call-cell { color: rgb(160, 200, 240); }
  .calllink { padding: 0; font: inherit; color: inherit; font-weight: inherit; letter-spacing: inherit; }
  .calllink:hover { color: #fff; box-shadow: none; text-decoration: underline dotted var(--gold-soft); }
  .country { white-space: nowrap; max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
  .conf { color: var(--gold); margin-left: 4px; font-size: 0.7rem; cursor: help; }
  td.archive { color: var(--muted); }
  .qrz { margin-left: 5px; font-size: 0.72rem; font-weight: 400; cursor: help; }
  .q-synced { color: var(--ok); opacity: 0.7; }
  .q-pending { color: var(--muted); }
  .q-error { color: var(--bad); }
  th.sync, td.sync { text-align: center; width: 3.2em; }
  td.sync .ok { color: var(--ok); font-weight: 700; cursor: help; }
  td.sync .q-pending, td.sync .q-error { cursor: help; }
  /* repère eQSL.cc : « e » discret, vert quand l'eQSL du correspondant est reçue */
  .eqsl { margin-left: 4px; font-size: 0.68rem; font-weight: 600; font-style: italic; cursor: help; }
  .e-synced { color: var(--gold-soft); }
  .e-rcvd { color: var(--ok); }
  .e-error { color: var(--bad); }
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
