<script>
  // Bandes ouvertes en ce moment, par direction (ionosondes via KC2G) — page du jour seulement
  import { api } from './api.js';
  import SkipMap from './SkipMap.svelte';

  let { onclose = null } = $props();
  let data = $state(null);
  let skipMap = $state();
  async function refresh() { skipMap?.refresh();
    data = await api.openBands().catch(() => ({ ok: false, msg: 'Serveur injoignable.' })); }
  $effect(() => {
    refresh();
    const t = setInterval(refresh, 15 * 60 * 1000);
    return () => clearInterval(t);
  });

  const STATE = { open: 'ouverte', edge: 'en limite', closed: 'fermée', weak: 'ouverte mais affaiblie', absorbed: 'absorbée (couche D)' };
  // portée par bande : meilleure direction, ou celle choisie d'un clic sur l'en-tête de la grille
  let sel = $state(null);
  const reachRows = $derived(data?.ok && data.reach ? (sel ? data.reach.dirs[sel] : data.reach.best) : []);
  const RANGES = [['d100', '≤100', '0 à 100 km (NVIS)'], ['d300', '≤300', '100 à 300 km (NVIS)'], ['d900', '≤900', '300 à 900 km'],
                  ['d2500', '≤2500', '900 à 2500 km'], ['dx', '>2500', '2500 km et plus']];
  function reachTip(row, key, label) {
    const c = row[key];
    if (!c.state) return `${row.band} ${label} : pas d'ionosonde assez proche.`;
    return `${row.band} · ${label}${c.dir && !sel ? ` · meilleure direction ${c.dir}` : ''} : ${STATE[c.state]}`
      + `\nMUF ${c.muf ?? '—'} MHz · absorption estimée ${c.db} dB`;
  }
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

<div class="backdrop" onclick={onclose} role="presentation"></div>
<section class="panel ob">
  <h2 class="panel-title">Bandes ouvertes et portée par bande <span class="count">{data?.ok ? `calcul de ${data.computed}` : ''}</span>
    <button class="ghost close" onclick={refresh} title="Recalculer maintenant">↻</button>
    <button class="ghost close" onclick={onclose} title="Fermer">✕</button></h2>
  {#if data?.ok}
   <div class="blocks">
   <div class="blk">
    <h3 class="sub">Par direction <span>MUF seule · clic sur une direction pour la portée</span></h3>
    <table>
      <thead>
        <tr>
          <th></th>
          {#each data.columns as c}
            {#if c.az == null}<th title={colTip(c)}>◎</th>
            {:else}<th class="pick" class:sel={sel === c.dir} title={colTip(c) + '\n\nClic : portée par bande dans cette direction (re-clic : meilleure direction)'}
                       onclick={() => (sel = sel === c.dir ? null : c.dir)}>{c.dir}</th>{/if}
          {/each}
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
   </div>
   <div class="blk">
    {#if reachRows.length}
      <h3 class="sub">Portée par bande <span>{sel ? `vers ${sel}` : 'meilleure direction'}</span>
        {#if sel}<button class="ghost tiny" onclick={() => (sel = null)} title="Revenir à la meilleure direction">✕</button>{/if}</h3>
      <table class="reach">
        <thead><tr><th></th>{#each RANGES as [, l, d]}<th title={d}>{l}</th>{/each}<th title="Zone de silence : distance en dessous de laquelle la bande est muette">silence</th></tr></thead>
        <tbody>
          {#each reachRows as row}
            <tr>
              <td class="b">{row.band}</td>
              {#each RANGES as [k, l, d]}<td class="c {row[k].state ?? 'none'}" title={reachTip(row, k, d)}></td>{/each}
              <td class="skip" title={row.skip ? `Zone de silence : rien en dessous de ${row.skip} km, la bande passe plus loin` : ''}>{row.skip ? `< ${row.skip}` : ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      <div class="legend">
        <span><i class="open"></i>ouverte</span><span><i class="edge"></i>limite</span>
        <span><i class="weak"></i>affaiblie</span><span><i class="absorbed"></i>absorbée</span>
      </div>
    {/if}
   </div>
   </div>
    <div class="blk wide">
      <h3 class="sub">Carte des zones de silence <span>depuis le QTH, jusqu'à 5000 km · une bande à la fois</span></h3>
      <SkipMap bind:this={skipMap} />
    </div>
    <p class="src">Distances en km. Onde de sol non calculée. Plafond : MUF mesurée. Plancher : absorption de jour <b>estimée</b> (modèle George-Bradley, R {data.reach?.ssn ?? '—'} déduit du SFI).
      La grille de gauche ne tient compte que de la MUF.
      {data.stations_count} ionosondes, KC2G (GIRO, NOAA, INGV, SWS).</p>
  {:else}
    <p class="muted">{data ? data.msg : 'Calcul en cours…'}</p>
  {/if}
</section>

<style>
  .backdrop { position: fixed; inset: 0; z-index: 20; background: rgba(0, 0, 0, 0.55); }
  .ob { position: fixed; z-index: 21; top: 70px; left: 50%; transform: translateX(-50%);
        width: min(1180px, calc(100vw - 32px)); max-height: calc(100vh - 90px); overflow-y: auto;
        display: flex; flex-direction: column; gap: 10px; background: #1e1d18; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.7); }
  .ob .panel-title { display: flex; align-items: center; gap: 8px; }
  .close { margin-left: auto; padding: 0 8px; font-size: 1rem; }
  .close + .close { margin-left: 0; }
  .blocks { display: flex; gap: 28px; flex-wrap: wrap; align-items: flex-start; }
  .blk.wide { border-top: 1px solid var(--panel-edge); padding-top: 10px; }
  .blk { flex: 1 1 460px; display: flex; flex-direction: column; gap: 8px; }
  table { font-size: 0.9rem !important; }
  td.c { height: 24px !important; }
  td.skip { font-size: 0.82rem !important; }
  table.reach th { font-size: 0.8rem !important; }
  .legend { font-size: 0.82rem !important; }
  .src { font-size: 0.8rem !important; }
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
  .weak { background: repeating-linear-gradient(45deg, rgba(95, 191, 107, 0.6) 0 3px, rgba(95, 191, 107, 0.2) 3px 6px); }
  .absorbed { background: rgba(214, 80, 80, 0.45); }
  th.pick { cursor: pointer; }
  th.pick:hover, th.pick.sel { color: #1a1606; background: var(--gold); border-radius: 3px; }
  .sub { margin: 0; font-size: 0.85rem; color: var(--gold); letter-spacing: 0.06em; text-transform: uppercase; display: flex; align-items: center; gap: 6px; }
  .sub span { color: var(--muted); text-transform: none; letter-spacing: 0; font-weight: 400; }
  .tiny { padding: 0 5px; font-size: 0.75rem; }
  table.reach td.c { height: 13px; }
  table.reach th { font-size: 0.64rem; white-space: nowrap; font-weight: 500; }
  td.skip { color: var(--warn); font-size: 0.68rem; text-align: left; width: 1%; white-space: nowrap; }
  .legend { display: flex; gap: 10px; flex-wrap: wrap; font-size: 0.72rem; }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
  .src { font-size: 0.7rem; color: var(--muted); margin: 0; }
  .muted { color: var(--muted); font-size: 0.8rem; margin: 0; }
</style>
