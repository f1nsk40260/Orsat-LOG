<script>
  import { kClass, fmtTime } from './util.js';
  import { tipSfi, tipA, tipK, tipSn, tipXray, tipGeomag, TIP_BANDS } from './proptips.js';

  let { snapshots = [], archive = null, isToday = false } = $props();
  const SLOTS = ['00', '03', '06', '09', '12', '15', '18', '21'];
  const kpMax = $derived.by(() => {
    const v = (archive?.kp || []).filter((k) => k != null);
    return v.length ? Math.max(...v) : null;
  });

  const latest = $derived(snapshots.length ? snapshots[snapshots.length - 1] : null);

  // frise 24 h : position x selon l'heure UTC du relevé
  const W = 290, H = 120, PADL = 18, PADB = 16;
  const xOf = (time) => {
    const h = +time.slice(0, 2) + +time.slice(2, 4) / 60;
    return PADL + (h / 24) * (W - PADL - 6);
  };
  const yK = (k) => H - PADB - (k / 9) * (H - PADB - 8);
  const sfiRange = $derived.by(() => {
    const v = snapshots.map((s) => s.sfi).filter((x) => x != null);
    if (!v.length) return [60, 200];
    const lo = Math.min(...v), hi = Math.max(...v);
    return hi - lo < 10 ? [lo - 5, hi + 5] : [lo, hi];
  });
  const ySfi = (v) => H - PADB - ((v - sfiRange[0]) / (sfiRange[1] - sfiRange[0])) * (H - PADB - 8);
  const sfiPath = $derived(
    snapshots.filter((s) => s.sfi != null)
      .map((s, i) => `${i ? 'L' : 'M'}${xOf(s.time).toFixed(1)},${ySfi(s.sfi).toFixed(1)}`).join(' ')
  );
  const kColor = (k) => (k >= 5 ? 'var(--bad)' : k >= 4 ? 'var(--warn)' : 'var(--ok)');

  // état des bandes (dernier relevé) : { "80m-40m": { day: "Good", night: "Fair" } }
  const bands = $derived.by(() => {
    const out = {};
    for (const c of latest?.conditions ?? []) {
      out[c.band] ??= {};
      out[c.band][c.time] = c.state;
    }
    return out;
  });
  const condFr = { Good: 'Bonne', Fair: 'Moyenne', Poor: 'Mauvaise' };
  const condClass = { Good: 'ok', Fair: 'warn', Poor: 'bad' };
</script>

<section class="panel prop">
  <h2 class="panel-title">Propagation du jour</h2>

  {#if latest}
    <div class="indices">
      <div title={tipSfi(latest.sfi)}><span>SFI</span><b>{latest.sfi ?? '—'}</b></div>
      <div title={tipA(latest.a_index)}><span>A</span><b>{latest.a_index ?? '—'}</b></div>
      <div title={tipK(latest.k_index)}><span>K</span><b class={kClass(latest.k_index)}>{latest.k_index ?? '—'}</b></div>
      <div title={tipSn(latest.sunspots)}><span>Taches</span><b>{latest.sunspots ?? '—'}</b></div>
      <div title={tipXray(latest.xray)}><span>X-ray</span><b>{latest.xray || '—'}</b></div>
    </div>
    {#if latest.geomagfield}
      <div class="geomag" title={tipGeomag(latest.geomagfield)}>Champ géomagnétique : {latest.geomagfield}</div>
    {/if}

    <svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Indice K et flux solaire sur la journée">
      {#each [0, 6, 12, 18, 24] as h}
        <line x1={PADL + (h / 24) * (W - PADL - 6)} x2={PADL + (h / 24) * (W - PADL - 6)}
              y1="6" y2={H - PADB} class="grid" />
        <text x={PADL + (h / 24) * (W - PADL - 6)} y={H - 4} class="axis" text-anchor={h === 0 ? 'start' : h === 24 ? 'end' : 'middle'}>{h}h</text>
      {/each}
      {#each [0, 3, 6, 9] as k}
        <text x={PADL - 6} y={yK(k) + 3} class="axis" text-anchor="end">{k}</text>
      {/each}
      {#each snapshots as s}
        {#if s.k_index != null}
          <rect x={xOf(s.time) - 3.5} width="7" y={yK(s.k_index)} height={H - PADB - yK(s.k_index)}
                fill={kColor(s.k_index)} opacity="0.75">
            <title>{fmtTime(s.time)} UTC — K {s.k_index}, SFI {s.sfi}</title>
          </rect>
        {/if}
      {/each}
      {#if sfiPath}<path d={sfiPath} class="sfi" />{/if}
    </svg>
    <div class="legend">
      <span><i class="lk"></i>indice K (0–9)</span>
      <span><i class="ls"></i>flux solaire</span>
      <span class="muted">{snapshots.length} relevé{snapshots.length > 1 ? 's' : ''} · dernier à {fmtTime(latest.time)} UTC</span>
    </div>

    {#if Object.keys(bands).length}
      <table class="bands" title={TIP_BANDS}>
        <thead><tr><th>Bandes</th><th>Jour</th><th>Nuit</th></tr></thead>
        <tbody>
          {#each Object.entries(bands) as [band, c]}
            <tr>
              <td>{band}</td>
              <td class={condClass[c.day]}>{condFr[c.day] ?? c.day ?? '—'}</td>
              <td class={condClass[c.night]}>{condFr[c.night] ?? c.night ?? '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {:else if !archive}
    <p class="muted">
      {isToday ? 'Premier relevé en cours… (hamqsl.com, toutes les 15 min)' : 'Aucun relevé de propagation ce jour-là.'}
    </p>
  {/if}

  {#if archive?.kp}
    <!-- Indices officiels du jour : seuls disponibles avant la mise en service du carnet -->
    {#if !latest}
      <div class="indices four">
        <div title={tipSfi(archive.sfi)}><span>SFI</span><b>{archive.sfi != null ? Math.round(archive.sfi) : '—'}</b></div>
        <div title={tipA(archive.ap)}><span>A</span><b>{archive.ap ?? '—'}</b></div>
        <div title={tipK(kpMax)}><span>Kp max</span><b class={kClass(kpMax)}>{kpMax != null ? +kpMax.toFixed(1) : '—'}</b></div>
        <div title={tipSn(archive.sn)}><span>Taches</span><b>{archive.sn ?? '—'}</b></div>
      </div>
    {/if}
    <div class="lbl" title={tipK(null)}>Kp officiels du jour (créneaux de 3 h UTC)</div>
    <svg viewBox="0 0 290 70" class="chart" role="img" aria-label="Kp officiels du jour">
      {#each archive.kp as k, i}
        {@const h = k == null ? 0 : Math.max(2, (k / 9) * 48)}
        <rect x={10 + i * 35} y={54 - h} width="27" height={h} rx="2" fill={k == null ? 'none' : kColor(k)} opacity="0.8">
          <title>{SLOTS[i]}–{String((i + 1) * 3).padStart(2, '0')} h UTC{'\n'}{tipK(k)}</title>
        </rect>
        <text x={23.5 + i * 35} y="66" class="axis" text-anchor="middle">{SLOTS[i]}</text>
        {#if k != null}<text x={23.5 + i * 35} y={50 - h} class="axis v" text-anchor="middle">{+k.toFixed(1)}</text>{/if}
      {/each}
    </svg>
    <p class="src">Archive GFZ Potsdam (CC BY 4.0){latest ? ' — valeurs définitives, à comparer aux relevés en direct ci-dessus' : ' — pas de relevé en direct ce jour-là'}.</p>
  {/if}
</section>

<style>
  .prop { display: flex; flex-direction: column; gap: 8px; }
  .indices { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
  .indices div { cursor: help; text-align: center; background: rgba(0, 0, 0, 0.3); border-radius: 6px; padding: 6px 2px; }
  .indices span { display: block; font-size: 0.68rem; color: var(--gold-soft); letter-spacing: 0.08em; text-transform: uppercase; }
  .indices b { font-size: 1.25rem; color: var(--text); }
  .indices.four { grid-template-columns: repeat(4, 1fr); }
  .lbl { font-size: 0.72rem; color: var(--muted); margin-top: 4px; }
  .axis.v { fill: var(--text); }
  .src { font-size: 0.7rem; color: var(--muted); margin: 0; }
  .geomag { font-size: 0.8rem; color: var(--muted); }
  .chart { width: 100%; height: auto; }
  .grid { stroke: rgba(207, 181, 59, 0.12); }
  .axis { fill: var(--muted); font-size: 10px; }
  .sfi { fill: none; stroke: var(--gold); stroke-width: 2; }
  .legend { display: flex; gap: 14px; font-size: 0.74rem; color: var(--text); flex-wrap: wrap; }
  .legend i { display: inline-block; width: 10px; height: 10px; margin-right: 4px; vertical-align: -1px; }
  .lk { background: var(--ok); } .ls { background: var(--gold); height: 3px !important; vertical-align: 2px !important; }
  .bands { font-size: 0.82rem; }
  .bands td, .bands th { padding: 3px 6px; }
  .ok { color: var(--ok); } .warn { color: var(--warn); } .bad { color: var(--bad); }
  .muted { color: var(--muted); }
</style>
