<script>
  // Ce que le WebSDR entendait ce jour-là : stations FT8 / FT4 / JS8 / WSPR décodées par l'autorun
  // de PhantomSDR-ORSAT. Grille bande × heure UTC (nombre de stations), plus lointaines par bande.
  let { heard = null } = $props();

  const ORDER = ['160m', '80m', '60m', '40m', '30m', '20m', '17m', '15m', '12m', '10m', '6m', '4m', '2m'];
  const rows = $derived.by(() => {
    const by = {};
    for (const g of heard?.grid || []) (by[g.band] ??= {})[g.hour] = g;
    const rank = (b) => (ORDER.includes(b) ? ORDER.indexOf(b) : 99);
    return Object.keys(by).sort((a, b) => rank(a) - rank(b)).map((band) => ({ band, hours: by[band] }));
  });
  const maxN = $derived(Math.max(1, ...(heard?.grid || []).map((g) => g.stations)));
  // Intensité : racine du nombre, pour que les heures calmes restent visibles
  const shade = (n) => (n ? `rgba(207, 181, 59, ${(0.15 + 0.85 * Math.sqrt(n / maxN)).toFixed(2)})` : 'rgba(255,255,255,0.03)');
  const km = (v) => (v == null ? '' : `${v.toLocaleString('fr-FR')} km`);
</script>

<section class="panel heard">
  <h2 class="panel-title">Entendu par le WebSDR</h2>
  {#if rows.length}
    <div class="grid" style:grid-template-columns="34px repeat(24, 1fr)">
      {#each rows as r}
        <span class="b">{r.band}</span>
        {#each Array(24) as _, h}
          {@const c = r.hours[h]}
          <span class="cell" style:background={shade(c?.stations)}
                title={c ? `${r.band} · ${String(h).padStart(2, '0')} h UTC : ${c.stations} station${c.stations > 1 ? 's' : ''} décodée${c.stations > 1 ? 's' : ''}${c.max_km ? `, la plus lointaine à ${km(c.max_km)}` : ''}` : `${r.band} · ${String(h).padStart(2, '0')} h UTC : rien décodé`}></span>
        {/each}
      {/each}
      <span></span>
      {#each Array(24) as _, h}<span class="hh">{h % 6 === 0 ? h : ''}</span>{/each}
    </div>
    {#if heard.detail && Object.keys(heard.farthest || {}).length}
      <div class="far">
        <div class="lbl">Les plus lointaines</div>
        {#each Object.entries(heard.farthest) as [band, list]}
          <div class="fr"><span class="fb">{band}</span>
            {#each list.slice(0, 3) as f}
              <span class="mono" title={`${f.call} ${f.grid} · ${f.mode.toUpperCase()} · ${f.snr ?? '?'} dB · ${String(f.hour).padStart(2, '0')} h UTC · azimut ${f.bearing}°`}>{f.call} <i>{km(f.km)}</i></span>
            {/each}
          </div>
        {/each}
      </div>
    {/if}
    <p class="src">Stations FT8 / FT4 / JS8 / WSPR décodées par l'autorun du WebSDR (IN93LR), heure par heure.</p>
  {:else}
    <p class="muted">Rien d'enregistré ce jour-là. Les décodages arrivent quand l'autorun du WebSDR est en service (panneau admin).</p>
  {/if}
</section>

<style>
  .heard { display: flex; flex-direction: column; gap: 6px; }
  .grid { display: grid; gap: 2px; align-items: center; }
  .b { font-size: 0.68rem; color: var(--gold-soft); }
  .cell { height: 12px; border-radius: 2px; cursor: help; }
  .hh { font-size: 0.6rem; color: var(--muted); }
  .far { font-size: 0.76rem; }
  .lbl { color: var(--muted); font-size: 0.7rem; margin-bottom: 2px; }
  .fr { display: flex; flex-wrap: wrap; gap: 4px 10px; }
  .fb { color: var(--gold-soft); min-width: 30px; }
  .fr i { color: var(--muted); font-style: normal; }
  .src { font-size: 0.68rem; color: var(--muted); margin: 0; }
  .muted { color: var(--muted); font-size: 0.82rem; margin: 0; }
</style>
