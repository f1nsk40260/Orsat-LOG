<script>
  // Météo spatiale NOAA SWPC : en direct sur la page du jour, relevés enregistrés sur les jours passés
  import { api } from './api.js';
  import { kClass, fmtTime } from './util.js';
  import IonoLayers from './IonoLayers.svelte';

  let { day, records = [], flares = [], isToday = false } = $props();

  let live = $state(null);
  async function refresh() { live = await api.spacewx().catch(() => ({ ok: false, msg: 'Serveur injoignable.' })); }
  $effect(() => {
    if (!isToday) { live = null; return; }
    refresh();
    const t = setInterval(refresh, 5 * 60 * 1000);
    return () => clearInterval(t);
  });

  // valeurs affichées : direct (aujourd'hui) ou dernier relevé du jour (archive)
  const last = $derived(records.length ? records[records.length - 1] : null);
  const cur = $derived(isToday && live?.ok ? live : last);
  const shownFlares = $derived(isToday && live?.ok ? live.flares_24h : flares);

  const bzClass = (bz) => (bz == null ? '' : bz <= -10 ? 'bad' : bz <= -5 ? 'warn' : 'ok');
  const windClass = (v) => (v == null ? '' : v >= 600 ? 'bad' : v >= 500 ? 'warn' : 'ok');
  const flareClass = (c) => (c?.[0] === 'X' ? 'bad' : c?.[0] === 'M' ? 'warn' : '');
  const hhmm = (iso) => (iso ? iso.slice(11, 16) : '—');
  const r = (v, d = 0) => (v == null ? '—' : (+v).toFixed(d));

  const TIP_BZ = 'Bz : composante nord-sud du champ magnétique du vent solaire (nT).\n'
    + 'Négative (sud) et durable, elle ouvre la magnétosphère : le Kp monte dans les heures qui suivent,\n'
    + 'les bandes hautes se dégradent, surtout vers le nord. Positive : calme.';
  const TIP_WIND = 'Vitesse du vent solaire (km/s). ~400 calme ; > 500 agité ; > 600 orage probable.';
  const TIP_X = 'Flux X du Soleil (GOES, 0,1–0,8 nm). Une éruption M ou X coupe les bandes HF côté jour\n'
    + 'pendant quelques minutes à une heure (absorption dans la couche D), d\'autant plus que la fréquence est basse.';
  const TIP_KP = 'Kp estimé minute par minute par la NOAA (le Kp officiel arrive toutes les 3 h).';
  const TIP_SCALES = 'Échelles NOAA : R = coupures radio (éruptions), S = tempête de protons\n'
    + '(absorption aux pôles), G = tempête géomagnétique. 0 = rien, 1 mineur … 5 extrême.';

  // couche D mesurée (dlayer.py) : éruption GOES et fmin des ionosondes, sur la page du jour
  const dl = $derived(isToday && live?.ok ? live.dlayer : null);
  const fminSt = $derived(dl?.fmin?.stations ?? []);
  const fminOk = $derived(fminSt.filter((s) => s.factor != null));
  const facClass = (f) => (f == null ? 'muted' : f >= 3 ? 'bad' : f >= 1.5 ? 'warn' : 'ok');
  const fminTip = $derived(fminSt.length
    ? 'Absorption de la couche D mesurée par les ionosondes (fmin, GIRO / ARTIST).\n'
      + 'Facteur = (fmin du moment ÷ fmin habituelle à cette heure)² ; ×1 = normal, il corrige le calcul des bandes.\n\n'
      + fminSt.map((s) => `${s.name} : ${s.factor != null ? '×' + s.factor : '—'}${s.fmin != null ? ` (fmin ${s.fmin} MHz${s.ref ? `, habituelle ${s.ref}` : ''})` : ''}${s.note ? ' — ' + s.note : ''}`).join('\n')
      + (dl.fmin.at ? `\n\nRelevé ${dl.fmin.at}` : '') + (dl.fmin.error ? `\nErreurs : ${dl.fmin.error}` : '')
    : 'Absorption de la couche D mesurée par les ionosondes (fmin) : premier relevé en cours.');

  // frise de Bz sur la journée (relevés enregistrés)
  const W = 290, H = 54, PADL = 18;
  const bzPts = $derived(records.filter((x) => x.bz != null));
  const xOf = (t) => PADL + ((+t.slice(0, 2) + +t.slice(2, 4) / 60) / 24) * (W - PADL - 6);
  const yOf = (bz) => H / 2 - Math.max(-20, Math.min(20, bz)) * (H / 2 - 4) / 20;
  const bzPath = $derived(bzPts.map((x, i) => `${i ? 'L' : 'M'}${xOf(x.time).toFixed(1)},${yOf(x.bz).toFixed(1)}`).join(' '));
  let big = $state(false);   // vue agrandie au centre de la page
</script>

{#if big}<div class="zoom-backdrop" onclick={() => (big = false)} role="presentation"></div>{/if}
<section class="panel sw zoomable" class:big>
  <button class="ghost zoom-btn" onclick={() => (big = !big)} title={big ? 'Fermer' : 'Agrandir'}>{big ? '✕' : '⤢'}</button>
  <h2 class="panel-title">Météo spatiale <span class="count">NOAA</span></h2>
  {#if cur}
    <div class="tiles">
      <div title={TIP_KP}><span>Kp</span><b class={kClass(cur.kp)}>{r(cur.kp, 1)}</b></div>
      <div title={TIP_BZ}><span>Bz nT</span><b class={bzClass(cur.bz)}>{r(cur.bz, 1)}</b></div>
      <div title={TIP_WIND}><span>Vent</span><b class={windClass(cur.speed)}>{r(cur.speed)}</b></div>
      <div title={TIP_X}><span>X</span><b class={flareClass(cur.xray)}>{cur.xray || '—'}</b></div>
    </div>
    {#if cur.scales}
      <div class="scales" title={TIP_SCALES}>
        {#each ['R', 'S', 'G'] as k}
          {@const v = cur.scales[k]?.scale ?? 0}
          <span class:warn={v >= 1 && v < 3} class:bad={v >= 3}>{k}{v}</span>
        {/each}
        <span class="muted">Bt {r(cur.bt, 1)} nT · {r(cur.density, 1)} p/cm³</span>
      </div>
    {/if}
    {#if bzPts.length > 1}
      <svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Bz sur la journée">
        <line x1={PADL} x2={W - 6} y1={H / 2} y2={H / 2} class="zero" />
        <text x={PADL - 4} y="10" class="axis" text-anchor="end">+</text>
        <text x={PADL - 4} y={H - 3} class="axis" text-anchor="end">−</text>
        <path d={bzPath} class="bz" />
        {#each bzPts as x}<circle cx={xOf(x.time)} cy={yOf(x.bz)} r="5" fill="transparent"><title>{fmtTime(x.time)} UTC — Bz {x.bz} nT, Kp {x.kp ?? '—'}, vent {x.speed ?? '—'} km/s</title></circle>{/each}
      </svg>
    {/if}
    <IonoLayers {day} {isToday} />
    {#if dl}
      <div class="dlay" title={fminTip}>
        <span class="lbl">Couche D mesurée</span>
        {#if dl.swf?.haf_mhz}<span class="fl bad" title="Éruption en cours ({dl.swf.class}) : absorption côté jour jusqu'à environ {dl.swf.haf_mhz} MHz (modèle D-RAP de la NOAA), ajoutée au calcul des bandes">éruption {dl.swf.class} · ≤ {dl.swf.haf_mhz} MHz</span>{/if}
        {#if fminOk.length}
          {#each fminOk as s}<span class="fl {facClass(s.factor)}">{s.name} ×{s.factor}</span>{/each}
        {:else}<span class="muted">{fminSt.length ? 'fmin indisponible' : 'premier relevé en cours…'}</span>{/if}
      </div>
    {/if}
    <div class="flares">
      <span class="lbl">Éruptions {isToday ? 'des dernières 24 h' : 'du jour'} (C et plus)</span>
      {#if shownFlares?.length}
        {#each shownFlares as f}
          <span class="fl {flareClass(f.cls)}" title="Début {hhmm(f.begin)} · fin {hhmm(f.end ?? f.finish)} UTC">{f.cls} {hhmm(f.max ?? f.peak ?? f.begin)}</span>
        {/each}
      {:else}<span class="muted">aucune</span>{/if}
    </div>
    <p class="src">NOAA SWPC{isToday && live?.ok ? ` · mesure ${hhmm(live.mag_time)} UTC` : last ? ` · relevé ${fmtTime(last.time)} UTC` : ''}</p>
  {:else}
    <p class="muted">{isToday ? (live && !live.ok ? live.msg : 'Lecture en cours…') : 'Pas de relevé ce jour-là (relevés depuis la v1.14).'}</p>
  {/if}
</section>

<style>
  .sw { display: flex; flex-direction: column; gap: 7px; }
  .count { color: var(--muted); font-weight: 400; margin-left: 8px; text-transform: none; letter-spacing: 0; }
  .tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
  .tiles div { cursor: help; text-align: center; background: rgba(0, 0, 0, 0.3); border-radius: 6px; padding: 5px 2px; }
  .tiles span { display: block; font-size: 0.66rem; color: var(--gold-soft); letter-spacing: 0.08em; text-transform: uppercase; }
  .tiles b { font-size: 1.15rem; color: var(--text); }
  .scales { display: flex; gap: 6px; align-items: center; font-size: 0.8rem; cursor: help; flex-wrap: wrap; }
  .scales span:not(.muted) { border: 1px solid var(--panel-edge); border-radius: 10px; padding: 0 7px; color: var(--ok); }
  .scales span.warn { color: var(--warn); border-color: var(--warn); }
  .scales span.bad { color: var(--bad); border-color: var(--bad); }
  .flares { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; font-size: 0.78rem; }
  .lbl { color: var(--muted); font-size: 0.72rem; width: 100%; }
  .fl { border: 1px solid var(--panel-edge); border-radius: 10px; padding: 0 7px; cursor: help; }
  .dlay { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; font-size: 0.78rem; cursor: help; }
  .chart { width: 100%; height: auto; }
  .zero { stroke: rgba(207, 181, 59, 0.25); stroke-dasharray: 3 3; }
  .bz { fill: none; stroke: var(--gold); stroke-width: 1.6; }
  .axis { fill: var(--muted); font-size: 10px; }
  .src { font-size: 0.7rem; color: var(--muted); margin: 0; }
  .ok { color: var(--ok) !important; } .warn { color: var(--warn) !important; } .bad { color: var(--bad) !important; }
  .muted { color: var(--muted); font-size: 0.8rem; }
  /* vue agrandie */
  .big .tiles span { font-size: 0.9rem; } .big .tiles b { font-size: 1.8rem; }
  .big .scales, .big .flares, .big .dlay { font-size: 1.05rem; }
  .big .lbl, .big .src, .big .muted { font-size: 0.95rem; }
</style>
