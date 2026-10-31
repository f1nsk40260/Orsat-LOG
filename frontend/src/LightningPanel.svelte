<script>
  // Orages (Blitzortung.org) et bruit de fond mesuré par ORSAT : distinguer une bande fermée d'une bande noyée dans le QRN.
  import { api } from './api.js';

  let { buckets = [], noise = [], isToday = false } = $props();

  let live = $state(null);
  let error = $state('');

  async function refresh() {
    try { live = await api.lightning(); error = ''; }
    catch (e) { error = e.message; }
  }

  $effect(() => {
    if (!isToday) { live = null; error = ''; return; }
    refresh();
    const t = setInterval(refresh, 60 * 1000);
    return () => clearInterval(t);
  });

  const SECT = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'];
  const NOISE_BANDS = [['160m', 'rgb(214, 80, 80)'], ['80m', 'rgb(224, 160, 48)'], ['40m', 'rgb(140, 185, 230)']];

  // résumé : direct sur la page du jour, sinon cumul de la journée archivée
  const summary = $derived.by(() => {
    if (live?.ok) return { sectors: SECT.map((s) => live.sectors[s] ?? 0), n500: live.n500, n2000: live.n2000,
                           world: live.world, nearest: live.nearest, label: `${live.window_min} dernières min` };
    if (!buckets.length) return null;
    const sectors = [0, 0, 0, 0, 0, 0, 0, 0];
    let n500 = 0, n2000 = 0, world = 0, near = null;
    for (const b of buckets) {
      n500 += b.n500; n2000 += b.n2000; world += b.total;
      b.sectors.forEach((v, i) => (sectors[i] += v));
      if (b.near_km != null && (!near || b.near_km < near.km)) near = { km: b.near_km, az: b.near_az };
    }
    if (near) near.dir = SECT[Math.round(near.az / 45) % 8];
    return { sectors, n500, n2000, world, nearest: near, label: 'sur la journée', day: true };
  });

  const level = (km) => (km == null ? '' : km <= 500 ? 'bad' : km <= 2000 ? 'warn' : 'ok');

  // rose des 8 secteurs (impacts à moins de 2000 km)
  const R = 34;
  const wedges = $derived.by(() => {
    if (!summary) return [];
    const max = Math.max(1, ...summary.sectors);
    return summary.sectors.map((v, i) => {
      const r = v ? 6 + (R - 6) * Math.sqrt(v / max) : 0;
      const a1 = ((i * 45 - 22.5 - 90) * Math.PI) / 180, a2 = ((i * 45 + 22.5 - 90) * Math.PI) / 180;
      return { v, d: r ? `M0,0 L${(r * Math.cos(a1)).toFixed(1)},${(r * Math.sin(a1)).toFixed(1)} A${r.toFixed(1)},${r.toFixed(1)} 0 0 1 ${(r * Math.cos(a2)).toFixed(1)},${(r * Math.sin(a2)).toFixed(1)} Z` : '' };
    });
  });

  // courbes 24 h : impacts < 2000 km (barres, échelle à gauche) et bruit de fond 160/80/40 m (lignes, échelle à droite)
  const W = 260, H = 100, PADL = 22, PADR = 22, PADB = 14, PADT = 13;
  const PW = W - PADL - PADR;
  const xH = (h) => PADL + (h / 24) * PW;
  const xOf = (t) => xH(+t.slice(0, 2) + +t.slice(2, 4) / 60);
  // valeur « ronde » (1, 2, 5 × 10ⁿ) juste au-dessus de v
  const niceUp = (v) => { const p = 10 ** Math.floor(Math.log10(v)); return [1, 2, 5, 10].find((m) => m * p >= v) * p; };
  const niceStep = (span) => [0.5, 1, 2, 5, 10, 20, 50].find((st) => span / st <= 4) ?? 100;
  const fmtN = (v) => (v >= 10000 ? `${Math.round(v / 1000)}k` : v >= 1000 ? `${+(v / 1000).toFixed(1)}k` : `${+v.toFixed(1)}`);
  const bars = $derived.by(() => {
    const top = niceUp(Math.max(1, ...buckets.map((b) => b.n2000)));
    const hOf = (v) => Math.sqrt(v / top) * (H - PADB - PADT);   // racine carrée : les petits nombres restent visibles
    const bw = (PW / 288) * 0.9;
    return {
      // graduations à 0, ¼ et le haut de l'échelle (mi-hauteur et hauteur pleine en racine carrée)
      ticks: [0, top / 4, top].map((v) => ({ v: fmtN(v), y: H - PADB - hOf(v) })),
      list: buckets.filter((b) => b.n2000).map((b) => {
        const h = Math.max(1, hOf(b.n2000));
        return { x: xOf(b.time), y: H - PADB - h, h, w: Math.max(0.8, bw), near: b.n500 > 0 };
      }),
    };
  });
  const noiseChart = $derived.by(() => {
    const pts = noise.filter((n) => NOISE_BANDS.some(([b]) => b === n.band));
    if (pts.length < 2) return { lines: [], ticks: [] };
    let lo = Math.min(...pts.map((p) => p.floor_db)), hi = Math.max(...pts.map((p) => p.floor_db));
    if (hi - lo < 3) { lo -= 1.5; hi += 1.5; }
    const step = niceStep(hi - lo);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const y = (v) => H - PADB - ((v - lo) / (hi - lo)) * (H - PADB - PADT);
    const ticks = [];
    for (let v = lo; v <= hi + step / 1000; v += step) ticks.push({ v: step < 1 ? v.toFixed(1) : Math.round(v), y: y(v) });
    const lines = NOISE_BANDS.map(([band, color]) => {
      const p = pts.filter((n) => n.band === band);
      return { band, color, d: p.length > 1 ? p.map((n, i) => `${i ? 'L' : 'M'}${xOf(n.time).toFixed(1)},${y(n.floor_db).toFixed(1)}`).join(' ') : '' };
    }).filter((l) => l.d);
    return { lines, ticks };
  });
  const lines = $derived(noiseChart.lines);

  const excess = $derived(live?.noise?.bands
    ? ['160m', '80m', '40m', '20m', '10m'].filter((b) => live.noise.bands[b]).map((b) => [b, live.noise.bands[b]])
    : []);
  const exClass = (e) => (e == null ? '' : e >= 6 ? 'bad' : e >= 3 ? 'warn' : e <= -6 ? 'cold' : '');
  let big = $state(false);   // vue agrandie au centre de la page
</script>

{#if big}<div class="zoom-backdrop" onclick={() => (big = false)} role="presentation"></div>{/if}
<section class="panel storms zoomable" class:big>
  <button class="ghost zoom-btn" onclick={() => (big = !big)} title={big ? 'Fermer' : 'Agrandir'}>{big ? '✕' : '⤢'}</button>
  <h2 class="panel-title title-row">Orages et QRN
    <!-- carte Blitzortung des impacts en direct, centrée sur la France, dans un nouvel onglet -->
    <a class="btn blitz" href="https://map.blitzortung.org/#4.58/46.54/3.23" target="_blank" rel="noopener" title="Ouvrir la carte Blitzortung">Blitz</a>
  </h2>

  {#if summary}
    <div class="head">
      <svg viewBox="-40 -40 80 80" class="rose" role="img" aria-label="Impacts de foudre par direction">
        <circle r={R} class="ring" /><circle r={R / 2} class="ring" />
        {#each wedges as w}{#if w.d}<path d={w.d} class="wedge" />{/if}{/each}
        <text y={-R - 1} class="cardinal" text-anchor="middle">N</text>
        <circle r="2" class="me" />
      </svg>
      <div class="facts">
        {#if summary.nearest}
          <div class="near {level(summary.nearest.km)}">
            Orage {summary.day ? 'au plus près' : ''} à <b>{summary.nearest.km} km</b> au {summary.nearest.dir}
          </div>
        {:else}
          <div class="near ok">Aucun orage à moins de 3000 km</div>
        {/if}
        <div class="row"><span>&lt; 500 km</span><b>{summary.n500}</b></div>
        <div class="row"><span>&lt; 2000 km</span><b>{summary.n2000}</b></div>
        <div class="row"><span>Monde</span><b>{summary.world}</b></div>
        <div class="when">impacts, {summary.label}</div>
      </div>
    </div>
  {:else}
    <p class="muted">
      {#if isToday}
        {#if live && live.status?.enabled === false}Écoute de la foudre désactivée (panneau admin).
        {:else if live?.status?.error}Blitzortung : {live.status.error}
        {:else if error}{error}{:else}Écoute du réseau Blitzortung…{/if}
      {:else}Aucun relevé de foudre ce jour-là.{/if}
    </p>
  {/if}

  {#if excess.length}
    <div class="excess" title="Bruit de fond mesuré par ORSAT, comparé à sa valeur habituelle à cette heure (30 jours)">
      {#each excess as [b, v]}
        <span class="chip {exClass(v.excess)}">{b}
          <b>{v.excess == null ? `${v.floor} dB` : `${v.excess > 0 ? '+' : ''}${v.excess} dB`}</b></span>
      {/each}
    </div>
  {/if}

  {#if bars.list.length || lines.length}
    <svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Foudre et bruit de fond sur la journée">
      {#if bars.list.length}
        {#each bars.ticks as t}
          <line x1={PADL} x2={W - PADR} y1={t.y} y2={t.y} class="hgrid" />
          <text x={PADL - 3} y={t.y + 2.5} class="axis al" text-anchor="end">{t.v}</text>
        {/each}
        <text x={PADL - 3} y="6" class="axis al unit" text-anchor="end">imp.</text>
      {/if}
      {#if lines.length}
        {#each noiseChart.ticks as t}
          <text x={W - PADR + 3} y={t.y + 2.5} class="axis ar" text-anchor="start">{t.v}</text>
        {/each}
        <text x={W - PADR + 3} y="6" class="axis ar unit" text-anchor="start">dB</text>
      {/if}
      {#each [0, 6, 12, 18, 24] as h}
        <line x1={xH(h)} x2={xH(h)} y1={PADT} y2={H - PADB} class="grid" />
        <text x={xH(h)} y={H - 3} class="axis" text-anchor="middle">{h}h</text>
      {/each}
      {#each bars.list as b}<rect x={b.x} y={b.y} width={b.w} height={b.h} class:near={b.near} class="bar" />{/each}
      {#each lines as l}<path d={l.d} style="stroke: {l.color}" class="line" />{/each}
    </svg>
    <div class="legend">
      <span><i class="lb"></i>foudre &lt; 2000 km (impacts / 5 min)</span><span><i class="ln"></i>&lt; 500 km</span>
      {#each lines as l}<span><i style="background: {l.color}"></i>bruit {l.band}</span>{/each}
    </div>
  {/if}

  <div class="foot muted">Données foudre : Blitzortung.org{#if live?.noise} · bruit mesuré à {live.noise.at.slice(11, 16)} UTC{/if}</div>
</section>

<style>
  .storms { display: flex; flex-direction: column; gap: 6px; }
  .title-row { display: flex; align-items: center; gap: 10px; }
  .blitz { padding: 1px 8px; font-size: 0.68rem; letter-spacing: 0.12em; }
  .head { display: flex; align-items: center; gap: 12px; }
  .rose { width: 84px; height: 84px; flex: none; }
  .ring { fill: none; stroke: rgba(207, 181, 59, 0.2); }
  .wedge { fill: rgba(207, 181, 59, 0.55); stroke: var(--gold); stroke-width: 0.6; }
  .me { fill: var(--gold); }
  .cardinal { fill: var(--muted); font-size: 7px; }
  .facts { flex: 1; font-size: 0.82rem; }
  .near { margin-bottom: 4px; }
  .near.bad b { color: var(--bad); } .near.warn b { color: var(--warn); } .near.ok { color: var(--ok); }
  .row { display: flex; justify-content: space-between; gap: 8px; }
  span { color: var(--muted); }
  b { font-weight: 500; }
  .when { font-size: 0.7rem; color: var(--muted); }
  .excess { display: flex; flex-wrap: wrap; gap: 5px; }
  .chip { border: 1px solid var(--panel-edge); border-radius: 12px; padding: 1px 8px; font-size: 0.78rem; }
  .chip b { color: var(--text); }
  .chip.warn b { color: var(--warn); } .chip.bad b { color: var(--bad); } .chip.cold b { color: rgb(140, 185, 230); }
  .chart { width: 100%; height: auto; margin-top: 2px; }
  .grid { stroke: rgba(207, 181, 59, 0.12); }
  .axis { fill: var(--muted); font-size: 9px; }
  .hgrid { stroke: rgba(207, 181, 59, 0.07); }
  .al { fill: var(--gold); font-size: 6.5px; } .ar { fill: var(--text); font-size: 6.5px; opacity: 0.75; }
  .unit { font-size: 6px; opacity: 0.8; }
  .bar { fill: rgba(207, 181, 59, 0.45); } .bar.near { fill: var(--bad); }
  /* trait fin, de même épaisseur à l'écran en vue normale comme agrandie */
  .line { fill: none; stroke-width: 1.1px; vector-effect: non-scaling-stroke; stroke-linejoin: round; }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 0.7rem; }
  .legend i { display: inline-block; width: 10px; height: 3px; margin-right: 4px; vertical-align: 2px; }
  .lb { background: rgba(207, 181, 59, 0.6); } .ln { background: var(--bad); }
  .foot { font-size: 0.7rem; }
  .muted { color: var(--muted); font-size: 0.82rem; margin: 0; }
  /* vue agrandie */
  .big .head { gap: 28px; }
  .big .rose { width: 190px; height: 190px; }
  .big .facts { font-size: 1.1rem; } .big .when { font-size: 0.9rem; }
  .big .chip { font-size: 1rem; padding: 2px 12px; }
  .big .legend { font-size: 0.95rem; } .big .legend i { width: 16px; }
  .big .foot, .big .muted { font-size: 0.9rem; }
  .big .chart { max-height: 52vh; }
</style>
