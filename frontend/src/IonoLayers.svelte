<script>
  // Altitude des couches ionosphériques sur la journée (ionosonde GIRO la plus proche, layers.py)
  import { api } from './api.js';
  import { fmtTime } from './util.js';

  let { day, isToday = false } = $props();

  let data = $state(null);
  async function load(d) {
    const r = await api.layers(d).catch((e) => ({ ok: false, msg: e.message }));
    if (d === day) data = r;
  }
  $effect(() => {
    const d = day;
    data = null;
    load(d);
    if (!isToday) return;
    const t = setInterval(() => load(d), 15 * 60 * 1000);
    return () => clearInterval(t);
  });

  const pts = $derived(data?.ok ? data.points : []);
  const last = $derived(pts.length ? pts[pts.length - 1] : null);

  // géométrie en pixels réels (1 unité = 1 px) : traits et textes gardent leur finesse en vue agrandie
  let cw = $state(260);
  const W = $derived(Math.max(220, Math.round(cw)));
  const H = $derived(Math.round(Math.min(340, Math.max(150, W * 0.38))));
  const PADL = 30, PADR = 8, PADT = 8, PADB = 16, HMAX = 450;
  const E_DEF = 110, F1_DEF = 200;   // altitudes typiques quand l'ionosonde ne donne que la fréquence
  const min = (t) => +t.slice(0, 2) * 60 + +t.slice(2, 4);
  const xOf = (t) => PADL + (min(t) / 1440) * (W - PADL - PADR);
  const yOf = (km) => H - PADB - (km / HMAX) * (H - PADB - PADT);

  // lissage : médiane glissante sur ±20 min (un ionogramme isolé mal dépouillé ne fait plus de dent de scie)
  function smooth(get) {
    return pts.map((p) => {
      if (get(p) == null) return null;
      const t = min(p.time);
      const v = pts.filter((q) => Math.abs(min(q.time) - t) <= 20 && get(q) != null).map(get).sort((a, b) => a - b);
      return v[Math.floor(v.length / 2)];
    });
  }
  // courbe découpée aux trous de mesure (> 1 h) et aux valeurs absentes
  function line(get) {
    const sm = smooth(get);
    let d = '', prev = null;
    for (const [i, p] of pts.entries()) {
      const h = sm[i];
      if (h == null) { prev = null; continue; }
      const cont = prev && min(p.time) - min(prev.time) <= 60;
      d += `${cont ? 'L' : 'M'}${xOf(p.time).toFixed(1)},${yOf(h).toFixed(1)}`;
      prev = p;
    }
    return d;
  }
  const hE = (p) => (p.e[0] ? p.e[1] ?? E_DEF : null);
  const hF1 = (p) => (p.f1[0] ? p.f1[1] ?? F1_DEF : null);
  const f2Path = $derived(line((p) => p.f2[1]));
  const ePath = $derived(line(hE));

  // bandes verticales par mesure (couche D et zone de survol)
  const cols = $derived(pts.map((p, i) => {
    const x0 = i ? (xOf(pts[i - 1].time) + xOf(p.time)) / 2 : xOf(p.time) - 2;
    const x1 = i < pts.length - 1 ? (xOf(p.time) + xOf(pts[i + 1].time)) / 2 : xOf(p.time) + 2;
    return { p, x: x0, w: Math.max(0.5, x1 - x0) };
  }));

  const v = (a, unit) => (a == null ? '—' : `${a} ${unit}`);
  function tip(p) {
    return `${fmtTime(p.time)} UTC\n`
      + `F2 : ${v(p.f2[1], 'km')} · foF2 ${v(p.f2[0], 'MHz')}\n`
      + `F1 : ${p.f1[0] ? `${v(p.f1[1], 'km')} · foF1 ${p.f1[0]} MHz` : 'absente'}\n`
      + `E : ${p.e[0] ? `${v(p.e[1], 'km')} · foE ${p.e[0]} MHz` : 'absente'}\n`
      + `Es : ${p.es ? `foEs ${p.es} MHz` : 'aucun'}\n`
      + `D : ${p.d > 0 ? `présente (Soleil ${Math.round(90 - Math.acos(p.d) * 180 / Math.PI)}° au-dessus de l'horizon)` : 'absente (nuit)'}`;
  }
  const TIP = 'Altitude des couches ionosphériques mesurée par l\'ionosonde (GIRO).\n'
    + 'F2 : couche qui fait le DX, plus haute la nuit. F1 : de jour seulement. E : vers 110 km, de jour.\n'
    + 'Es : E sporadique (nuages très ionisés à l\'altitude de la E). D : 60-90 km, de jour seulement ;\n'
    + 'elle ne réfléchit pas, elle absorbe (surtout les bandes basses) : son altitude n\'est pas mesurable.\n'
    + 'Les altitudes E et F1 non mesurées sont prises à leur valeur typique.';
</script>

<div class="iono" title={TIP}>
  <span class="lbl">Altitude des couches ionosphériques</span>
  {#if pts.length}
    <div class="wrap" bind:clientWidth={cw}>
    <svg width={W} height={H} viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Altitude des couches ionosphériques sur la journée">
      {#each [100, 200, 300, 400] as km}
        <line x1={PADL} x2={W - PADR} y1={yOf(km)} y2={yOf(km)} class="grid" />
        <text x={PADL - 3} y={yOf(km) + 3} class="axis" text-anchor="end">{km}</text>
      {/each}
      <text x={PADL - 3} y={PADT + 2} class="axis" text-anchor="end">km</text>
      {#each [0, 6, 12, 18, 24] as h}
        <text x={PADL + (h / 24) * (W - PADL - PADR)} y={H - 3} class="axis"
              text-anchor={h === 0 ? 'start' : h === 24 ? 'end' : 'middle'}>{h}h</text>
      {/each}
      <!-- couche D : 60-90 km, intensité selon la hauteur du Soleil -->
      {#each cols as c}{#if c.p.d > 0}
        <rect x={c.x} y={yOf(90)} width={c.w} height={yOf(60) - yOf(90)} class="dl" style="opacity: {0.15 + 0.7 * c.p.d}" />
      {/if}{/each}
      {#if ePath}<path d={ePath} class="e" />{/if}
      {#each pts as p}
        {#if p.es}<rect x={xOf(p.time) - 1} y={yOf((hE(p) ?? E_DEF) + 6)} width="2" height="4" class="es" style="opacity: {Math.min(1, 0.3 + p.es / 8)}" />{/if}
        {#if hF1(p)}<circle cx={xOf(p.time)} cy={yOf(hF1(p))} r="1.2" class="f1" />{/if}
      {/each}
      {#if f2Path}<path d={f2Path} class="f2" />{/if}
      <!-- survol : toutes les valeurs de la mesure -->
      {#each cols as c}<rect x={c.x} y={PADT} width={c.w} height={H - PADB - PADT} fill="transparent"><title>{tip(c.p)}</title></rect>{/each}
    </svg>
    </div>
    <div class="legend">
      <span><i class="lf2"></i>F2 {v(last.f2[1], 'km')} · {v(last.f2[0], 'MHz')}</span>
      <span><i class="lf1"></i>F1 {last.f1[0] ? `${last.f1[1] ?? '~' + F1_DEF} km · ${last.f1[0]} MHz` : 'absente'}</span>
      <span><i class="le"></i>E {last.e[0] ? `${last.e[1] ?? '~' + E_DEF} km · ${last.e[0]} MHz` : 'absente'}</span>
      <span><i class="les"></i>Es {last.es ? `${last.es} MHz` : 'aucun'}</span>
      <span><i class="ld"></i>D {last.d > 0 ? 'présente' : 'absente (nuit)'}</span>
    </div>
    <span class="src">Ionosonde {data.station} (GIRO) · mesure {fmtTime(last.time)} UTC</span>
  {:else}
    <span class="muted">{data ? (data.msg || 'Pas de mesure.') : 'Lecture de l\'ionosonde…'}</span>
  {/if}
</div>

<style>
  .iono { display: flex; flex-direction: column; gap: 3px; cursor: help; }
  .lbl { color: var(--muted); font-size: 0.72rem; }
  .wrap { width: 100%; }
  .chart { display: block; }
  .grid { stroke: rgba(207, 181, 59, 0.12); }
  .axis { fill: var(--muted); font-size: 10px; }
  .dl { fill: rgb(170, 90, 60); }
  .e { fill: none; stroke: rgb(140, 185, 230); stroke-width: 1.2; stroke-linejoin: round; }
  .f2 { fill: none; stroke: var(--gold); stroke-width: 1.5; stroke-linejoin: round; }
  .f1 { fill: rgb(230, 215, 150); }
  .es { fill: rgb(224, 90, 200); }
  .legend { display: flex; flex-wrap: wrap; gap: 2px 10px; font-size: 0.7rem; color: var(--text); }
  .legend i { display: inline-block; width: 10px; height: 3px; margin-right: 4px; vertical-align: 2px; border-radius: 1px; }
  .lf2 { background: var(--gold); } .lf1 { background: rgb(230, 215, 150); } .le { background: rgb(140, 185, 230); }
  .les { background: rgb(224, 90, 200); } .ld { background: rgb(170, 90, 60); }
  .src { font-size: 0.68rem; color: var(--muted); }
  .muted { color: var(--muted); font-size: 0.78rem; }
  /* vue agrandie de la fenêtre Météo spatiale */
  :global(.big) .iono .lbl { font-size: 0.95rem; }
  :global(.big) .iono .legend { font-size: 0.95rem; gap: 4px 16px; }
  :global(.big) .iono .legend i { width: 16px; }
  :global(.big) .iono .src, :global(.big) .iono .muted { font-size: 0.9rem; }
  :global(.big) .iono .axis { font-size: 12px; }
</style>
