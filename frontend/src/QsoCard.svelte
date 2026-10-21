<script>
  // Fiche d'un QSO : les conditions dans lesquelles il a été réalisé.
  // Carte (trajet orthodromique, jour / nuit et ligne grise à l'instant du QSO), Soleil et
  // champ magnétique du jour (archive GFZ), position dans le cycle, contexte du trafic.
  import { onMount, onDestroy } from 'svelte';
  import L from 'leaflet';
  import 'leaflet/dist/leaflet.css';
  import { api } from './api.js';
  import EibiPick from './EibiPick.svelte';
  import { addFonds } from './mapbase.js';
  import { tipSfi, tipA, tipK, tipSn, TIP_FOF2, TIP_MUF3000, TIP_MUFHOP, TIP_FOES } from './proptips.js';
  import { qsoInstant, sunElevation, daylight, shadeImage, greatCircle, MERCATOR_LAT } from './sun.js';

  let { entry, onclose, onedit } = $props();

  let ctx = $state(null);
  let error = $state('');
  let mapEl = $state();
  let map;
  let iono = $state(null);          // ionosphère mesurée (GIRO), chargée après la fiche
  let ionoBusy = $state(false);
  let ionoErr = $state('');
  let ionoLayer;
  // Annuaire QRZ : photo, prénom, nom, QTH du correspondant (pas pour les écoutes SWL)
  let who = $state(null);
  let bigPhoto = $state(false);

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

  // Ionosphère : MUF limitante du trajet (plus petite des MUF aux points de réflexion)
  const ionoPts = $derived((iono?.points || []).filter((p) => p.station));
  const mufPath = $derived.by(() => {
    const v = ionoPts.map((p) => p.muf_hop ?? p.measure.mufd).filter((x) => x != null);
    return v.length ? Math.min(...v) : null;
  });
  const verdict = $derived.by(() => {
    const f = iono?.freq_mhz, m = mufPath;
    if (!f || !m) return null;
    const r = f / m;
    if (r <= 0.85) return { cls: 'ok', txt: `${f.toFixed(3)} MHz sous la MUF de ${m.toFixed(1)} MHz : réflexion F2 franche.` };
    if (r <= 1) return { cls: 'warn', txt: `${f.toFixed(3)} MHz juste sous la MUF de ${m.toFixed(1)} MHz : en limite, signaux souvent forts mais instables.` };
    return { cls: 'bad', txt: `${f.toFixed(3)} MHz au-dessus de la MUF de ${m.toFixed(1)} MHz : pas par la couche F2 seule — sporadique E, diffusion, ou ionosphère différente du point de mesure.` };
  });
  const foesMax = $derived(Math.max(0, ...ionoPts.map((p) => p.measure.foes ?? 0)) || null);

  // Courbe ±2 h d'un point : foF2 (bleu), MUF(3000) (or), fréquence du QSO (pointillés)
  function ionoCurve(p) {
    const s = (p.series || []).filter((x) => x.fof2 != null || x.mufd != null);
    if (s.length < 2) return null;
    const t0 = new Date(iono.when).getTime(), span = 2 * 3600e3;
    const vals = s.flatMap((x) => [x.fof2, x.mufd, x.foes]).filter((v) => v != null);
    if (iono.freq_mhz) vals.push(iono.freq_mhz);
    const hi = Math.ceil(Math.max(...vals) + 1), lo = 0;
    const X = (ts) => 22 + ((new Date(ts).getTime() - t0 + span) / (2 * span)) * 252;
    const Y = (v) => 62 - ((v - lo) / (hi - lo)) * 56;
    const path = (k) => {
      let d = '', pen = false;
      for (const x of s) {
        if (x[k] == null) { pen = false; continue; }
        d += `${pen ? 'L' : 'M'}${X(x.ts).toFixed(1)},${Y(x[k]).toFixed(1)}`;
        pen = true;
      }
      return d;
    };
    return { fof2: path('fof2'), mufd: path('mufd'), foes: path('foes'), hi,
             fy: iono.freq_mhz ? Y(iono.freq_mhz) : null, xq: X(iono.when) };
  }

  async function loadIono(refresh = false) {
    ionoBusy = true;
    ionoErr = '';
    try {
      iono = await api.qsoIono(entry.id, refresh);
      drawIono();
    } catch (err) {
      ionoErr = err.message;
    } finally {
      ionoBusy = false;
    }
  }

  // Points de réflexion et ionosondes sur la carte
  function drawIono() {
    if (!map || !iono?.points) return;
    ionoLayer?.remove();
    ionoLayer = L.layerGroup().addTo(map);
    for (const p of iono.points) {
      L.circleMarker(p.point, { radius: 4, color: '#cfb53b', fillColor: '#0b0d12', fillOpacity: 1, weight: 2 })
        .bindTooltip(`Point de réflexion · ${p.label}`).addTo(ionoLayer);
      if (p.station) {
        L.polyline([p.point, [p.station.lat, p.station.lon]], { color: '#9ad08a', weight: 1, dashArray: '3 4' }).addTo(ionoLayer);
        L.circleMarker([p.station.lat, p.station.lon], { radius: 5, color: '#9ad08a', fillColor: '#9ad08a', fillOpacity: 0.9, weight: 1 })
          .bindTooltip(`Ionosonde ${p.station.name} (${p.station.code})`).addTo(ionoLayer);
      }
    }
  }

  function drawMap() {
    if (!mapEl || !ctx) return;
    map = L.map(mapEl, { worldCopyJump: false, minZoom: 1, attributionControl: true, zoomControl: true });
    addFonds(L, map);
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
    // Stations décodées par le WebSDR sur la bande, dans l'heure du QSO (autorun)
    for (const h of ctx.heard?.points || []) {
      L.circleMarker([h.lat, h.lon], { radius: 2.5, color: '#e07a5f', fillColor: '#e07a5f', fillOpacity: 0.8, weight: 0 })
        .bindTooltip(`${h.call} · ${h.km ?? '?'} km · ${h.snr ?? '?'} dB (décodé par le WebSDR)`).addTo(map);
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

  // Écoute SWL : ligne de la grille EiBi retenue -> site et locator de l'émetteur, puis la fiche
  // est recalculée (trajet, point de réflexion, ionosphère)
  let eibiMsg = $state('');
  async function applyEibi(c) {
    if (!c.locator) { eibiMsg = 'Site d’émission inconnu de la grille : rien à appliquer.'; return; }
    const q = ctx.qso;
    try {
      const upd = await api.updateQso(q.id, { ...q, gridsquare: c.locator, qth: `${c.site} (${c.site_country})`,
        comment: q.comment || [c.lang, c.target ? `→ ${c.target}` : ''].filter(Boolean).join(' ') });
      Object.assign(entry, upd || {});
      map?.remove(); map = null; ionoLayer = null; iono = null;
      ctx = await api.qsoContext(q.id);
      eibiMsg = `Émetteur retenu : ${c.site} (${c.locator}).`;
      setTimeout(() => { drawMap(); loadIono(); }, 0);
    } catch (err) {
      eibiMsg = err.message;
    }
  }

  onMount(async () => {
    if (entry.kind !== 'SWL') api.qrzLookup(entry.call).then((r) => (who = r)).catch(() => {});
    try {
      ctx = await api.qsoContext(entry.id);
      setTimeout(() => { drawMap(); if (entry.kind !== 'SWL' || entry.freq) loadIono(); }, 0);
    } catch (err) {
      error = err.message;
    }
  });
  onDestroy(() => map?.remove());
</script>

<div class="backdrop" onclick={onclose} role="presentation"></div>
<div class="panel card" role="dialog" aria-label="Fiche du QSO">
  <div class="head">
    {#if who?.ok && who.image}
      <button type="button" class="photo" onclick={() => (bigPhoto = true)} title="Agrandir la photo (QRZ.com)">
        <img src={who.image} alt={`Photo de ${entry.call}`} referrerpolicy="no-referrer" />
      </button>
    {/if}
    <div class="ident">
      <h2 class="call mono">{#if entry.kind !== 'SWL'}<a href={`https://www.qrz.com/db/${encodeURIComponent(entry.call)}`} target="_blank" rel="noopener"
          title="Ouvrir la page QRZ.com de {entry.call} (nouvel onglet)">{entry.call}<small>QRZ ↗</small></a>{:else}{entry.call}{/if}</h2>
      {#if who && !who.ok && entry.kind !== 'SWL'}
        <div class="who dim" title={who.msg}>{(who.msg || '').includes('non réglés') ? 'Photo, nom et QTH : régler l’annuaire QRZ dans le panneau admin (carte QRZ).' : `QRZ.com : ${who.msg}`}</div>
      {/if}
      {#if who?.ok && (who.fname || who.name || who.qth)}
        <div class="who">{[who.fname, who.name].filter(Boolean).join(' ')}{who.qth ? ` · ${who.qth}` : ''}{who.state ? ` (${who.state})` : ''}{who.country ? ` · ${who.country}` : ''}</div>
      {/if}
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

  {#if bigPhoto && who?.image}
    <button type="button" class="photo-big" onclick={() => (bigPhoto = false)} title="Fermer">
      <img src={who.image} alt={`Photo de ${entry.call}`} referrerpolicy="no-referrer" />
      <span>{entry.call} · {[who.fname, who.name].filter(Boolean).join(' ')} — photo QRZ.com</span>
    </button>
  {/if}

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
          {#if ctx.heard?.points?.length}<span><i class="sw heard"></i>entendu par le WebSDR (±1 h)</span>{/if}
          {#if iono?.points?.length}<span><i class="sw iono"></i>ionosonde · ◯ point de réflexion</span>{/if}
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
            <div title={tipSfi(ctx.solar.sfi ?? entry.sfi)}><span>SFI</span><b>{ctx.solar.sfi != null ? Math.round(ctx.solar.sfi) : entry.sfi != null ? Math.round(entry.sfi) : '—'}</b></div>
            <div title={tipA(ctx.solar.ap ?? entry.a_index)}><span>Indice A</span><b>{ctx.solar.ap ?? entry.a_index ?? '—'}</b></div>
            <div title={tipK(ctx.solar.kp?.[ctx.solar.slot] ?? entry.k_index)}><span>K du QSO</span><b style:color={kpColor(ctx.solar.kp?.[ctx.solar.slot] ?? entry.k_index)}>{r1(ctx.solar.kp?.[ctx.solar.slot] ?? entry.k_index)}</b></div>
            <div title={tipSn(ctx.solar.sn)}><span>Taches</span><b>{ctx.solar.sn ?? '—'}</b></div>
          </div>
          {#if cycleText}<p class="cycle">{cycleText}</p>{/if}

          {#if ctx.solar.kp}
            <div class="kp">
              <div class="lbl" title={tipK(null)}>Kp de la journée (créneaux de 3 h UTC)</div>
              <svg viewBox="0 0 280 74" class="kpsvg">
                {#each ctx.solar.kp as k, i}
                  {@const h = k == null ? 0 : Math.max(2, (k / 9) * 52)}
                  <rect x={8 + i * 34} y={58 - h} width="26" height={h} rx="2" fill={kpColor(k)}
                        opacity={i === ctx.solar.slot ? 1 : 0.45}><title>{SLOTS[i]}–{String((i + 1) * 3).padStart(2, '0')} h UTC{'\n'}{tipK(k)}</title></rect>
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

        {#if entry.kind === 'SWL' && entry.freq}
          <section>
            <h3>Qui émettait ? <span class="n">grille EiBi</span></h3>
            {#if !ctx.target_ll}<p class="muted small">Site de l’émetteur inconnu : choisis la station entendue pour tracer le trajet et lire l’ionosphère.</p>{/if}
            <EibiPick freq={entry.freq} date={entry.qso_date} time={(entry.time_on || '').slice(0, 4)} onpick={applyEibi} compact />
            {#if eibiMsg}<p class="small" style="margin-top:4px">{eibiMsg}</p>{/if}
          </section>
        {/if}

        <section>
          <h3>Ionosphère mesurée
            {#if iono && !ionoBusy}<button type="button" class="mini" onclick={() => loadIono(true)} title="Interroger à nouveau GIRO">↻</button>{/if}
          </h3>
          {#if ionoBusy}
            <p class="muted small">Interrogation des ionosondes GIRO… (quelques secondes)</p>
          {:else if ionoErr}
            <p class="err small">{ionoErr}</p>
          {:else if iono && !iono.ok}
            <p class="muted small">{iono.msg}</p>
          {:else if iono}
            {#if verdict}<p class="verdict {verdict.cls}">{verdict.txt}</p>{/if}
            {#if iono.provisional}<p class="src">QSO récent : mesures encore en cours de publication, la fiche se complétera d’elle-même.</p>{/if}
            {#each iono.points as p}
              <div class="ipt">
                <div class="lbl">{p.label} · saut de {p.hop_km} km
                  {#if p.station} — ionosonde <b>{p.station.name}</b> à {p.station.km} km du point{/if}</div>
                {#if p.station}
                  <div class="kpis k5">
                    <div title={TIP_FOF2}><span>foF2</span><b>{r1(p.measure.fof2)}</b></div>
                    <div title={TIP_MUF3000}><span>MUF 3000</span><b>{r1(p.measure.mufd)}</b></div>
                    <div title={TIP_MUFHOP}><span>MUF du saut</span><b class="g">{r1(p.muf_hop)}</b></div>
                    <div title={TIP_FOES}><span>foEs</span><b>{r1(p.measure.foes)}</b></div>
                  </div>
                  <p class="src">Mesure de {p.measure.ts.slice(11, 16)} UTC ({p.dt_min ? `${p.dt_min} min d’écart` : 'à la minute'}){p.measure.cs === 999 ? ', dépouillée à la main' : p.measure.cs >= 0 ? `, confiance ${p.measure.cs} %` : ''} · MHz</p>
                  {@const c = ionoCurve(p)}
                  {#if c}
                    <svg viewBox="0 0 280 74" class="kpsvg">
                      <line x1={c.xq} y1="4" x2={c.xq} y2="62" stroke="#cfb53b" stroke-dasharray="2 3" />
                      {#if c.fy != null}<line x1="22" y1={c.fy} x2="274" y2={c.fy} stroke="#e8e2c8" stroke-dasharray="4 3" stroke-width="0.8" opacity="0.7" />{/if}
                      <path d={c.mufd} fill="none" stroke="#cfb53b" stroke-width="2" />
                      <path d={c.fof2} fill="none" stroke="#6eaae6" stroke-width="1.6" />
                      <path d={c.foes} fill="none" stroke="#9ad08a" stroke-width="1.2" opacity="0.9" />
                      <text x="2" y="10" class="v">{c.hi}</text><text x="2" y="64" class="v">0</text>
                      <text x="22" y="72">−2 h</text><text x={c.xq} y="72" text-anchor="middle">QSO</text><text x="274" y="72" text-anchor="end">+2 h</text>
                    </svg>
                    <div class="legend in">
                      <span><i class="sw gold"></i>MUF(3000)</span><span><i class="sw blue"></i>foF2</span>
                      <span><i class="sw green"></i>foEs</span><span><i class="sw dash"></i>fréquence du QSO</span>
                    </div>
                  {/if}
                {:else}
                  <p class="muted small">{p.msg}</p>
                {/if}
              </div>
            {/each}
            {#if foesMax && foesMax >= 5}<p class="small es">Couche E sporadique mesurée (foEs {r1(foesMax)} MHz) : ouvertures Es possibles jusque vers {Math.round(foesMax * 5)} MHz sur un saut de 2000 km.</p>{/if}
            {#if ionoPts.length}<p class="src">{iono.credit} · données de l’observatoire {ionoPts.map((p) => p.station.name).join(', ')}. MUF du saut : MUF(3000) mesurée ramenée à la longueur du saut (loi de la sécante).</p>{/if}
          {/if}
        </section>

        {#if ctx.heard}
          {@const h = ctx.heard}
          <section>
            <h3>Le WebSDR entendait <span class="n">{h.band} · ±1 h</span></h3>
            <p class="small"><b class="g">{h.stations}</b> station{h.stations > 1 ? 's' : ''} décodée{h.stations > 1 ? 's' : ''} sur {h.band} dans l'heure du QSO et les heures voisines.</p>
            {#if h.toward}
              <p class="small">Vers {entry.call} (azimut {entry.bearing}° ± 30°) : <b class="g">{h.toward.count}</b>
                {#if h.toward.far_call} — la plus lointaine <span class="mono">{h.toward.far_call}</span> à {h.toward.far_km} km ({h.toward.far_snr ?? '?'} dB){/if}</p>
            {/if}
            {#if h.near}
              <p class="small">Station décodée la plus proche de {entry.call} : <span class="mono">{h.near.call}</span>, à {h.near.km_from_target} km de lui ({h.near.snr ?? '?'} dB en {h.near.mode.toUpperCase()}).</p>
            {/if}
            {#if !h.detail}<p class="src">Détail effacé (plus de 2 ans) : seul le résumé est conservé.</p>{/if}
            <p class="src">Décodages FT8 / FT4 / JS8 / WSPR de l'autorun du WebSDR (IN93LR) : une ouverture constatée, pas une prévision.</p>
          </section>
        {/if}

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
  .head { align-items: center; }
  .ident { flex: 1; }
  /* Indicatif = bouton encadré vers sa page QRZ.com */
  .call a { color: inherit; text-decoration: none; display: inline-flex; align-items: center; gap: 8px;
            border: 1px solid rgba(207, 181, 59, 0.6); border-radius: 6px; padding: 0 10px 1px;
            background: linear-gradient(180deg, rgba(207, 181, 59, 0.16), rgba(207, 181, 59, 0.04)); }
  .call a:hover { background: linear-gradient(180deg, rgba(207, 181, 59, 0.32), rgba(207, 181, 59, 0.1)); }
  .call a small { font-size: 0.62rem; letter-spacing: 0.05em; color: var(--gold-soft); font-family: inherit; }
  .who.dim { color: var(--muted); font-size: 0.78rem; }
  .who { color: var(--gold-soft); font-size: 0.95rem; margin-top: 1px; }
  .photo { padding: 0; border: 1px solid var(--panel-edge); border-radius: 6px; overflow: hidden; background: #000; height: 76px; cursor: zoom-in; }
  .photo img { height: 100%; width: auto; max-width: 130px; object-fit: cover; display: block; }
  .photo-big { position: fixed; inset: 0; z-index: 60; background: rgba(0, 0, 0, 0.85); border: 0; border-radius: 0;
               display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; cursor: zoom-out; }
  .photo-big img { max-width: 90vw; max-height: 82vh; border-radius: 6px; box-shadow: 0 6px 30px rgba(0, 0, 0, 0.8); }
  .photo-big span { color: var(--gold-soft); font-size: 0.9rem; }
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
  .sw.heard { background: #e07a5f; width: 6px; height: 6px; border-radius: 50%; }
  b.g { color: var(--gold); }
  .sw.iono { background: #9ad08a; width: 8px; height: 8px; border-radius: 50%; }
  .sw.blue { background: #6eaae6; height: 3px; }
  .sw.green { background: #9ad08a; height: 3px; }
  .sw.dash { background: repeating-linear-gradient(90deg, #e8e2c8 0 4px, transparent 4px 7px); height: 2px; }
  .legend.in { margin: 2px 0 0; gap: 10px; font-size: 0.68rem; }
  .ipt { margin-top: 6px; }
  .ipt + .ipt { border-top: 1px dashed var(--panel-edge); padding-top: 6px; }
  .ipt .lbl b { color: var(--gold-soft); font-weight: 600; }
  .kpis.k5 { margin-top: 4px; }
  .kpis b.g { color: var(--gold); }
  .verdict { margin: 0 0 6px; font-size: 0.84rem; padding: 5px 8px; border-radius: 5px; background: rgba(0, 0, 0, 0.35); }
  .verdict.ok { color: var(--ok); } .verdict.warn { color: var(--warn); } .verdict.bad { color: var(--bad); }
  .es { color: #9ad08a; margin-top: 6px; }
  .mini { float: right; padding: 0 7px; font-size: 0.8rem; line-height: 1.4; }
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
  .kpis div { cursor: help; background: rgba(0, 0, 0, 0.35); border-radius: 5px; padding: 4px 6px; text-align: center; }
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
