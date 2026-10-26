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

  // courbes 24 h : impacts < 2000 km (barres) et bruit de fond 160/80/40 m (lignes)
  const W = 260, H = 100, PADL = 4, PADB = 14;
  const xOf = (t) => PADL + ((+t.slice(0, 2) + +t.slice(2, 4) / 60) / 24) * (W - PADL - 4);
  const bars = $derived.by(() => {
    const max = Math.max(1, ...buckets.map((b) => b.n2000));
    const bw = ((W - PADL - 4) / 288) * 0.9;
    return buckets.filter((b) => b.n2000).map((b) => {
      const h = Math.max(1, (Math.sqrt(b.n2000 / max)) * (H - PADB - 8));
      return { x: xOf(b.time), y: H - PADB - h, h, w: Math.max(0.8, bw), near: b.n500 > 0 };
    });
  });
  const lines = $derived.by(() => {
    const pts = noise.filter((n) => NOISE_BANDS.some(([b]) => b === n.band));
    if (pts.length < 2) return [];
    let lo = Math.min(...pts.map((p) => p.floor_db)), hi = Math.max(...pts.map((p) => p.floor_db));
    if (hi - lo < 3) { lo -= 1.5; hi += 1.5; }
    const y = (v) => H - PADB - ((v - lo) / (hi - lo)) * (H - PADB - 8);
    return NOISE_BANDS.map(([band, color]) => {
      const p = pts.filter((n) => n.band === band);
      return { band, color, d: p.length > 1 ? p.map((n, i) => `${i ? 'L' : 'M'}${xOf(n.time).toFixed(1)},${y(n.floor_db).toFixed(1)}`).join(' ') : '' };
    }).filter((l) => l.d);
  });

  const excess = $derived(live?.noise?.bands
    ? ['160m', '80m', '40m', '20m', '10m'].filter((b) => live.noise.bands[b]).map((b) => [b, live.noise.bands[b]])
    : []);
  const exClass = (e) => (e == null ? '' : e >= 6 ? 'bad' : e >= 3 ? 'warn' : e <= -6 ? 'cold' : '');
</script>

<section class="panel storms">
  <h2 class="panel-title">Orages et QRN</h2>

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

  {#if bars.length || lines.length}
    <svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Foudre et bruit de fond sur la journée">
      {#each [0, 6, 12, 18, 24] as h}
        <line x1={PADL + (h / 24) * (W - PADL - 4)} x2={PADL + (h / 24) * (W - PADL - 4)} y1="4" y2={H - PADB} class="grid" />
        <text x={PADL + (h / 24) * (W - PADL - 4)} y={H - 3} class="axis"
              text-anchor={h === 0 ? 'start' : h === 24 ? 'end' : 'middle'}>{h}h</text>
      {/each}
      {#each bars as b}<rect x={b.x} y={b.y} width={b.w} height={b.h} class:near={b.near} class="bar" />{/each}
      {#each lines as l}<path d={l.d} style="stroke: {l.color}" class="line" />{/each}
    </svg>
    <div class="legend">
      <span><i class="lb"></i>foudre &lt; 2000 km</span><span><i class="ln"></i>&lt; 500 km</span>
      {#each lines as l}<span><i style="background: {l.color}"></i>bruit {l.band}</span>{/each}
    </div>
  {/if}

  <div class="foot muted">Données foudre : Blitzortung.org{#if live?.noise} · bruit mesuré à {live.noise.at.slice(11, 16)} UTC{/if}</div>
</section>

<style>
  .storms { display: flex; flex-direction: column; gap: 6px; }
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
  .bar { fill: rgba(207, 181, 59, 0.45); } .bar.near { fill: var(--bad); }
  .line { fill: none; stroke-width: 1.4; }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 0.7rem; }
  .legend i { display: inline-block; width: 10px; height: 3px; margin-right: 4px; vertical-align: 2px; }
  .lb { background: rgba(207, 181, 59, 0.6); } .ln { background: var(--bad); }
  .foot { font-size: 0.7rem; }
  .muted { color: var(--muted); font-size: 0.82rem; margin: 0; }
</style>
