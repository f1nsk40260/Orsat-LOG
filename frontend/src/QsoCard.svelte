<script>
  // Fiche d'un QSO : les conditions dans lesquelles il a été réalisé.
  // Carte (trajet orthodromique, jour / nuit et ligne grise à l'instant du QSO), Soleil et
  // champ magnétique du jour (archive GFZ), position dans le cycle, contexte du trafic.
  import { onMount, onDestroy } from 'svelte';
  import L from 'leaflet';
  import 'leaflet/dist/leaflet.css';
  import { api } from './api.js';
  import { qsoInstant, sunElevation, daylight, shadeImage, greatCircle, MERCATOR_LAT } from './sun.js';

  let { entry, onclose, onedit } = $props();

  let ctx = $state(null);
  let error = $state('');
  let mapEl = $state();
  let map;

  const d8 = (d) => (d ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : '');
  const t4 = (t) => (t ? `${t.slice(0, 2)}:${t.slice(2, 4)}` : '');
  const r1 = (v) => (v == null ? '—' : +(+v).toFixed(1));
  const SLOTS = ['00', '03', '06', '09', '12', '15', '18', '21'];
  const kpColor = (k) => (k == null ? 'var(--muted)' : k >= 5 ? 'var(--bad)' : k >= 4 ? 'var(--warn)' : 'var(--ok)');

  // Hauteur du Soleil aux deux bouts, à l'instant du QSO
  const instant = $derived(ctx ? qsoInstant(ctx.qso.qso_date, ctx.qso.time_on) : null);
  const sunHere = $derived(ctx?.origin_ll ? sunElevation(instant, ...ctx.origin_ll) : null);
  const sunThere = $derived(ctx?.target_ll ? sunElevation(instant, ...ctx.target_ll) : null);

  // SFI des 7 jours autour : courbe
  const spark = $derived.by(() => {
    const pts = (ctx?.week || []).map((w, i) => [i, w.sfi]).filter(([, v]) => v != null);
    if (pts.length < 2) return null;
    const vs = pts.map(([, v]) => v);
    const lo = Math.min(...vs) - 2, hi = Math.max(...vs) + 2;
    const X = (i) => 6 + (i * 268) / 14, Y = (v) => 52 - ((v - lo) / (hi - lo)) * 44;
    return { path: pts.map(([i, v], k) => `${k ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' '),
             dot: ctx.week[7].sfi != null ? [X(7), Y(ctx.week[7].sfi)] : null, lo: Math.round(lo + 2), hi: Math.round(hi - 2),
             trend: ctx.week[7].sfi != null && ctx.week[4].sfi != null ? ctx.week[7].sfi - ctx.week[4].sfi : null };
  });

  const cycleText = $derived.by(() => {
    const c = ctx?.cycle;
    if (!c) return '';
    const m = c.from_max;
    const when = m === 0 ? 'au maximum' : m < 0 ? `${-m} mois avant le maximum` : `${m} mois après le maximum`;
    return `Cycle ${c.cycle} · ${when}${c.max_provisional ? ' (maximum provisoire)' : ''}`;
  });

  function drawMap() {
    if (!mapEl || !ctx) return;
    map = L.map(mapEl, { worldCopyJump: false, minZoom: 1, attributionControl: true, zoomControl: true });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd', maxZoom: 8, noWrap: true,
      attribution: '© OpenStreetMap · © CARTO',
    }).addTo(map);
    L.imageOverlay(shadeImage(instant), [[-MERCATOR_LAT, -180], [MERCATOR_LAT, 180]], { opacity: 1 }).addTo(map);
    const gold = '#cfb53b';
    const pts = [];
    if (ctx.origin_ll) {
      L.circleMarker(ctx.origin_ll, { radius: 6, color: gold, fillColor: gold, fillOpacity: 1, weight: 2 })
        .bindTooltip(`${ctx.qso.kind === 'SWL' ? 'WebSDR' : 'Station'} ${ctx.origin}`).addTo(map);
      pts.push(ctx.origin_ll);
    }
    if (ctx.target_ll) {
      L.circleMarker(ctx.target_ll, { radius: 6, color: '#6eaae6', fillColor: '#6eaae6', fillOpacity: 1, weight: 2 })
        .bindTooltip(`${ctx.qso.call}${ctx.qso.gridsquare ? ' · ' + ctx.qso.gridsquare : ''}`).addTo(map);
      pts.push(ctx.target_ll);
    }
    if (pts.length === 2) {
      for (const seg of greatCircle(pts[0], pts[1])) {
        L.polyline(seg, { color: gold, weight: 2.5, opacity: 0.95 }).addTo(map);
      }
      map.fitBounds(L.latLngBounds(pts).pad(0.35), { maxZoom: 5 });
    } else if (pts.length === 1) {
      map.setView(pts[0], 3);
    } else {
      map.setView([30, 0], 1);
    }
  }

  onMount(async () => {
    try {
      ctx = await api.qsoContext(entry.id);
      setTimeout(drawMap, 0);
    } catch (err) {
      error = err.message;
    }
  });
  onDestroy(() => map?.remove());
</script>

<div class="backdrop" onclick={onclose} role="presentation"></div>
<div class="panel card" role="dialog" aria-label="Fiche du QSO">
  <div class="head">
    <div>
      <h2 class="call mono">{entry.call}</h2>
      <div class="sub">
        {d8(entry.qso_date)} · {t4(entry.time_on)} UTC · {entry.band || '—'} · {entry.submode || entry.mode || '—'}
        {#if entry.freq} · {(entry.freq / 1e6).toFixed(3)} MHz{/if}
        {#if entry.kind === 'SWL'}<span class="swl">écoute SWL</span>{/if}
      </div>
    </div>
    <div class="head-btns">
      {#if onedit}<button type="button" onclick={() => onedit(entry)} title="Corriger ce QSO">✎ Modifier</button>{/if}
      <button type="button" onclick={onclose}>Fermer</button>
    </div>
  </div>

  {#if error}
    <p class="err">{error}</p>
  {:else if !ctx}
    <p class="muted">Chargement…</p>
  {:else}
    <div class="body">
      <div class="left">
        <div class="map" bind:this={mapEl}></div>
        <div class="legend">
          <span><i class="sw gold"></i>trajet (chemin court)</span>
          <span><i class="sw grey"></i>ligne grise (Soleil entre +6° et −6°)</span>
          <span><i class="sw night"></i>nuit</span>
          <span class="muted">à {t4(entry.time_on)} UTC le {d8(entry.qso_date)}</span>
        </div>
        <div class="ends">
          <div>
            <b>{ctx.qso.kind === 'SWL' ? 'WebSDR' : 'Chez toi'}</b> <span class="mono">{ctx.origin || '—'}</span>
            {#if sunHere != null}<span class="day">{daylight(sunHere)}</span> <span class="muted">Soleil {r1(sunHere)}°</span>{/if}
          </div>
          <div>
            <b>Chez {entry.call}</b> <span class="mono">{entry.gridsquare || (ctx.target_ll ? 'coordonnées QRZ' : '—')}</span>
            {#if sunThere != null}<span class="day">{daylight(sunThere)}</span> <span class="muted">Soleil {r1(sunThere)}°</span>{/if}
          </div>
          <div class="geo">
            {#if entry.distance_km != null}<b>{entry.distance_km} km</b> · azimut {entry.bearing}°{/if}
            {#if entry.country} · {entry.country}{entry.cont ? ` (${entry.cont})` : ''}{entry.cqz ? ` · zone CQ ${entry.cqz}` : ''}{/if}
            {#if entry.confirmed}<span class="conf">◆ confirmé {entry.confirmed}</span>{/if}
          </div>
        </div>
      </div>

      <div class="right">
        <section>
          <h3>Soleil et champ magnétique</h3>
          <div class="kpis">
            <div><span>SFI</span><b>{ctx.solar.sfi != null ? Math.round(ctx.solar.sfi) : entry.sfi != null ? Math.round(entry.sfi) : '—'}</b></div>
            <div><span>Indice A</span><b>{ctx.solar.ap ?? entry.a_index ?? '—'}</b></div>
            <div><span>K du QSO</span><b style:color={kpColor(ctx.solar.kp?.[ctx.solar.slot] ?? entry.k_index)}>{r1(ctx.solar.kp?.[ctx.solar.slot] ?? entry.k_index)}</b></div>
            <div><span>Taches</span><b>{ctx.solar.sn ?? '—'}</b></div>
          </div>
          {#if cycleText}<p class="cycle">{cycleText}</p>{/if}

          {#if ctx.solar.kp}
            <div class="kp">
              <div class="lbl">Kp de la journée (créneaux de 3 h UTC)</div>
              <svg viewBox="0 0 280 74" class="kpsvg">
                {#each ctx.solar.kp as k, i}
                  {@const h = k == null ? 0 : Math.max(2, (k / 9) * 52)}
                  <rect x={8 + i * 34} y={58 - h} width="26" height={h} rx="2" fill={kpColor(k)}
                        opacity={i === ctx.solar.slot ? 1 : 0.45} />
                  {#if i === ctx.solar.slot}<rect x={6 + i * 34} y="2" width="30" height="58" fill="none" stroke="#cfb53b" stroke-width="1.2" rx="3" />{/if}
                  <text x={21 + i * 34} y="70" text-anchor="middle">{SLOTS[i]}</text>
                  {#if k != null}<text x={21 + i * 34} y={54 - h} text-anchor="middle" class="v">{r1(k)}</text>{/if}
                {/each}
              </svg>
            </div>
          {/if}

          {#if spark}
            <div class="kp">
              <div class="lbl">SFI des 7 jours autour
                {#if spark.trend != null}<span class="muted"> — {spark.trend > 2 ? 'en hausse' : spark.trend < -2 ? 'en baisse' : 'stable'}</span>{/if}
              </div>
              <svg viewBox="0 0 280 60" class="kpsvg">
                <line x1="137" y1="2" x2="137" y2="56" stroke="#cfb53b" stroke-dasharray="2 3" stroke-width="1" />
                <path d={spark.path} fill="none" stroke="#6eaae6" stroke-width="2" />
                {#if spark.dot}<circle cx={spark.dot[0]} cy={spark.dot[1]} r="3.5" fill="#cfb53b" />{/if}
                <text x="2" y="10" class="v">{spark.hi}</text><text x="2" y="56" class="v">{spark.lo}</text>
              </svg>
            </div>
          {/if}

          {#if ctx.snapshot}
            <p class="snap">Relevé du carnet à {t4(ctx.snapshot.time)} UTC : SFI {ctx.snapshot.sfi ?? '—'}, A {ctx.snapshot.a_index ?? '—'},
              K {ctx.snapshot.k_index ?? '—'}{ctx.snapshot.xray ? `, X ${ctx.snapshot.xray}` : ''}{ctx.snapshot.geomagfield ? ` — ${ctx.snapshot.geomagfield}` : ''}</p>
          {/if}
          <p class="src">{ctx.solar.source === 'GFZ' ? 'Indices : archive GFZ Potsdam (CC BY 4.0).' : entry.solar_src === 'hamqsl' ? 'Indices relevés à la saisie (hamqsl.com).' : 'Pas d’indices pour cette date.'}</p>
        </section>

        <section>
          <h3>Ce jour-là sur {entry.band || 'cette bande'} <span class="n">{ctx.same_day_band.length}</span></h3>
          {#if ctx.same_day_band.length}
            <ul class="list">
              {#each ctx.same_day_band.slice(0, 14) as o}
                <li><span class="mono t">{t4(o.time_on)}</span> <span class="mono c">{o.call}</span>
                    <span class="muted">{o.country || ''}{o.distance_km != null ? ` · ${o.distance_km} km` : ''}</span></li>
              {/each}
            </ul>
            {#if ctx.same_day_band.length > 14}<p class="muted small">… et {ctx.same_day_band.length - 14} autres</p>{/if}
          {:else}<p class="muted small">Aucun autre QSO ce jour-là sur cette bande.</p>{/if}
        </section>

        {#if entry.kind !== 'SWL'}
          <section>
            <h3>Avec {entry.call} <span class="n">{ctx.same_call.length}</span></h3>
            {#if ctx.same_call.length}
              <ul class="list">
                {#each ctx.same_call.slice(0, 10) as o}
                  <li><span class="mono t">{d8(o.qso_date)}</span> <span class="muted">{o.band || ''} {o.submode || o.mode || ''}</span>
                      <span class="muted">{o.sfi != null ? `SFI ${Math.round(o.sfi)}` : ''}{o.k_index != null ? ` · K ${r1(o.k_index)}` : ''}</span></li>
                {/each}
              </ul>
            {:else}<p class="muted small">Premier QSO avec cette station.</p>{/if}
          </section>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.65); z-index: 40; }
  .card {
    position: fixed; z-index: 41; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: min(1220px, calc(100vw - 32px)); max-height: calc(100vh - 32px); overflow-y: auto;
  }
  .head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 10px; }
  .call { margin: 0; font-size: 1.6rem; color: var(--gold); letter-spacing: 0.06em; }
  .sub { color: var(--text); font-size: 0.9rem; margin-top: 2px; }
  .swl { margin-left: 8px; color: rgb(110, 170, 230); }
  .head-btns { display: flex; gap: 8px; }
  .body { display: grid; grid-template-columns: 1.55fr 1fr; gap: 16px; }
  .map { height: 430px; border: 1px solid var(--panel-edge); border-radius: 6px; background: #0b0d12; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 0.75rem; color: var(--muted); margin: 6px 0 8px; }
  .sw { display: inline-block; width: 18px; height: 8px; border-radius: 2px; margin-right: 5px; vertical-align: middle; }
  .sw.gold { background: #cfb53b; height: 3px; }
  .sw.grey { background: rgba(207, 181, 59, 0.35); }
  .sw.night { background: rgba(4, 6, 20, 0.75); border: 1px solid #333; }
  .ends { display: grid; gap: 4px; font-size: 0.88rem; }
  .ends b { color: var(--gold-soft); font-weight: 600; }
  .day { margin-left: 8px; color: var(--text); }
  .geo { margin-top: 4px; }
  .conf { margin-left: 10px; color: var(--gold); }
  section { border: 1px solid var(--panel-edge); border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; }
  h3 { margin: 0 0 8px; color: var(--gold); font-size: 0.82rem; letter-spacing: 0.1em; text-transform: uppercase; }
  h3 .n { color: var(--muted); font-weight: 400; letter-spacing: 0; margin-left: 4px; }
  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
  .kpis div { background: rgba(0, 0, 0, 0.35); border-radius: 5px; padding: 4px 6px; text-align: center; }
  .kpis span { display: block; font-size: 0.66rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
  .kpis b { font-size: 1.15rem; color: var(--text); }
  .cycle { margin: 8px 0 0; font-size: 0.82rem; color: var(--gold-soft); }
  .kp { margin-top: 8px; }
  .lbl { font-size: 0.72rem; color: var(--muted); margin-bottom: 2px; }
  .kpsvg { width: 100%; height: auto; display: block; }
  .kpsvg text { fill: var(--muted); font-size: 8px; font-family: inherit; }
  .kpsvg text.v { fill: var(--text); }
  .snap { font-size: 0.78rem; margin: 8px 0 0; }
  .src { font-size: 0.7rem; color: var(--muted); margin: 6px 0 0; }
  .list { list-style: none; margin: 0; padding: 0; font-size: 0.8rem; max-height: 180px; overflow-y: auto; }
  .list li { display: flex; gap: 8px; padding: 1px 0; }
  .list .t { color: var(--muted); min-width: 44px; }
  .list .c { color: var(--gold); min-width: 80px; }
  .small { font-size: 0.78rem; margin: 0; }
  .muted { color: var(--muted); }
  .err { color: var(--bad); }
  @media (max-width: 900px) { .body { grid-template-columns: 1fr; } .map { height: 320px; } }
</style>
