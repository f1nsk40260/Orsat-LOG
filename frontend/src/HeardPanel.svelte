<script>
  // Ce que le WebSDR entendait ce jour-là : stations FT8 / FT4 / JS8 / WSPR décodées par l'autorun
  // de PhantomSDR-ORSAT. Grille bande × heure UTC (nombre de stations), plus lointaines par bande.
  let { heard = null, large = false, onclose = null, day = '' } = $props();
  const d8 = (d) => (d ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : '');

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
  import HeardMap from './HeardMap.svelte';
  // Fenêtre : filtres de la carte choisis à la souris dans la grille
  let selBand = $state('');
  let selHour = $state(null);
  const BAND_COLORS = { '160m': '#8e7cc3', '80m': '#6fa8dc', '60m': '#76a5af', '40m': '#93c47d', '30m': '#b6d7a8',
    '20m': '#ffd966', '17m': '#f6b26b', '15m': '#e69138', '12m': '#e06666', '10m': '#c27ba0', '6m': '#d5a6bd' };
  function pickBand(b) { selBand = selBand === b && selHour == null ? '' : b; selHour = null; }
  function pickCell(b, h) {
    if (selBand === b && selHour === h) { selHour = null; return; }
    selBand = b; selHour = h;
  }
  const km = (v) => (v == null ? '' : `${v.toLocaleString('fr-FR')} km`);
</script>

{#if large}<div class="backdrop" onclick={onclose} role="presentation"></div>{/if}
<section class="panel heard" class:large role={large ? 'dialog' : undefined} aria-label="Entendu par le WebSDR">
  <div class="head">
    <h2 class="panel-title">Entendu par le WebSDR{#if large && day}<span class="when"> · {d8(day)} (UTC)</span>{/if}</h2>
    {#if onclose}<button type="button" onclick={onclose}>Fermer</button>{/if}
  </div>
  {#if rows.length}
    <div class="grid" style:grid-template-columns={large ? "48px repeat(24, 1fr)" : "34px repeat(24, 1fr)"}>
      {#each rows as r}
        {#if large}<button type="button" class="b bb" class:on={selBand === r.band} onclick={() => pickBand(r.band)}>{r.band}</button>
        {:else}<span class="b">{r.band}</span>{/if}
        {#each Array(24) as _, h}
          {@const c = r.hours[h]}
          <span class="cell" class:sel={large && selBand === r.band && (selHour === h || selHour == null)}
                class:click={large} onclick={() => large && pickCell(r.band, h)} role="presentation"
                style:background={shade(c?.stations)}
                title={c ? `${r.band} · ${String(h).padStart(2, '0')} h UTC : ${c.stations} station${c.stations > 1 ? 's' : ''} décodée${c.stations > 1 ? 's' : ''}${c.max_km ? `, la plus lointaine à ${km(c.max_km)}` : ''}` + (large ? '\nClic : carte de cette heure' : '') : `${r.band} · ${String(h).padStart(2, '0')} h UTC : rien décodé`}></span>
        {/each}
      {/each}
      <span></span>
      {#each Array(24) as _, h}<span class="hh">{large ? String(h).padStart(2, '0') : h % 6 === 0 ? h : ''}</span>{/each}
    </div>
    {#if large}
      <div class="filters">
        <span class="muted">Carte :</span>
        <button type="button" class:on={!selBand && selHour == null} onclick={() => { selBand = ''; selHour = null; }}>Toutes bandes, toute la journée</button>
        {#each rows as r}
          <button type="button" class:on={selBand === r.band} onclick={() => pickBand(r.band)}
                  title="N'afficher que le {r.band} (clic sur une case de la grille : une seule heure)">
            <i class="dot" style:background={BAND_COLORS[r.band] || '#e07a5f'}></i>{r.band}</button>
        {/each}
      </div>
      <HeardMap {day} band={selBand} hour={selHour} colors={BAND_COLORS} />
    {/if}
    {#if heard.detail && Object.keys(heard.farthest || {}).length}
      <div class="far">
        <div class="lbl">Les plus lointaines</div>
        {#each Object.entries(heard.farthest) as [band, list]}
          <div class="fr"><span class="fb">{band}</span>
            {#each list.slice(0, large ? 5 : 3) as f}
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
  .head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
  .when { color: var(--muted); font-weight: 400; letter-spacing: 0; text-transform: none; }
  .backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.65); z-index: 40; }
  .heard.large {
    position: fixed; z-index: 41; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: min(1100px, calc(100vw - 32px)); max-height: calc(100vh - 32px); overflow-y: auto; gap: 12px; padding: 16px 20px;
  }
  .large .grid { gap: 3px; }
  .bb { background: none; border: 1px solid transparent; padding: 0 4px; text-align: left; cursor: pointer; color: var(--gold-soft); }
  .bb.on { border-color: var(--gold); color: var(--gold); }
  .cell.click { cursor: pointer; }
  .cell.sel { outline: 1px solid var(--gold); outline-offset: 0; }
  .filters { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 0.8rem; }
  .filters button { padding: 2px 9px; font-size: 0.8rem; }
  .filters button.on { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; vertical-align: 0; }
  .large .b { font-size: 0.85rem; }
  .large .cell { height: 24px; }
  .large .hh { font-size: 0.7rem; text-align: center; }
  .large .far { font-size: 0.88rem; }
  .large .lbl { font-size: 0.8rem; }
  .large .fr { padding: 2px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
  .large .fb { min-width: 44px; }
  .large .src { font-size: 0.75rem; }
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
