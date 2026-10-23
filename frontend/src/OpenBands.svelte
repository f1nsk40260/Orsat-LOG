<script>
  // Bandes ouvertes en ce moment, par direction (ionosondes via KC2G) — page du jour seulement
  import { api } from './api.js';

  let data = $state(null);
  async function refresh() { data = await api.openBands().catch(() => ({ ok: false, msg: 'Serveur injoignable.' })); }
  $effect(() => {
    refresh();
    const t = setInterval(refresh, 15 * 60 * 1000);
    return () => clearInterval(t);
  });

  const STATE = { open: 'ouverte', edge: 'en limite', closed: 'fermée' };
  function cellTip(row, col, cell) {
    const where = col.az == null ? 'proche (saut de 600 km)' : `vers ${col.dir} (${col.az}°, saut de 3000 km)`;
    if (!cell.state) return `${row.band} ${where} : pas d'ionosonde assez proche du point de réflexion.`;
    const muf = col.muf != null ? `MUF F2 ${col.muf} MHz` : 'MUF F2 inconnue';
    const es = col.es ? ` · Es ≈ ${col.es} MHz` : '';
    return `${row.band} ${where} : ${STATE[cell.state]}${cell.via === 'Es' ? ' (par sporadique E)' : ''}\n${muf}${es}`;
  }
  function colTip(col) {
    const st = col.stations?.length
      ? col.stations.map((s) => `${s.name} (${s.km} km du point, il y a ${s.age_min} min)`).join('\n')
      : 'aucune ionosonde à moins de 1500 km du point de réflexion';
    return `${col.az == null ? 'Proche : réflexion au-dessus du QTH' : `Direction ${col.dir} (${col.az}°)`}\nMUF ${col.muf ?? '—'} MHz\n${st}`;
  }
</script>

<section class="panel ob">
  <h2 class="panel-title">Bandes ouvertes <span class="count">{data?.ok ? data.computed : ''}</span></h2>
  {#if data?.ok}
    <table>
      <thead>
        <tr>
          <th></th>
          {#each data.columns as c}<th title={colTip(c)}>{c.az == null ? '◎' : c.dir}</th>{/each}
        </tr>
        <tr class="muf">
          <th>MUF</th>
          {#each data.columns as c}<th title={colTip(c)}>{c.muf != null ? Math.round(c.muf) : '—'}</th>{/each}
        </tr>
      </thead>
      <tbody>
        {#each data.rows as row}
          <tr>
            <td class="b">{row.band}</td>
            {#each row.cells as cell, i}
              <td class="c {cell.state ?? 'none'}" class:es={cell.via === 'Es'} title={cellTip(row, data.columns[i], cell)}></td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
    <div class="legend">
      <span><i class="open"></i>ouverte</span><span><i class="edge"></i>en limite</span>
      <span><i class="closed"></i>fermée</span><span><i class="open es"></i>par Es</span>
    </div>
    <p class="src">Limite haute selon la MUF mesurée ; l'absorption de jour sur les bandes basses n'est pas comptée.
      {data.stations_count} ionosondes, KC2G (GIRO, NOAA, INGV, SWS).</p>
  {:else}
    <p class="muted">{data ? data.msg : 'Calcul en cours…'}</p>
  {/if}
</section>

<style>
  .ob { display: flex; flex-direction: column; gap: 6px; }
  .count { color: var(--muted); font-weight: 400; margin-left: 8px; text-transform: none; letter-spacing: 0; }
  table { border-collapse: separate; border-spacing: 2px; width: 100%; font-size: 0.74rem; }
  th { color: var(--gold-soft); font-weight: 600; text-align: center; cursor: help; padding: 0; }
  tr.muf th { color: var(--text); font-weight: 400; font-size: 0.7rem; }
  tr.muf th:first-child { color: var(--muted); }
  td.b { color: var(--text); white-space: nowrap; padding-right: 3px; }
  td.c { height: 14px; border-radius: 3px; cursor: help; }
  .open { background: rgba(95, 191, 107, 0.75); }
  .edge { background: rgba(224, 160, 48, 0.7); }
  .closed { background: rgba(255, 255, 255, 0.05); }
  .none { background: repeating-linear-gradient(45deg, rgba(255,255,255,0.04) 0 3px, transparent 3px 6px); }
  .es { box-shadow: inset 0 0 0 2px var(--gold); }
  .legend { display: flex; gap: 10px; flex-wrap: wrap; font-size: 0.72rem; }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
  .src { font-size: 0.7rem; color: var(--muted); margin: 0; }
  .muted { color: var(--muted); font-size: 0.8rem; margin: 0; }
</style>
