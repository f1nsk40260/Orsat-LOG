<script>
  import { api } from './api.js';
  import { fmtTime } from './util.js';

  let { snapshots = [], isToday = false } = $props();

  let live = $state(null);      // mesure actuelle (page du jour)
  let error = $state('');

  async function refresh() {
    const r = await api.weather().catch((e) => ({ data: null, error: e.message }));
    live = r.data;
    error = r.error || '';
  }

  $effect(() => {
    if (!isToday) { live = null; error = ''; return; }
    refresh();
    const t = setInterval(refresh, 5 * 60 * 1000);
    return () => clearInterval(t);
  });

  // valeur affichée : mesure en direct sur la page du jour, dernier relevé sinon
  const cur = $derived(live ?? (snapshots.length ? snapshots[snapshots.length - 1] : null));

  // tendance de pression sur ~3 h (utile pour la propagation troposphérique VHF/UHF)
  const trend = $derived.by(() => {
    if (!cur?.bar || snapshots.length < 2) return null;
    const last = snapshots[snapshots.length - 1];
    const toMin = (t) => +t.slice(0, 2) * 60 + +t.slice(2, 4);
    const ref = [...snapshots].reverse().find((s) => s.bar != null && toMin(last.time) - toMin(s.time) >= 150);
    return ref ? Math.round((cur.bar - ref.bar) * 10) / 10 : null;
  });

  const DIRS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSO', 'SO', 'OSO', 'O', 'ONO', 'NO', 'NNO'];
  const dirName = (d) => (d == null ? '' : DIRS[Math.round(d / 22.5) % 16]);

  // courbes 24 h : température (échelle à gauche) et pression (échelle à droite)
  const W = 260, H = 90, PADL = 24, PADR = 30, PADB = 14, PADT = 13;
  const xOf = (time) => PADL + ((+time.slice(0, 2) + +time.slice(2, 4) / 60) / 24) * (W - PADL - PADR);
  const xH = (h) => PADL + (h / 24) * (W - PADL - PADR);
  // pas « rond » donnant au plus 5 graduations
  const niceStep = (span) => [0.5, 1, 2, 5, 10, 20, 50].find((st) => span / st <= 4) ?? 100;
  function series(key) {
    const pts = snapshots.filter((s) => s[key] != null);
    if (pts.length < 2) return { path: '', ticks: [] };
    let lo = Math.min(...pts.map((p) => p[key])), hi = Math.max(...pts.map((p) => p[key]));
    if (hi - lo < 1) { lo -= 0.5; hi += 0.5; }
    const step = niceStep(hi - lo);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const y = (v) => H - PADB - ((v - lo) / (hi - lo)) * (H - PADB - PADT);
    const ticks = [];
    for (let v = lo; v <= hi + step / 1000; v += step) ticks.push({ v: step < 1 ? v.toFixed(1) : Math.round(v), y: y(v) });
    return {
      path: pts.map((p, i) => `${i ? 'L' : 'M'}${xOf(p.time).toFixed(1)},${y(p[key]).toFixed(1)}`).join(' '),
      ticks,
    };
  }
  const tSeries = $derived(series('temp'));
  const pSeries = $derived(series('bar'));
  const tMinMax = $derived.by(() => {
    const v = snapshots.map((s) => s.temp).filter((x) => x != null);
    return v.length ? [Math.min(...v), Math.max(...v)] : null;
  });
  let big = $state(false);   // vue agrandie au centre de la page
</script>

{#if big}<div class="zoom-backdrop" onclick={() => (big = false)} role="presentation"></div>{/if}
<section class="panel weather zoomable" class:big>
  <button class="ghost zoom-btn" onclick={() => (big = !big)} title={big ? 'Fermer' : 'Agrandir'}>{big ? '✕' : '⤢'}</button>
  <h2 class="panel-title head">Météo locale
    <!-- carte des vents Windy centrée sur le WebSDR, dans un nouvel onglet -->
    <a class="btn windy" href="https://www.windy.com/?43.663,-1.298,5" target="_blank" rel="noopener" title="Ouvrir la carte Windy">Windy</a>
  </h2>

  {#if cur}
    <div class="main">
      <div class="temp">{cur.temp ?? '—'}<small>°C</small></div>
      <div class="side">
        <div><span>Humidité</span><b>{cur.hum ?? '—'} %</b></div>
        <div><span>Point de rosée</span><b>{cur.dew ?? '—'} °C</b></div>
      </div>
    </div>
    <div class="rows">
      <div>
        <span>Pression</span>
        <b>{cur.bar ?? '—'} hPa
          {#if trend != null}
            <em class:up={trend > 0.5} class:down={trend < -0.5} title="Variation sur 3 h">
              {trend > 0.5 ? '↗' : trend < -0.5 ? '↘' : '→'} {trend > 0 ? '+' : ''}{trend}
            </em>
          {/if}
        </b>
      </div>
      <div>
        <span>Vent</span>
        <b>
          {#if cur.wdir != null}<i class="arrow" style="transform: rotate({cur.wdir + 180}deg)">↑</i>{dirName(cur.wdir)}{/if}
          {cur.wspd ?? '—'} km/h{#if cur.wspdhi} · rafales {cur.wspdhi}{/if}
        </b>
      </div>
      <div><span>Pluie du jour</span><b>{cur.rain ?? '—'} mm{#if cur.rainrate} · {cur.rainrate} mm/h{/if}</b></div>
      {#if cur.solarrad != null || cur.uvi != null}
        <div><span>Soleil</span><b>{cur.solarrad ?? '—'} W/m² · UV {cur.uvi ?? '—'}</b></div>
      {/if}
      {#if tMinMax}
        <div><span>Mini / maxi</span><b>{tMinMax[0]} / {tMinMax[1]} °C</b></div>
      {/if}
    </div>

    {#if tSeries.path || pSeries.path}
      <svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Température et pression sur la journée">
        {#each tSeries.ticks as t}
          <line x1={PADL} x2={W - PADR} y1={t.y} y2={t.y} class="hgrid" />
          <text x={PADL - 3} y={t.y + 3} class="axis at" text-anchor="end">{t.v}</text>
        {/each}
        {#each pSeries.ticks as t}
          <text x={W - PADR + 3} y={t.y + 3} class="axis ap" text-anchor="start">{t.v}</text>
        {/each}
        {#if tSeries.path}<text x={PADL - 3} y="6" class="axis at unit" text-anchor="end">°C</text>{/if}
        {#if pSeries.path}<text x={W - PADR + 3} y="6" class="axis ap unit" text-anchor="start">hPa</text>{/if}
        {#each [0, 6, 12, 18, 24] as h}
          <line x1={xH(h)} x2={xH(h)} y1={PADT} y2={H - PADB} class="grid" />
          <text x={xH(h)} y={H - 3} class="axis" text-anchor="middle">{h}h</text>
        {/each}
        {#if pSeries.path}<path d={pSeries.path} class="p" />{/if}
        {#if tSeries.path}<path d={tSeries.path} class="t" />{/if}
      </svg>
      <div class="legend"><span><i class="lt"></i>température</span><span><i class="lp"></i>pression</span></div>
    {/if}

    <div class="foot muted">
      {#if live?.epoch}mesure de {new Date(live.epoch * 1000).toISOString().slice(11, 16)} UTC · {/if}
      {snapshots.length} relevé{snapshots.length > 1 ? 's' : ''} ce jour
    </div>
  {:else}
    <p class="muted">
      {#if isToday}
        {error ? `Weathercloud : ${error}` : 'Lecture de la station…'}
      {:else}
        Aucun relevé météo ce jour-là.
      {/if}
    </p>
  {/if}
  {#if isToday && error && cur}<p class="err">Weathercloud : {error} (dernier relevé affiché)</p>{/if}
</section>

<style>
  .weather { display: flex; flex-direction: column; gap: 6px; }
  .head { display: flex; align-items: center; gap: 10px; }
  .windy { padding: 1px 8px; font-size: 0.68rem; letter-spacing: 0.12em; }
  .main { display: flex; align-items: center; gap: 14px; }
  .temp { font-size: 2.1rem; color: var(--gold); font-weight: 600; text-shadow: 0 0 10px rgba(207, 181, 59, 0.3); }
  .temp small { font-size: 1rem; color: var(--gold-soft); }
  .side { flex: 1; font-size: 0.82rem; }
  .side div, .rows div { display: flex; justify-content: space-between; gap: 8px; }
  .rows { font-size: 0.84rem; display: flex; flex-direction: column; gap: 2px; }
  span { color: var(--muted); }
  b { font-weight: 500; text-align: right; }
  em { font-style: normal; color: var(--muted); margin-left: 4px; }
  em.up { color: var(--ok); } em.down { color: var(--warn); }
  .arrow { display: inline-block; font-style: normal; color: var(--gold); margin-right: 3px; }
  .chart { width: 100%; height: auto; margin-top: 4px; }
  .grid { stroke: rgba(207, 181, 59, 0.12); }
  .hgrid { stroke: rgba(207, 181, 59, 0.07); }
  .axis { fill: var(--muted); font-size: 9px; }
  .at { fill: var(--gold); font-size: 6.5px; } .ap { fill: rgb(140, 185, 230); font-size: 6.5px; }
  .unit { font-size: 6px; opacity: 0.8; }
  .t { fill: none; stroke: var(--gold); stroke-width: 2; }
  .p { fill: none; stroke: rgb(140, 185, 230); stroke-width: 1.5; stroke-dasharray: 4 2; }
  .legend { display: flex; gap: 12px; font-size: 0.72rem; }
  .legend i { display: inline-block; width: 12px; height: 3px; margin-right: 4px; vertical-align: 2px; }
  .lt { background: var(--gold); } .lp { background: rgb(140, 185, 230); }
  .foot { font-size: 0.72rem; }
  .muted { color: var(--muted); font-size: 0.82rem; margin: 0; }
  .err { color: var(--warn); font-size: 0.74rem; margin: 0; }
  /* vue agrandie */
  .big .temp { font-size: 3.6rem; } .big .temp small { font-size: 1.6rem; }
  .big .side, .big .rows { font-size: 1.1rem; gap: 4px; }
  .big .legend { font-size: 0.95rem; } .big .legend i { width: 18px; }
  .big .foot, .big .muted { font-size: 0.9rem; }
  .big .chart { max-height: 56vh; }
</style>
