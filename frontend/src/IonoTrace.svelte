<script>
  // Fenêtre « Trajet d'une onde » : rebond d'une onde HF sur l'ionosphère mesurée en ce moment (raytrace.js)
  import { api } from './api.js';
  import { dayOf, fmtTime } from './util.js';
  import { profile, trace, fan, foMax, layerName, R } from './raytrace.js';

  let { onclose = null, locator = 'IN93LR' } = $props();

  // ---------- mesures de l'ionosonde (page du jour) ----------
  let data = $state(null);
  let idx = $state(-1);             // mesure choisie (-1 = la plus récente)
  async function load() { data = await api.layers(dayOf()).catch((e) => ({ ok: false, msg: e.message })); }
  $effect(() => { load(); const t = setInterval(load, 15 * 60 * 1000); return () => clearInterval(t); });
  const pts = $derived(data?.ok ? data.points : []);
  const cur = $derived(pts.length ? Math.min(idx < 0 ? pts.length - 1 : idx, pts.length - 1) : -1);

  // valeurs de la mesure, médiane sur ±20 min (un ionogramme mal dépouillé ne fausse pas le tracé)
  const mn = (t) => +t.slice(0, 2) * 60 + +t.slice(2, 4);
  function med(get) {
    const t = mn(pts[cur].time);
    const v = pts.filter((q) => Math.abs(mn(q.time) - t) <= 20).map(get).filter((x) => x != null).sort((a, b) => a - b);
    return v.length ? v[Math.floor(v.length / 2)] : null;
  }
  const iono = $derived(cur < 0 ? null : {
    foF2: med((p) => p.f2[0]), hmF2: med((p) => p.f2[1]), foF1: pts[cur].f1[0] ? med((p) => p.f1[0]) : null,
    hmF1: med((p) => p.f1[1]), foE: pts[cur].e[0] ? med((p) => p.e[0]) : null, hmE: med((p) => p.e[1]),
    foEs: pts[cur].es ? med((p) => p.es) : null, time: pts[cur].time,
  });

  // ---------- réglages : fréquence et angle de départ ----------
  const BANDS = [['160m', 1.84], ['80m', 3.65], ['60m', 5.36], ['40m', 7.1], ['30m', 10.12], ['20m', 14.1],
                 ['17m', 18.1], ['15m', 21.2], ['12m', 24.94], ['10m', 28.5], ['6m', 50.15]];
  let freq = $state(14.1);
  let elev = $state(10);
  const setF = (v) => (freq = Math.round(Math.max(1, Math.min(60, v)) * 100) / 100);
  const setE = (v) => (elev = Math.max(1, Math.min(89, Math.round(v))));
  const bandOf = $derived(BANDS.find(([, f]) => Math.abs(f - freq) < 0.6)?.[0]);

  // molette (non passive) sur les réglages
  function wheel(node, fn) {
    const h = (e) => { e.preventDefault(); fn(e.deltaY < 0 ? 1 : -1); };
    node.addEventListener('wheel', h, { passive: false });
    return { destroy: () => node.removeEventListener('wheel', h) };
  }

  // ---------- calcul ----------
  const fp2 = $derived(iono ? profile(iono) : null);
  const ELEVS = Array.from({ length: 30 }, (_, i) => 1 + i * 3);
  const fanRes = $derived(fp2 ? fan(fp2, freq, ELEVS) : null);
  const ray = $derived(fp2 ? trace(fp2, freq, elev) : null);
  // MUF pour l'angle choisi : plus haute fréquence qui revient encore (dichotomie)
  const muf = $derived.by(() => {
    if (!fp2) return null;
    let lo = 1, hi = 80;
    if (trace(fp2, lo, elev, 3).ground == null) return null;
    for (let i = 0; i < 12; i++) { const m = (lo + hi) / 2; if (trace(fp2, m, elev, 3).ground != null) lo = m; else hi = m; }
    return Math.round(lo * 10) / 10;
  });
  const HOPS = 3;

  // ---------- dessin : coupe de la Terre, échelle verticale exagérée ----------
  let cw = $state(900);
  const W = $derived(Math.max(300, Math.round(cw)));
  const H = $derived(Math.round(Math.min(420, Math.max(240, W * 0.42))));
  const HTOP = 500;
  const dMax = $derived.by(() => {
    const far = ray?.ground ? ray.ground * HOPS : 0;
    return Math.max(1500, Math.min(12000, Math.max(far, fanRes?.maxHop ?? 0, 2000) * 1.08));
  });
  const geo = $derived.by(() => {
    const span = dMax / R;
    const ex = Math.max(1, (0.3 * dMax) / HTOP);                 // exagération verticale
    const top = R + ex * HTOP;
    const xr = 2 * top * Math.sin(span / 2), y0 = R * Math.cos(span / 2);
    const s = Math.min((W - 90) / xr, (H - 34) / (top - y0));
    return { span, ex, s, top, cx: W / 2 + 30, cy: 8 + top * s };   // centre de la Terre (hors écran, en bas)
  });
  const P = (th, h) => {
    const g = geo, a = th - g.span / 2, r = R + g.ex * Math.min(h, HTOP + 20);
    return [(g.cx + r * g.s * Math.sin(a)).toFixed(1), (g.cy - r * g.s * Math.cos(a)).toFixed(1)];
  };
  const path = (pts, off = 0) => pts.map(([th, h], i) => `${i ? 'L' : 'M'}${P(th + off, h).join(',')}`).join(' ');
  const arc = (h, n = 80) => Array.from({ length: n + 1 }, (_, i) => `${i ? 'L' : 'M'}${P((i / n) * geo.span, h).join(',')}`).join(' ');

  // ionosphère en strates colorées selon la densité (fp / fo max)
  const strata = $derived.by(() => {
    if (!fp2) return [];
    const fmx = Math.max(1, foMax(iono));
    const out = [];
    for (let h = 70; h < HTOP; h += 6) {
      const o = fp2(h + 3) / (fmx * fmx);          // densité relative (fp² ∝ électrons)
      if (o > 0.02) out.push({ h, o: Math.min(0.38, o * 0.38) });
    }
    return out;
  });
  const band = (h0, h1, n = 60) => {
    const a = Array.from({ length: n + 1 }, (_, i) => P((i / n) * geo.span, h1).join(','));
    const b = Array.from({ length: n + 1 }, (_, i) => P(((n - i) / n) * geo.span, h0).join(','));
    return `M${a.join(' L')} L${b.join(' L')} Z`;
  };
  const kmTicks = $derived.by(() => {
    const st = dMax > 6000 ? 1000 : 500;
    return Array.from({ length: Math.floor(dMax / st) + 1 }, (_, i) => i * st);
  });
  const hops = $derived(ray?.ground ? Array.from({ length: HOPS }, (_, k) => k) : [0]);
  const km = (v) => Math.round(v).toLocaleString('fr-FR');
</script>

<div class="backdrop" onclick={onclose} role="presentation"></div>
<section class="panel tr">
  <h2 class="panel-title">Trajet d'une onde depuis {locator}
    <button class="ghost close" onclick={onclose} title="Fermer">✕</button></h2>

  {#if !iono}
    <p class="muted">{data ? (data.msg || 'Pas de mesure d\'ionosonde aujourd\'hui.') : 'Lecture de l\'ionosonde…'}</p>
  {:else}
    <div class="ctl">
      <div class="grp">
        <span class="lab">Fréquence</span>
        <div class="bands">
          {#each BANDS as [b, f]}<button type="button" class:on={bandOf === b} onclick={() => setF(f)}>{b}</button>{/each}
        </div>
        <div class="val" use:wheel={(d) => setF(freq + d * 0.1)} title="Molette : ±100 kHz">
          <button type="button" onclick={() => setF(freq - 0.1)}>−</button>
          <b>{freq.toFixed(2)} MHz</b>
          <button type="button" onclick={() => setF(freq + 0.1)}>+</button>
        </div>
      </div>
      <div class="grp">
        <span class="lab">Angle de départ</span>
        <div class="val" use:wheel={(d) => setE(elev + d)} title="Molette : ±1°">
          <button type="button" onclick={() => setE(elev - 1)}>−</button>
          <b>{elev}°</b>
          <button type="button" onclick={() => setE(elev + 1)}>+</button>
        </div>
        <span class="lab">Mesure</span>
        <div class="val" use:wheel={(d) => (idx = Math.max(0, Math.min(pts.length - 1, cur + d)))} title="Molette : mesure précédente / suivante">
          <button type="button" onclick={() => (idx = Math.max(0, cur - 1))} disabled={cur <= 0}>◀</button>
          <b>{fmtTime(iono.time)} UTC</b>
          <button type="button" onclick={() => (idx = cur + 1 >= pts.length - 1 ? -1 : cur + 1)} disabled={cur >= pts.length - 1}>▶</button>
        </div>
      </div>
    </div>

    <div class="wrap" bind:clientWidth={cw}>
      <svg width={W} height={H} viewBox="0 0 {W} {H}" role="img" aria-label="Coupe de l'ionosphère et trajet de l'onde">
        {#each strata as s}<path d={band(s.h, s.h + 6)} class="iono" style="opacity: {s.o}" />{/each}
        {#each [100, 200, 300, 400] as h}
          <path d={arc(h)} class="alt" />
          <text x={P(0, h)[0] - 4} y={+P(0, h)[1] + 3} class="axis" text-anchor="end">{h}</text>
        {/each}
        <text x={P(0, 470)[0] - 4} y={+P(0, 470)[1] + 3} class="axis" text-anchor="end">km</text>
        <!-- éventail : tous les angles, en léger -->
        {#each fanRes.rays as r}<path d={path(r.pts)} class="fan" class:out={r.ground == null} />{/each}
        <!-- zone de silence -->
        {#if fanRes.skip && fanRes.skip > 60 && !fanRes.allBack}
          <path d={Array.from({ length: 31 }, (_, i) => `${i ? 'L' : 'M'}${P((i / 30) * (fanRes.skip / R), 0).join(',')}`).join(' ')} class="skip" />
        {/if}
        <path d={arc(0)} class="ground" />
        {#each kmTicks as d}
          <text x={P(d / R, 0)[0]} y={+P(d / R, 0)[1] + 13} class="axis" text-anchor={d === 0 ? 'start' : 'middle'}>{d ? km(d) : '0 km'}</text>
        {/each}
        <!-- rayon choisi, répété sur 3 sauts -->
        {#each hops as k}<path d={path(ray.pts, k * (ray.ground ?? 0) / R)} class="ray" style="opacity: {1 - k * 0.25}" />{/each}
        {#if ray.ground}
          {#each hops as k}
            {@const [x, y] = P((k + 1) * ray.ground / R, 0)}
            <circle cx={x} cy={y} r="4" class="land" />
            <text x={x} y={+y - 8} class="lt" text-anchor="middle">{km((k + 1) * ray.ground)} km</text>
          {/each}
        {/if}
        <circle cx={P(0, 0)[0]} cy={P(0, 0)[1]} r="4" class="me" />
      </svg>
    </div>

    <div class="res">
      {#if ray.ground}
        <div><span>Retour au sol (1er saut)</span><b class="big">{km(ray.ground)} km</b></div>
        <div><span>Réfléchie par la couche</span><b>{layerName(ray.apex, iono)} · à {Math.round(ray.apex)} km</b></div>
        <div><span>2e et 3e sauts</span><b>{km(2 * ray.ground)} km · {km(3 * ray.ground)} km</b></div>
      {:else}
        <div><span>À {elev}°, sur {freq.toFixed(2)} MHz</span><b class="bad">l'onde traverse l'ionosphère : pas de retour</b></div>
      {/if}
      <div><span>MUF pour {elev}°</span><b>{muf != null ? `${muf} MHz` : '—'}</b></div>
      <div><span>Zone de silence</span>
        <b>{fanRes.allBack ? 'aucune (tous les angles reviennent)' : fanRes.skip != null ? `0 à ${km(fanRes.skip)} km` : 'totale : la fréquence passe à travers'}</b></div>
      <div><span>Portée maxi d'un saut</span><b>{fanRes.maxHop != null ? `${km(fanRes.maxHop)} km` : '—'}</b></div>
      <div><span>Ionosphère ({data.station}, {fmtTime(iono.time)} UTC)</span>
        <b>foF2 {iono.foF2 ?? '—'} MHz à {iono.hmF2 ?? '—'} km{iono.foE ? ` · foE ${iono.foE}` : ''}{iono.foF1 ? ` · foF1 ${iono.foF1}` : ''}{iono.foEs ? ` · foEs ${iono.foEs}` : ''}</b></div>
    </div>
    <p class="src">Tracé de rayons sur Terre sphérique dans le profil électronique reconstruit à partir de l'ionosonde
      (couches de Chapman). Même ionosphère supposée sur tout le trajet, sans champ magnétique ni absorption :
      c'est la géométrie du saut, pas le bilan de liaison. Échelle verticale exagérée ×{Math.round(geo.ex)}.
      L'onde de sol (quelques dizaines de km) n'est pas représentée.</p>
  {/if}
</section>

<style>
  .backdrop { position: fixed; inset: 0; z-index: 20; background: rgba(0, 0, 0, 0.6); }
  .tr { position: fixed; z-index: 21; top: 50%; left: 50%; transform: translate(-50%, -50%);
        width: min(1050px, 96vw); max-height: 94vh; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
  .tr .panel-title { display: flex; align-items: center; font-size: 0.95rem; }
  .close { margin-left: auto; padding: 1px 12px; font-size: 1.5rem; line-height: 1.2; }
  .ctl { display: flex; flex-wrap: wrap; gap: 8px 22px; align-items: center; }
  .grp { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; }
  .lab { color: var(--muted); font-size: 0.85rem; }
  .bands { display: flex; flex-wrap: wrap; gap: 4px; }
  .bands button { padding: 4px 9px; font-size: 0.9rem; }
  .bands button.on { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); font-weight: 600; }
  .val { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--panel-edge); border-radius: 6px;
         padding: 2px 4px; cursor: ns-resize; }
  .val b { min-width: 92px; text-align: center; font-size: 1.05rem; color: var(--gold); }
  .val button { padding: 2px 11px; font-size: 1.15rem; line-height: 1.2; }
  .wrap { width: 100%; }
  svg { display: block; }
  .iono { fill: rgb(207, 181, 59); }
  .alt { fill: none; stroke: rgba(207, 181, 59, 0.15); stroke-dasharray: 3 4; }
  .axis { fill: var(--muted); font-size: 11px; }
  .ground { fill: none; stroke: rgb(120, 160, 90); stroke-width: 2; }
  .skip { fill: none; stroke: var(--bad); stroke-width: 5; opacity: 0.75; }
  .fan { fill: none; stroke: rgba(240, 225, 170, 0.22); stroke-width: 1; }
  .fan.out { stroke: rgba(160, 160, 160, 0.14); }
  .ray { fill: none; stroke: rgb(255, 120, 60); stroke-width: 2.2; stroke-linejoin: round; }
  .land { fill: rgb(255, 120, 60); stroke: #000; stroke-width: 1; }
  .me { fill: var(--gold); stroke: #000; stroke-width: 1; }
  .lt { fill: var(--text); font-size: 12px; font-weight: 600; paint-order: stroke; stroke: rgba(0, 0, 0, 0.7); stroke-width: 3px; }
  .res { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 4px 20px; font-size: 0.95rem; }
  .res div { display: flex; justify-content: space-between; gap: 10px; border-bottom: 1px solid rgba(207, 181, 59, 0.08); padding: 2px 0; }
  .res span { color: var(--muted); }
  .res b { font-weight: 500; text-align: right; }
  .res b.big { color: rgb(255, 140, 80); font-size: 1.15rem; font-weight: 700; }
  .res b.bad { color: var(--warn); }
  .src { font-size: 0.75rem; color: var(--muted); margin: 0; }
  .muted { color: var(--muted); }
</style>
