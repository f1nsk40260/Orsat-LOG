<script>
  // Carte azimutale équidistante centrée sur le QTH : zones de silence et ouvertures, bande par bande,
  // avec les correspondants du jour (QSO, tour de table) placés dessus.
  import { geoAzimuthalEquidistant, geoPath, geoGraticule10 } from 'd3-geo';
  import { feature, mesh } from 'topojson-client';
  import world from 'world-atlas/countries-110m.json';
  import { api } from './api.js';

  let data = $state(null);
  let band = $state('20m');
  let onlyBand = $state(false);
  let hover = $state('');

  export async function refresh() { data = await api.skipMap().catch(() => ({ ok: false, msg: 'Serveur injoignable.' })); }
  $effect(() => { refresh(); });

  const SIZE = 640, C = SIZE / 2, R = 300, EARTH = 6371, KM_MIN = 150, KM_MAX = 5000;
  // zoom à la molette (centré sur le QTH) : rayon affiché en km
  let MAX_KM = $state(KM_MAX);
  const scale = $derived(R / (MAX_KM / EARTH));
  function onWheel(e) {
    e.preventDefault();
    MAX_KM = Math.round(Math.min(KM_MAX, Math.max(KM_MIN, MAX_KM * (e.deltaY > 0 ? 1.25 : 0.8))));
  }
  const ZOOMS = [[250, '250 km'], [600, '600 km'], [1200, '1200 km'], [2500, '2500 km'], [5000, '5000 km']];
  // anneaux repères : environ 5 cercles, pas « rond »
  const ringStep = $derived([25, 50, 100, 200, 250, 500, 1000].find((s) => MAX_KM / s <= 6) ?? 1000);
  const ringKms = $derived(Array.from({ length: Math.floor(MAX_KM / ringStep) }, (_, i) => (i + 1) * ringStep));
  // fonds de carte détaillés chargés à la demande : 1:50 M sous 1500 km, 1:10 M sous 600 km
  const topo = (w) => ({ land: feature(w, w.objects.land ?? w.objects.countries), borders: mesh(w, w.objects.countries, (a, b) => a !== b) });
  let fine = $state(null), finest = $state(null);
  $effect(() => {
    if (MAX_KM < 1500 && !fine) import('world-atlas/countries-50m.json').then((m) => (fine = topo(m.default)));
    if (MAX_KM < 600 && !finest) import('world-atlas/countries-10m.json').then((m) => (finest = topo(m.default)));
  });
  const detail = $derived(MAX_KM < 600 && finest ? finest : MAX_KM < 1500 && fine ? fine : null);
  const landShown = $derived(detail ? detail.land : land);
  const bordersShown = $derived(detail ? detail.borders : borders);

  // villes (Natural Earth, domaine public) : seuil de population selon le zoom, étiquettes sans chevauchement
  let cityList = $state(null);
  $effect(() => {
    if (MAX_KM <= 2500 && !cityList) import('./data/cities.json').then((m) => (cityList = m.default));
  });
  const popMin = $derived(MAX_KM > 2500 ? 3e6 : MAX_KM > 1200 ? 8e5 : MAX_KM > 600 ? 2e5 : MAX_KM > 300 ? 5e4 : 1.5e4);
  const cities = $derived.by(() => {
    if (!proj || !data?.ok) return [];
    const src = cityList ?? [];
    // les indicatifs des correspondants sont prioritaires : pas de nom de ville par-dessus
    const placed = stations.map((st) => [st.p[0] + 7 + st.call.length * 3.5, st.p[1], st.call.length * 7 + 14]), out = [];
    for (const [name, lat, lon, pop] of src) {
      if (pop < popMin) break;                         // liste triée par population décroissante
      if (bearingKm(data.home, [lat, lon])[1] > MAX_KM * 0.98) continue;
      const p = proj([lon, lat]);
      if (!p) continue;
      const w = name.length * 6.2 + 8;
      if (placed.some((q) => Math.abs(q[0] - p[0]) < (q[2] + w) / 2 && Math.abs(q[1] - p[1]) < 13)) continue;
      placed.push([p[0] + w / 2, p[1], w]);
      out.push({ name, p, pop });
      if (out.length >= 70) break;
    }
    return out;
  });
  const land = feature(world, world.objects.land ?? world.objects.countries);
  const borders = mesh(world, world.objects.countries, (a, b) => a !== b);

  const proj = $derived(data?.ok
    ? geoAzimuthalEquidistant().rotate([-data.home[1], -data.home[0]]).scale(scale).translate([C, C])
        .clipAngle((MAX_KM / EARTH) * 180 / Math.PI)
    : null);
  const path = $derived(proj ? geoPath(proj) : null);

  const FILL = { o: 'rgba(95,191,107,0.55)', e: 'rgba(224,160,48,0.55)', w: 'rgba(95,191,107,0.28)',
                 a: 'rgba(214,80,80,0.45)', c: 'rgba(10,10,12,0.72)', '-': 'url(#nodata)' };
  const LABEL = { o: 'ouverte', e: 'en limite de MUF', w: 'ouverte mais affaiblie (absorption)',
                  a: 'absorbée (couche D)', c: 'zone de silence (MUF dépassée)', '-': 'pas de mesure' };

  const xy = (az, km) => {
    const r = (km / MAX_KM) * R, a = (az * Math.PI) / 180;
    return [C + r * Math.sin(a), C - r * Math.cos(a)];
  };
  function sector(az0, az1, r0, r1) {
    const [x0, y0] = xy(az0, r1), [x1, y1] = xy(az1, r1), [x2, y2] = xy(az1, r0), [x3, y3] = xy(az0, r0);
    const R1 = (r1 / MAX_KM) * R, R0 = (r0 / MAX_KM) * R;
    return `M${x0},${y0} A${R1},${R1} 0 0 1 ${x1},${y1} L${x2},${y2} A${R0},${R0} 0 0 0 ${x3},${y3} Z`;
  }

  const cells = $derived.by(() => {
    if (!data?.ok || !data.bands[band]) return [];
    const codes = data.bands[band], n = data.rings.length, step = data.az_step, out = [];
    for (let i = 0; i < codes.length; i++) {
      const az = Math.floor(i / n) * step, k = i % n;
      const r0 = k ? data.rings[k - 1] : 0, r1 = data.rings[k];
      if (r0 >= MAX_KM) continue;
      out.push({ d: sector(az - step / 2, az + step / 2, r0, r1), code: codes[i], az, r0, r1, muf: data.muf[i] });
    }
    return out;
  });

  // correspondants du jour : position, azimut, distance, état de leur bande à leur place
  function bearingKm(a, b) {
    const t = (x) => (x * Math.PI) / 180;
    const [la1, lo1, la2, lo2] = [t(a[0]), t(a[1]), t(b[0]), t(b[1])];
    const d = 2 * Math.asin(Math.sqrt(Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2));
    const y = Math.sin(lo2 - lo1) * Math.cos(la2), x = Math.cos(la1) * Math.sin(la2) - Math.sin(la1) * Math.cos(la2) * Math.cos(lo2 - lo1);
    return [((Math.atan2(y, x) * 180) / Math.PI + 360) % 360, d * EARTH];
  }
  function codeAt(b, az, km) {
    const codes = data.bands[b];
    if (!codes) return '-';
    const n = data.rings.length, step = data.az_step;
    const ai = Math.round(az / step) % (360 / step), k = data.rings.findIndex((r) => km <= r);
    return k < 0 ? '-' : codes[ai * n + k];
  }
  const stations = $derived.by(() => {
    if (!data?.ok || !proj) return [];
    return (data.stations ?? [])
      .filter((s) => !onlyBand || s.band === band)
      .map((s) => {
        const [az, km] = bearingKm(data.home, [s.lat, s.lon]);
        const p = km <= MAX_KM ? proj([s.lon, s.lat]) : null;
        return { ...s, az: Math.round(az), km: Math.round(km), p, code: codeAt(s.band, az, km) };
      })
      .filter((s) => s.p);
  });
  const bandList = $derived(data?.ok ? Object.keys(data.bands) : []);
  const sessions = $derived([...new Set((data?.stations ?? []).map((s) => s.session).filter(Boolean))]);
</script>

<div class="sm">
  <div class="bar">
    <div class="bands" role="group" aria-label="Bande affichée">
      {#each bandList as b}<button type="button" class:on={band === b} onclick={() => (band = b)}>{b}</button>{/each}
    </div>
    <div class="bands zoom" role="group" aria-label="Rayon affiché" title="Rayon de la carte (molette sur la carte pour zoomer)">
      {#each ZOOMS as [km, l]}<button type="button" class:on={Math.abs(MAX_KM - km) < km * 0.1} onclick={() => (MAX_KM = km)}>{l}</button>{/each}
    </div>
    <button type="button" class="tog" class:on={onlyBand} onclick={() => (onlyBand = !onlyBand)}
            title="Afficher tous les correspondants du jour, ou seulement ceux de la bande choisie">
      {onlyBand ? `Correspondants : ${band} seulement` : 'Correspondants : toutes bandes'}</button>
  </div>

  {#if data?.ok}
    <div class="wrap">
      <svg viewBox="0 0 {SIZE} {SIZE}" class="map" onwheel={onWheel} role="img" aria-label="Carte azimutale des zones de silence sur {band}">
        <defs>
          <clipPath id="disc"><circle cx={C} cy={C} r={R} /></clipPath>
          <pattern id="nodata" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="3" height="6" fill="rgba(255,255,255,0.10)" /></pattern>
        </defs>
        <circle cx={C} cy={C} r={R} class="sea" />
        <g clip-path="url(#disc)">
          <path d={path(landShown)} class="land" />
          {#each cells as c}
            <path d={c.d} fill={FILL[c.code]} class="cell"
                  onmouseenter={() => (hover = `${band} · azimut ${c.az}° · ${c.r0}–${c.r1} km : ${LABEL[c.code]}${c.muf ? ` · MUF ${c.muf} MHz` : ''}`)}
                  onmouseleave={() => (hover = '')} />
          {/each}
          <path d={path(geoGraticule10())} class="grat" />
          <path d={path(bordersShown)} class="border" />
          <path d={path(landShown)} class="coast" />
        </g>
        {#each ringKms as km}
          <circle cx={C} cy={C} r={(km / MAX_KM) * R} class="ring" />
          <text x={C + 3} y={C - (km / MAX_KM) * R + 11} class="rlab">{km}</text>
        {/each}
        {#each [['N', 0], ['E', 90], ['S', 180], ['O', 270]] as [l, az]}
          {@const p = xy(az, MAX_KM * 1.045)}
          <text x={p[0]} y={p[1] + 4} class="card" text-anchor="middle">{l}</text>
        {/each}
        {#each cities as c}
          <circle cx={c.p[0]} cy={c.p[1]} r="2" class="city" />
          <text x={c.p[0] + 4} y={c.p[1] + 3.5} class="cname">{c.name}</text>
        {/each}
        <circle cx={C} cy={C} r="4" class="home" />
        {#each stations as s}
          <g class="st" onmouseenter={() => (hover = `${s.call} · ${s.band ?? '?'} · ${s.km} km, azimut ${s.az}°${s.session ? ` · ${s.session}` : ''} : ${LABEL[s.code]} sur sa bande`)}
             onmouseleave={() => (hover = '')}>
            <circle cx={s.p[0]} cy={s.p[1]} r="5" class="dot {s.code}" />
            <text x={s.p[0] + 7} y={s.p[1] + 4} class="call">{s.call}</text>
          </g>
        {/each}
      </svg>
      <div class="side">
        <p class="hover">{hover || 'Survolez la carte ou un correspondant.'}</p>
        <div class="legend">
          {#each ['o', 'e', 'w', 'a', 'c'] as k}<span><i style="background:{FILL[k]}"></i>{LABEL[k]}</span>{/each}
          <span><i class="hatch"></i>pas de mesure (pas d'ionosonde assez proche)</span>
        </div>
        {#if stations.length}
          <h4>Correspondants du jour{sessions.length ? ` · ${sessions.join(', ')}` : ''}</h4>
          <table class="list">
            <tbody>
              {#each stations.toSorted((a, b) => a.km - b.km) as s}
                <tr><td class="mono">{s.call}</td><td>{s.band ?? '—'}</td><td>{s.km} km</td><td>{s.az}°</td>
                  <td><i class="dot-s {s.code}"></i>{s.code === 'c' ? 'silence' : s.code === 'o' ? 'ouvert' : s.code === 'e' ? 'limite' : s.code === 'w' ? 'affaibli' : s.code === 'a' ? 'absorbé' : '—'}</td></tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="muted">Aucun correspondant du jour avec une position connue (locator ou QRZ).</p>
        {/if}
        <p class="src">Projection azimutale équidistante centrée sur le QTH (distances et azimuts vrais depuis chez vous).
          Molette sur la carte : zoom. Pas de 5°, anneaux de 25 km jusqu'à 300 km, 50 km jusqu'à 1000 km puis 250 km ; au-delà de 3500 km, plusieurs sauts. Même calcul que le tableau « Portée par bande ». Calcul de {data.when}, R {data.ssn}.
          Fond de carte et villes Natural Earth (domaine public), plus détaillés en zoomant.</p>
      </div>
    </div>
  {:else}
    <p class="muted">{data ? data.msg : 'Calcul de la carte…'}</p>
  {/if}
</div>

<style>
  .sm { display: flex; flex-direction: column; gap: 8px; }
  .bar { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
  .bands { display: inline-flex; border: 1px solid rgba(207, 181, 59, 0.6); border-radius: 999px; overflow: hidden; }
  .bands button { border: 0; border-radius: 0; background: rgba(0, 0, 0, 0.3); padding: 3px 10px; font-size: 0.85rem; }
  .bands button + button { border-left: 1px solid rgba(207, 181, 59, 0.3); }
  .bands button.on { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); font-weight: 600; }
  .tog { border-radius: 999px; padding: 3px 12px; font-size: 0.82rem; }
  .tog.on { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); }
  .wrap { display: flex; gap: 18px; flex-wrap: wrap; align-items: flex-start; }
  .map { flex: 0 1 600px; min-width: 320px; height: auto; cursor: zoom-in; }
  .zoom button { padding: 3px 8px; font-size: 0.78rem; }
  .side { flex: 1 1 300px; display: flex; flex-direction: column; gap: 8px; }
  .sea { fill: #10141a; stroke: var(--gold-soft); }
  .land { fill: #2a2a24; }
  .coast { fill: none; stroke: rgba(230, 226, 211, 0.55); stroke-width: 0.7; pointer-events: none; }
  .border { fill: none; stroke: rgba(230, 226, 211, 0.22); stroke-width: 0.5; pointer-events: none; }
  .grat { fill: none; stroke: rgba(207, 181, 59, 0.08); pointer-events: none; }
  .cell { stroke: none; }
  .cell:hover { stroke: var(--gold); stroke-width: 1.2; }
  .ring { fill: none; stroke: rgba(207, 181, 59, 0.35); stroke-dasharray: 3 4; pointer-events: none; }
  .rlab { fill: var(--gold-soft); font-size: 10px; pointer-events: none; }
  .card { fill: var(--gold); font-size: 14px; font-weight: 700; }
  .home { fill: var(--gold); stroke: #000; }
  .city { fill: rgba(230, 226, 211, 0.85); pointer-events: none; }
  .cname { fill: rgba(230, 226, 211, 0.85); font-size: 10px; pointer-events: none; paint-order: stroke; stroke: rgba(0, 0, 0, 0.8); stroke-width: 2.5px; }
  .st { cursor: help; }
  .dot { stroke: #000; stroke-width: 1; fill: #6eaae6; }
  .dot.c { fill: #fff; stroke: var(--bad); stroke-width: 2.5; }
  .call { fill: #fff; font-size: 11px; font-family: ui-monospace, monospace; paint-order: stroke; stroke: #000; stroke-width: 3px; }
  .hover { min-height: 2.6em; margin: 0; font-size: 0.9rem; color: var(--text); background: rgba(0, 0, 0, 0.35); border-radius: 6px; padding: 6px 8px; }
  .legend { display: flex; flex-direction: column; gap: 3px; font-size: 0.82rem; }
  .legend i, .dot-s { display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 6px; vertical-align: -2px; }
  .hatch { background: repeating-linear-gradient(45deg, rgba(255,255,255,0.12) 0 3px, transparent 3px 6px); }
  h4 { margin: 4px 0 0; color: var(--gold); font-size: 0.85rem; font-weight: 600; }
  .list { font-size: 0.82rem; border-collapse: collapse; }
  .list td { padding: 2px 8px 2px 0; border-top: 1px solid rgba(207, 181, 59, 0.08); }
  .dot-s { border-radius: 50%; background: #6eaae6; }
  .dot-s.c { background: var(--bad); }
  .dot-s.o { background: var(--ok); } .dot-s.e { background: var(--warn); }
  .mono { font-family: ui-monospace, monospace; color: var(--gold); }
  .src { font-size: 0.76rem; color: var(--muted); margin: 0; }
  .muted { color: var(--muted); font-size: 0.85rem; margin: 0; }
</style>
