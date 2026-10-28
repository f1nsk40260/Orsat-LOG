<script>
  // Fenêtre « Trajet d'une onde » : rebond d'une onde HF sur l'ionosphère mesurée en ce moment (raytrace.js)
  import { api } from './api.js';
  import { dayOf, fmtTime } from './util.js';
  import { profile, trace, fan, foMax, layerName, R } from './raytrace.js';
  import { budget, MODES, pct, pCls } from './linkbudget.js';

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

  // ---------- antenne du WebSDR (diagramme NEC) : zone couverte au premier saut ----------
  let showAnt = $state(false);
  let antData = $state(null);
  $effect(() => { if (!antData) api.antenna().then((a) => (antData = a)).catch(() => (antData = { error: true })); });
  const antAll = $derived.by(() => {
    if (!antData?.bands) return null;
    const [name, b] = Object.entries(antData.bands).reduce((a, c) => (Math.abs(c[1].mhz - freq) < Math.abs(a[1].mhz - freq) ? c : a));
    const g = (e) => b.avg[Math.max(0, Math.min(90, Math.round(e)))];
    let gmax = -99, emax = 0;
    for (let e = 1; e <= 89; e++) if (g(e) > gmax) { gmax = g(e); emax = e; }
    return { name, mhz: b.mhz, far: Math.abs(b.mhz - freq) / freq > 0.15, g, gmax, emax };
  });
  const ant = $derived(showAnt ? antAll : null);
  // éventail fin (1°) : chaque angle qui revient pose sa distance de retour au sol
  const fine = $derived(fp2 ? fan(fp2, freq, Array.from({ length: 177 }, (_, i) => 1 + i / 2)).rays.filter((r) => r.ground != null)
    .sort((a, b) => a.ground - b.ground) : []);
  const spans = (list) => list.map((r, i) => ({ ...r,
    d0: i ? (list[i - 1].d + r.d) / 2 : r.d - 15, d1: i < list.length - 1 ? (r.d + list[i + 1].d) / 2 : r.d + 15 }));
  // zone couverte par l'antenne : retours pondérés par le gain de la loop
  const cover = $derived.by(() => {
    if (!antAll || !fine.length) return null;
    const ant = antAll;
    const rays = fine.map((r) => ({ d: r.ground, rel: ant.g(r.el) - ant.gmax, el: r.el }));
    const segs = spans(rays).filter((r) => r.d1 - r.d0 < 400 && r.rel > -10);
    const zone = (lim) => { const z = rays.filter((r) => r.rel >= lim); return z.length ? [z[0].d, z[z.length - 1].d] : null; };
    return { segs, z3: zone(-3), z10: zone(-10) };
  });
  // ---------- bilan de liaison : SNR et chances de réception (linkbudget.js) ----------
  let ctx = $state(null);
  async function loadCtx() { ctx = await api.linkctx().catch(() => null); }
  $effect(() => { loadCtx(); const t = setInterval(loadCtx, 5 * 60 * 1000); return () => clearInterval(t); });
  const POWERS = [5, 10, 25, 50, 100, 200, 400, 800, 1000];
  let pW = $state(100);
  const setP = (d) => { const i = POWERS.indexOf(pW); pW = POWERS[Math.max(0, Math.min(POWERS.length - 1, (i < 0 ? 4 : i) + d))]; };
  let groundMode = $state('SSB');           // ce que montre la bande colorée sur le sol
  const NOISE_BANDS = [['160m', 1.9], ['80m', 3.65], ['60m', 5.36], ['40m', 7.1], ['30m', 10.12], ['20m', 14.2], ['17m', 18.1], ['15m', 21.2], ['12m', 24.94], ['10m', 28.5]];
  const nBand = $derived(NOISE_BANDS.reduce((a, c) => (Math.abs(c[1] - freq) < Math.abs(a[1] - freq) ? c : a))[0]);
  const bud = (r, hops) => budget({ f: freq, elev: r.el ?? elev, len1: r.len, hops, grDbi: antAll ? antAll.g(r.el ?? elev) : 0,
                                     ctx, band: nBand, foF2: iono?.foF2, pW });
  const rayB = $derived(ray?.ground && ray.len ? [1, 2, 3].map((h) => bud({ ...ray, el: elev }, h)) : null);
  // bande des chances sur le sol : tranches de 10 km, chacune prend la meilleure chance des angles qui y
  // retombent (comme on choisirait son angle), puis les tranches voisines de même couleur sont fusionnées
  const chance = $derived.by(() => {
    if (groundMode === 'Antenne' || !fine.length) return [];
    const STEP = 10;
    const list = fine.map((r) => { const b = bud(r, 1); const m = b.modes.find((x) => x.id === groundMode);
                                    return { d: r.ground, el: r.el, p: m.p, snr: m.snr, la: b.la }; });
    const bins = new Map();
    for (const r of spans(list)) {
      if (r.d1 - r.d0 > 400) continue;
      for (let k = Math.floor(r.d0 / STEP); k * STEP < r.d1; k++) {
        const o = bins.get(k);
        if (!o || r.p > o.p) bins.set(k, r);
      }
    }
    const out = [];
    for (const k of [...bins.keys()].sort((x, y) => x - y)) {
      const r = bins.get(k);
      const last = out[out.length - 1];
      if (last && last.d1 === k * STEP && pCls(last.p) === pCls(r.p)) { last.d1 = (k + 1) * STEP; if (r.p > last.p) Object.assign(last, { p: r.p, snr: r.snr, el: r.el, la: r.la, d: r.d }); }
      else out.push({ ...r, d0: k * STEP, d1: (k + 1) * STEP });
    }
    return out;
  });
  // zone avant le 1er saut : distances atteintes par les autres angles de départ (plus hauts), en un saut
  const near = $derived.by(() => {
    if (!rayB || !fine.length) return [];
    const lim = ray.ground;
    const edges = [0, ...[250, 500, 1000, 1500, 2000, 3000].filter((e) => e < lim - 100), lim];
    return edges.slice(0, -1).map((lo, i) => {
      const hi = edges[i + 1];
      const rs = fine.filter((r) => r.ground >= lo && r.ground < hi);
      if (!rs.length) return { lo, hi, silent: true };
      const bs = rs.map((r) => ({ r, b: bud(r, 1) }));
      // pour chaque mode : la meilleure chance dans la tranche, et l'angle qui la donne
      return { lo, hi, modes: MODES.map((m, k) => bs.reduce((a, c) => (c.b.modes[k].p > a.p
        ? { p: c.b.modes[k].p, snr: c.b.modes[k].snr, el: c.r.el, la: c.b.la } : a), { p: -1 })) };
    });
  });
  const modesTxt = (b) => b.modes.slice().reverse().map((m) => `${m.id} ${pct(m.p)}`).join(', ');

  // résumé en phrases simples
  let showHelp = $state(false);
  const summary = $derived.by(() => {
    if (!ray || !fanRes) return [];
    const b = bandOf ? `Sur ${bandOf} (${freq.toFixed(2)} MHz)` : `Sur ${freq.toFixed(2)} MHz`;
    const out = [];
    if (ray.ground) out.push(`${b}, une onde qui part à ${elev}° monte jusqu'à ${Math.round(ray.apex)} km, rebondit sur la couche ${layerName(ray.apex, iono)} et retombe à ${km(ray.ground)} km de IN93LR.`);
    else out.push(`${b}, une onde qui part à ${elev}° traverse l'ionosphère et se perd dans l'espace${muf ? ` : à cet angle, seules les fréquences sous ${muf} MHz reviennent` : ''}. Baissez l'angle ou la fréquence.`);
    if (fanRes.allBack) out.push('Tous les angles reviennent : pas de zone de silence, cette fréquence sert aussi bien pour le proche que pour le lointain.');
    else if (fanRes.skip != null) out.push(`Personne entre 0 et ${km(fanRes.skip)} km ne reçoit l'onde réfléchie (zone de silence) ; un seul saut porte au plus à ${km(fanRes.maxHop)} km.`);
    else out.push('Aucun angle ne revient : la fréquence est au-dessus de ce que l\'ionosphère réfléchit en ce moment.');
    if (near.length) {
      const k = MODES.findIndex((m) => m.id === (groundMode === 'Antenne' ? 'SSB' : groundMode));
      out.push(`Plus près, avec des angles de départ plus hauts, en ${MODES[k].id} : `
        + near.map((z) => `${km(z.lo)} à ${km(z.hi)} km ${z.silent ? 'zone de silence' : pct(z.modes[k].p)}`).join(' · ') + '.');
    }
    if (rayB) out.push(`Chances de réception à ${km(ray.ground)} km avec ${pW} W : ${modesTxt(rayB[0])} (SNR en SSB ≈ ${Math.round(rayB[0].modes[0].snr)} dB, absorption de la couche D ${rayB[0].la.toFixed(1)} dB). Au 2e saut (${km(2 * ray.ground)} km) : ${modesTxt(rayB[1])}.`);
    if (ant) {
      const rel = ant.gmax - ant.g(elev);
      out.push(`La loop du WebSDR rayonne surtout vers ${ant.emax}°${ant.emax >= 50 ? ' (presque vers le haut : antenne de proximité)' : ant.emax <= 20 ? ' (angle bas : bonne pour le lointain)' : ''}`
        + (cover?.z3 ? ` : elle couvre le mieux de ${km(cover.z3[0])} à ${km(cover.z3[1])} km` : ' : aucun retour au sol dans son lobe principal à cette fréquence')
        + `. À ${elev}°, elle est ${rel < 0.5 ? 'à son maximum' : `${rel.toFixed(0)} dB sous son maximum${rel >= 10 ? ' (très peu efficace)' : rel >= 6 ? ' (peu efficace)' : ''}`}.`);
    }
    return out;
  });
  const relCls = (rel) => (rel >= -3 ? 'g3' : rel >= -6 ? 'g6' : 'g10');

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

  // lobe de l'antenne dessiné au point de départ (champ relatif, échelle linéaire)
  const lobe = $derived.by(() => {
    if (!ant) return '';
    const [ox, oy] = P(0, 0).map(Number), [tx, ty] = P(200 / R, 0).map(Number), [ux, uy] = P(0, 60).map(Number);
    const tn = Math.hypot(tx - ox, ty - oy), un = Math.hypot(ux - ox, uy - oy);
    const t = [(tx - ox) / tn, (ty - oy) / tn], u = [(ux - ox) / un, (uy - oy) / un], L = Math.min(150, H * 0.45);
    let d = `M${ox},${oy}`;
    for (let e = 0; e <= 90; e += 2) {
      const r = L * Math.pow(10, (Math.max(-30, ant.g(e) - ant.gmax)) / 20), a = (e * Math.PI) / 180;
      d += ` L${(ox + r * (Math.cos(a) * t[0] + Math.sin(a) * u[0])).toFixed(1)},${(oy + r * (Math.cos(a) * t[1] + Math.sin(a) * u[1])).toFixed(1)}`;
    }
    return d + ' Z';
  });
  // ---------- zoom (molette sur le dessin, centré sur la souris) et déplacement (glisser) ----------
  let vb = $state(null);                       // [x, y, largeur, hauteur] ; null = vue entière
  const zoom = $derived(vb ? W / vb[2] : 1);
  const view = $derived(vb ?? [0, 0, W, H]);
  function zoomAt(fx, fy, k) {                 // fx, fy : position relative (0-1) dans le dessin
    const [x, y, w, h] = view;
    const nw = Math.max(W / 12, Math.min(W, w / k)), nh = nw * H / W;
    if (nw >= W - 0.5) { vb = null; return; }
    const nx = Math.max(0, Math.min(W - nw, x + fx * w - fx * nw)), ny = Math.max(0, Math.min(H - nh, y + fy * h - fy * nh));
    vb = [nx, ny, nw, nh];
  }
  function zoomable(node) {
    let drag = null;
    const wh = (e) => {
      e.preventDefault();
      const r = node.getBoundingClientRect();
      zoomAt((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height, e.deltaY < 0 ? 1.25 : 0.8);
    };
    const down = (e) => { if (!vb) return; drag = { x: e.clientX, y: e.clientY, v: [...vb] }; node.setPointerCapture(e.pointerId); };
    const move = (e) => {
      if (!drag) return;
      const r = node.getBoundingClientRect(), [x, y, w, h] = drag.v;
      vb = [Math.max(0, Math.min(W - w, x - (e.clientX - drag.x) * w / r.width)),
            Math.max(0, Math.min(H - h, y - (e.clientY - drag.y) * h / r.height)), w, h];
    };
    const up = () => (drag = null);
    node.addEventListener('wheel', wh, { passive: false });
    node.addEventListener('pointerdown', down); node.addEventListener('pointermove', move);
    node.addEventListener('pointerup', up); node.addEventListener('pointercancel', up);
    return { destroy() { node.removeEventListener('wheel', wh); node.removeEventListener('pointerdown', down);
      node.removeEventListener('pointermove', move); node.removeEventListener('pointerup', up); node.removeEventListener('pointercancel', up); } };
  }

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
    // pas des graduations adapté à la portion visible : une dizaine de repères à l'écran
    const vis = dMax / zoom;
    const st = [50, 100, 250, 500, 1000].find((x) => vis / x <= 12) ?? 1000;
    return Array.from({ length: Math.floor(dMax / st) + 1 }, (_, i) => i * st);
  });
  const hops = $derived(ray?.ground ? Array.from({ length: HOPS }, (_, k) => k) : [0]);
  const km = (v) => Math.round(v).toLocaleString('fr-FR');
</script>

<div class="backdrop" onclick={onclose} role="presentation"></div>
<section class="panel tr">
  <h2 class="panel-title">Trajet d'une onde depuis {locator}
    <button class="ghost helpbtn" class:on={showHelp} onclick={() => (showHelp = !showHelp)} title="Comment lire cette fenêtre">? Aide</button>
    <button class="ghost close" onclick={onclose} title="Fermer">✕</button></h2>

  {#if !iono}
    <p class="muted">{data ? (data.msg || 'Pas de mesure d\'ionosonde aujourd\'hui.') : 'Lecture de l\'ionosonde…'}</p>
  {:else}
    {#if showHelp}
      <div class="help">
        <h3>Ce que montre le dessin</h3>
        <p>Une coupe de la Terre vue de côté : IN93LR est le point doré à gauche, le sol est la ligne verte, l'ionosphère
          est la bande dorée au-dessus (D, E, F1, F2 à droite = nom des couches à leur altitude). Les hauteurs sont
          exagérées pour que les couches restent visibles.</p>
        <p>La ligne <b class="o">orange</b> est votre onde : elle part avec l'angle choisi, se courbe dans l'ionosphère,
          retombe au sol, rebondit et repart (3 sauts). Les fines lignes claires sont tous les autres angles de départ
          (de 1° à 88°) : on voit d'un coup d'œil lesquels reviennent et lesquels s'échappent (lignes grises qui sortent en haut).</p>
        <h3>Les réglages</h3>
        <p><b>Fréquence</b> : une bande, puis − / + ou la molette pour affiner. <b>Angle de départ</b> : 1° = presque
          à l'horizontale (DX), 90° = droit vers le haut (NVIS). <b>Mesure</b> : rejouer une autre heure de la journée.</p>
        <h3>Ce qu'il faut retenir</h3>
        <p>Plus la fréquence monte, plus l'onde a du mal à revenir : elle doit partir bas, et la <b>zone de silence</b>
          s'agrandit. Si la fréquence dépasse la <b>MUF</b>, l'onde traverse. Plus l'angle est bas, plus le saut est long.</p>
        <h3>Chances de réception</h3>
        <p>Pour chaque distance, le carnet fait le bilan : puissance en face (réglable, dipôle supposé), affaiblissement
          sur la longueur du trajet, <b>absorption de la couche D</b> (plus forte de jour, sur les bandes basses et pour
          les angles bas, corrigée par la mesure des ionosondes), gain de la loop du WebSDR, et bruit de fond (modèle
          de zone rurale, relevé si ORSAT mesure en ce moment plus de bruit que d'habitude). Il en tire le rapport
          signal/bruit (SNR) et le compare au seuil de chaque mode : SSB +10 dB, CW 0 dB, FT8 −21 dB, WSPR −28 dB.
          Comme le signal fluctue (fading), le résultat est une <b>chance en %</b>. La bande colorée sur le sol montre
          ces chances pour le mode choisi : <b class="g">vert</b> ≥ 90 %, ambre 50 à 90 %, rouge 10 à 50 %.
          Ce sont des ordres de grandeur, à quelques dB près.</p>
        <h3>Antenne du WebSDR</h3>
        <p>Le lobe bleu montre dans quels angles la loop rayonne (et donc écoute) le mieux. Sur le sol, le <b class="g">vert</b>
          marque les distances atteintes par ses meilleurs angles : c'est la zone qu'elle couvre le mieux au premier saut ;
          l'ambre, une couverture plus faible. Une loop basse rayonne surtout vers le haut : elle favorise le proche.</p>
        <p class="muted">Calcul : tracé de rayons dans l'ionosphère reconstruite à partir de l'ionosonde ({data.station}).
          Ionosphère supposée la même partout, sans champ magnétique ni absorption : c'est la géométrie du saut,
          pas une garantie de liaison.</p>
      </div>
    {/if}
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
        <button type="button" class="antbtn" class:on={showAnt} onclick={() => (showAnt = !showAnt)}
                title="Diagramme réel (NEC) de la loop du WebSDR : lobe au départ et zone couverte au sol au premier saut">📡 Antenne du WebSDR</button>
      </div>
      <div class="grp">
        <span class="lab">Puissance en face</span>
        <div class="val" use:wheel={setP} title="Puissance de la station émettrice (molette)">
          <button type="button" onclick={() => setP(-1)}>−</button>
          <b>{pW} W</b>
          <button type="button" onclick={() => setP(1)}>+</button>
        </div>
        <span class="lab">Sol colorié selon</span>
        <div class="bands">
          {#each [...MODES.map((m) => m.id), 'Antenne'] as m}
            <button type="button" class:on={groundMode === m} onclick={() => (groundMode = m)}
                    title={m === 'Antenne' ? 'Zone couverte par la loop du WebSDR (gain NEC)' : `Chances de recevoir en ${m} selon la distance`}>{m}</button>
          {/each}
        </div>
      </div>
    </div>

    <div class="wrap" bind:clientWidth={cw}>
      <div class="zoombar">
        <button type="button" onclick={() => zoomAt(0.5, 0.5, 1.5)} title="Zoomer (ou molette sur le dessin)">＋</button>
        <button type="button" onclick={() => zoomAt(0.5, 0.5, 1 / 1.5)} disabled={!vb} title="Dézoomer">−</button>
        <button type="button" onclick={() => (vb = null)} disabled={!vb} title="Revenir à la vue entière">⟲ Vue entière</button>
        <span>{vb ? `zoom ×${zoom.toFixed(1)} · glisser pour se déplacer` : 'molette sur le dessin pour zoomer'}</span>
      </div>
      <svg use:zoomable class:zoomed={!!vb} width={W} height={H} viewBox={view.join(' ')} style="--z: {zoom}"
           role="img" aria-label="Coupe de l'ionosphère et trajet de l'onde">
        {#each strata as s}<path d={band(s.h, s.h + 6)} class="iono" style="opacity: {s.o}" />{/each}
        {#each [100, 200, 300, 400] as h}
          <path d={arc(h)} class="alt" />
          <text x={P(0, h)[0] - 4 / zoom} y={+P(0, h)[1] + 3 / zoom} class="axis" text-anchor="end">{h}</text>
        {/each}
        <text x={P(0, 470)[0] - 4 / zoom} y={+P(0, 470)[1] + 3 / zoom} class="axis" text-anchor="end">km</text>
        <!-- nom des couches, au bord droit, à leur altitude mesurée -->
        {#each [['D', 50, true], ['E', (iono.hmE || 110) + 12, iono.foE || iono.foEs], ['F1', iono.hmF1 || 200, iono.foF1], ['F2', iono.hmF2 || 300, iono.foF2]] as [n, h, on]}
          {#if on}<text x={+P(geo.span, h)[0] + 4 / zoom} y={+P(geo.span, h)[1] + 4 / zoom} class="lay">{n}</text>{/if}
        {/each}
        <!-- éventail : tous les angles, en léger -->
        {#each fanRes.rays as r}<path d={path(r.pts)} class="fan" class:out={r.ground == null} />{/each}
        <!-- zone de silence -->
        {#if fanRes.skip && fanRes.skip > 60 && !fanRes.allBack}
          <path d={Array.from({ length: 31 }, (_, i) => `${i ? 'L' : 'M'}${P((i / 30) * (fanRes.skip / R), 0).join(',')}`).join(' ')} class="skip" />
        {/if}
        <path d={arc(0)} class="ground" />
        {#each chance as c}<path d={Array.from({ length: 9 }, (_, i) => `${i ? 'L' : 'M'}${P((c.d0 + (i / 8) * (c.d1 - c.d0)) / R, 0).join(',')}`).join(' ')} class="chbg" />{/each}
        {#each chance as c}
          <path d={Array.from({ length: 5 }, (_, i) => `${i ? 'L' : 'M'}${P((c.d0 + (i / 4) * (c.d1 - c.d0)) / R, 0).join(',')}`).join(' ')}
                class="ch {pCls(c.p)}"><title>{km(c.d0)} à {km(c.d1)} km · meilleur angle {c.el}° · {groundMode} : {pct(c.p)} (SNR ≈ {Math.round(c.snr)} dB) · absorption D {c.la.toFixed(1)} dB</title></path>
        {/each}
        {#if cover && groundMode === 'Antenne'}
          {#each cover.segs as c}
            <path d={Array.from({ length: 5 }, (_, i) => `${i ? 'L' : 'M'}${P((c.d0 + (i / 4) * (c.d1 - c.d0)) / R, 0).join(',')}`).join(' ')}
                  class="cov {relCls(c.rel)}"><title>{km(c.d)} km · départ à {c.el}° · {c.rel.toFixed(1)} dB / maxi</title></path>
          {/each}
        {/if}
        {#if lobe}<path d={lobe} class="lobe" />{/if}
        {#each kmTicks as d}
          <text x={P(d / R, 0)[0]} y={+P(d / R, 0)[1] + 22 / zoom} class="kmt" text-anchor={d === 0 ? 'start' : 'middle'}>{d ? km(d) : '0 km'}</text>
        {/each}
        <!-- rayon choisi, répété sur 3 sauts -->
        {#each hops as k}<path d={path(ray.pts, k * (ray.ground ?? 0) / R)} class="ray" style="opacity: {1 - k * 0.25}" />{/each}
        {#if ray.ground}
          {#each hops as k}
            {@const [x, y] = P((k + 1) * ray.ground / R, 0)}
            {@const pm = rayB && groundMode !== 'Antenne' ? rayB[k].modes.find((m) => m.id === groundMode).p : null}
            <circle cx={x} cy={y} r={5 / zoom} class="land {pm != null ? pCls(pm) : ''}"><title>{rayB ? `${km((k + 1) * ray.ground)} km : ${modesTxt(rayB[k])}` : ''}</title></circle>
            <text x={x} y={+y - 8 / zoom} class="lt" text-anchor="middle">{km((k + 1) * ray.ground)} km</text>
          {/each}
        {/if}
        <circle cx={P(0, 0)[0]} cy={P(0, 0)[1]} r={4 / zoom} class="me" />
      </svg>
    </div>
    <div class="legend">
      <span><i class="k-ray"></i>votre onde (angle choisi), sur 3 sauts</span>
      <span><i class="k-fan"></i>les autres angles</span>
      <span><i class="k-out"></i>angles qui traversent</span>
      {#if fanRes.skip && !fanRes.allBack}<span><i class="k-skip"></i>zone de silence</span>{/if}
      <span><i class="k-iono"></i>ionosphère (plus c'est doré, plus elle est dense)</span>
      {#if ant}<span><i class="k-lobe"></i>lobe de la loop</span>{/if}
      {#if groundMode === 'Antenne'}<span><i class="k-cov"></i>bien couvert par la loop</span><span><i class="k-cov2"></i>couvert moins bien</span>
      {:else}<span class="lgm">chances en {groundMode} :</span><span><i class="ch-p9"></i>≥ 90 %</span><span><i class="ch-p5"></i>50 à 90 %</span><span><i class="ch-p1"></i>10 à 50 %</span><span><i class="ch-p0"></i>moins de 10 %</span>{/if}
    </div>
    <div class="summary">{#each summary as l}<p>{l}</p>{/each}</div>
    {#if rayB}
      <table class="chances" title="Probabilité que le signal dépasse le seuil du mode, compte tenu des variations (fading) d'environ ±7 dB">
        <thead><tr><th>Chances de réception · {pW} W, dipôle en face</th>
          {#each near as z}<th class="nr" title="Distances avant le 1er saut, atteintes par d'autres angles de départ (plus hauts) : meilleure chance de la tranche">{km(z.lo)}–{km(z.hi)} km<br><small>plus près</small></th>{/each}
          {#each rayB as _, k}<th>{k + 1}{k ? 'e' : 'er'} saut · {km((k + 1) * ray.ground)} km</th>{/each}</tr></thead>
        <tbody>
          {#each MODES as m, i}
            <tr><td>{m.label} <small>(seuil {m.req > 0 ? '+' : ''}{m.req} dB en {m.bw} Hz)</small></td>
              {#each near as z}{#if z.silent}<td class="sil" title="Aucun angle ne retombe ici : zone de silence (seule l'onde de sol, sur quelques dizaines de km)">silence</td>
                {:else}<td class="nr {pCls(z.modes[i].p)}" title="Meilleur angle {z.modes[i].el}° · SNR {z.modes[i].snr.toFixed(1)} dB en {m.bw} Hz · absorption D {z.modes[i].la.toFixed(1)} dB">{pct(z.modes[i].p)}</td>{/if}{/each}
              {#each rayB as b}<td class={pCls(b.modes[i].p)} title="SNR estimé {b.modes[i].snr.toFixed(1)} dB en {m.bw} Hz">{pct(b.modes[i].p)}</td>{/each}</tr>
          {/each}
          <tr class="det"><td>Absorption de la couche D</td>{#each near as z}<td class="nr">{z.silent ? '' : `${Math.min(...z.modes.map((m) => m.la)).toFixed(1)} dB`}</td>{/each}{#each rayB as b}<td>{b.la.toFixed(1)} dB</td>{/each}</tr>
          <tr class="det"><td>Affaiblissement de trajet</td>{#each near as z}<td class="nr"></td>{/each}{#each rayB as b}<td>{b.lbf.toFixed(0)} dB</td>{/each}</tr>
        </tbody>
      </table>
      <p class="src">Bruit : modèle UIT-R P.372 (zone rurale){ctx?.noise?.[nBand] != null ? `, corrigé du bruit mesuré par ORSAT sur ${nBand} (${ctx.noise[nBand] > 0 ? '+' : ''}${ctx.noise[nBand]} dB par rapport à l'habitude)` : ''}.
        Absorption D : modèle George & Bradley{ctx ? ` (Soleil à ${Math.round(90 - ctx.chi)}° au-dessus de l'horizon, facteur mesuré ×${ctx.dfactor}${ctx.flare ? `, éruption ${ctx.flare}` : ''})` : ''}.
        Réception sur la loop du WebSDR (gain NEC), émission sur un dipôle (+2 dBi), 9 dB de pertes diverses, 3 dB par rebond au sol.</p>
    {/if}

    <div class="res">
      {#if ray.ground}
        <div title="Distance où l'onde revient sur Terre après un rebond : c'est là qu'on l'entend."><span>Retour au sol (1er saut)</span><b class="big">{km(ray.ground)} km</b></div>
        <div title="Couche qui renvoie l'onde et altitude la plus haute atteinte. E : vers 100 km, de jour. F2 : 200 à 400 km, fait le DX."><span>Réfléchie par la couche</span><b>{layerName(ray.apex, iono)} · à {Math.round(ray.apex)} km</b></div>
        <div title="L'onde rebondit sur le sol et repart : chaque saut ajoute la même distance (même ionosphère supposée partout)."><span>2e et 3e sauts</span><b>{km(2 * ray.ground)} km · {km(3 * ray.ground)} km</b></div>
      {:else}
        <div><span>À {elev}°, sur {freq.toFixed(2)} MHz</span><b class="bad">l'onde traverse l'ionosphère : pas de retour</b></div>
      {/if}
      {#if ant}
        <div title="Gain de la loop du WebSDR (NEC) à l'angle choisi, et son meilleur angle. dBi : gain par rapport à une antenne idéale qui rayonne pareil partout."><span>Antenne ({ant.name}{ant.far ? ', bande calculée la plus proche' : ''})</span>
          <b>{ant.g(elev).toFixed(1)} dBi à {elev}° · maxi {ant.gmax.toFixed(1)} dBi à {ant.emax}°</b></div>
        <div title="Distances atteintes par les angles où la loop rayonne presque au maximum (moins de 3 dB de perte)."><span>Zone couverte (≤ 3 dB du maxi)</span><b class="g3t">{cover?.z3 ? `${km(cover.z3[0])} à ${km(cover.z3[1])} km` : 'aucune au 1er saut'}</b></div>
        <div title="Distances atteintes avec au plus 10 dB de perte par rapport au meilleur angle de la loop."><span>Zone couverte (≤ 10 dB du maxi)</span><b class="g6t">{cover?.z10 ? `${km(cover.z10[0])} à ${km(cover.z10[1])} km` : 'aucune au 1er saut'}</b></div>
      {:else if showAnt}<div><span>Antenne</span><b>{antData?.error ? 'diagramme indisponible' : 'lecture…'}</b></div>{/if}
      <div title="Fréquence maximale utilisable à cet angle : au-dessus, l'onde traverse l'ionosphère."><span>MUF pour {elev}°</span><b>{muf != null ? `${muf} MHz` : '—'}</b></div>
      <div title="Distances où personne ne reçoit l'onde réfléchie : trop près pour le saut, trop loin pour l'onde de sol."><span>Zone de silence</span>
        <b>{fanRes.allBack ? 'aucune (tous les angles reviennent)' : fanRes.skip != null ? `0 à ${km(fanRes.skip)} km` : 'totale : la fréquence passe à travers'}</b></div>
      <div title="Distance la plus longue atteinte en un seul rebond (onde partie presque à l'horizontale)."><span>Portée maxi d'un saut</span><b>{fanRes.maxHop != null ? `${km(fanRes.maxHop)} km` : '—'}</b></div>
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
  .close { margin-left: 10px; padding: 1px 12px; font-size: 1.5rem; line-height: 1.2; }
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
  svg { display: block; cursor: zoom-in; touch-action: none; }
  svg.zoomed { cursor: grab; }
  svg.zoomed:active { cursor: grabbing; }
  svg :global(path), svg :global(circle) { vector-effect: non-scaling-stroke; }
  .zoombar { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
  .zoombar button { padding: 2px 12px; font-size: 1.15rem; line-height: 1.2; }
  .zoombar span { color: var(--muted); font-size: 0.85rem; margin-left: 6px; }
  .iono { fill: rgb(207, 181, 59); }
  .alt { fill: none; stroke: rgba(207, 181, 59, 0.15); stroke-dasharray: 3 4; }
  .axis { fill: rgb(200, 190, 160); font-size: calc(11px / var(--z)); }
  /* distances au sol : clair et cerné de noir, lisible sur la bande colorée comme sur le fond */
  .kmt { fill: rgb(255, 245, 215); font-size: calc(12.5px / var(--z)); font-weight: 600; paint-order: stroke;
         stroke: rgba(0, 0, 0, 0.9); stroke-width: calc(3.5px / var(--z)); stroke-linejoin: round; }
  .ground { fill: none; stroke: rgb(120, 160, 90); stroke-width: 2; }
  .skip { fill: none; stroke: rgb(200, 200, 210); stroke-width: 5; stroke-dasharray: 6 5; opacity: 0.8; }
  .fan { fill: none; stroke: rgba(240, 225, 170, 0.22); stroke-width: 1; }
  .fan.out { stroke: rgba(160, 160, 160, 0.14); }
  .helpbtn { margin-left: auto; padding: 2px 12px; font-size: 1rem; text-transform: none; letter-spacing: 0; }
  .helpbtn + .close { margin-left: 10px; }
  .helpbtn.on { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); }
  .help { border: 1px solid var(--panel-edge); border-radius: 8px; padding: 8px 14px; background: rgba(0, 0, 0, 0.35);
          font-size: 0.95rem; line-height: 1.45; }
  .help h3 { color: var(--gold); font-size: 0.85rem; letter-spacing: 0.08em; text-transform: uppercase; margin: 8px 0 2px; }
  .help p { margin: 2px 0 6px; }
  .help b.o { color: rgb(255, 120, 60); } .help b.g { color: rgb(110, 220, 120); }
  .lay { fill: var(--gold); font-size: calc(13px / var(--z)); font-weight: 700; }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 0.85rem; color: var(--text); }
  .legend i { display: inline-block; width: 18px; height: 6px; margin-right: 6px; vertical-align: 3px; border-radius: 2px; }
  .k-ray { background: rgb(255, 120, 60); } .k-fan { background: rgba(240, 225, 170, 0.5); } .k-out { background: rgba(160, 160, 160, 0.4); }
  .k-skip { background: repeating-linear-gradient(90deg, rgb(200, 200, 210) 0 5px, transparent 5px 9px); } .k-iono { background: rgba(207, 181, 59, 0.6); height: 10px !important; vertical-align: -1px !important; }
  .k-lobe { background: rgba(90, 200, 220, 0.6); border: 1px solid rgb(90, 200, 220); height: 8px !important; vertical-align: 0 !important; }
  .k-cov { background: rgb(95, 210, 110); } .k-cov2 { background: rgba(224, 180, 60, 0.7); }
  .chbg { fill: none; stroke: #000; stroke-width: 13; stroke-linecap: butt; opacity: 0.85; }
  .ch { fill: none; stroke-width: 9; stroke-linecap: butt; }
  .ch.p9 { stroke: rgb(40, 255, 90); } .ch.p5 { stroke: rgb(255, 205, 0); } .ch.p1 { stroke: rgb(255, 55, 55); } .ch.p0 { stroke: rgb(95, 95, 105); }
  .land.p9 { fill: rgb(95, 210, 110); } .land.p5 { fill: rgb(224, 180, 60); } .land.p1, .land.p0 { fill: rgb(214, 80, 80); }
  .ch-p9 { background: rgb(40, 255, 90); } .ch-p5 { background: rgb(255, 205, 0); } .ch-p1 { background: rgb(255, 55, 55); } .ch-p0 { background: rgb(95, 95, 105); }
  .lgm { color: var(--muted); }
  .chances { width: 100%; border-collapse: collapse; font-size: 0.95rem; cursor: help; }
  .chances th { color: var(--gold-soft); font-weight: 500; text-align: center; padding: 3px 6px; font-size: 0.85rem; }
  .chances th:first-child, .chances td:first-child { text-align: left; }
  .chances td { padding: 3px 6px; text-align: center; border-top: 1px solid rgba(207, 181, 59, 0.08); }
  .chances td small { color: var(--muted); }
  .chances td.p9 { color: rgb(110, 220, 120); font-weight: 700; } .chances td.p5 { color: rgb(230, 190, 70); font-weight: 600; }
  .chances td.p1 { color: rgb(224, 110, 90); } .chances td.p0 { color: var(--muted); }
  .chances th.nr { color: var(--muted); } .chances th small { font-size: 0.75rem; text-transform: none; }
  .chances td.nr { background: rgba(255, 255, 255, 0.02); }
  .chances td.sil { color: var(--bad); font-size: 0.85rem; background: rgba(214, 80, 80, 0.06); }
  .chances tr.det td { color: var(--muted); font-size: 0.85rem; }
  .summary { border-left: 3px solid var(--gold); padding: 4px 12px; background: rgba(207, 181, 59, 0.06); font-size: 1rem; line-height: 1.45; }
  .summary p { margin: 2px 0; }
  .res div[title] { cursor: help; }
  .antbtn { padding: 4px 12px; font-size: 0.95rem; }
  .antbtn.on { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); font-weight: 600; }
  .lobe { fill: rgba(90, 200, 220, 0.18); stroke: rgb(90, 200, 220); stroke-width: 1.5; }
  .cov { fill: none; stroke-width: 7; stroke-linecap: butt; }
  .cov.g3 { stroke: rgb(95, 210, 110); } .cov.g6 { stroke: rgba(95, 210, 110, 0.5); } .cov.g10 { stroke: rgba(224, 180, 60, 0.45); }
  .g3t { color: rgb(110, 220, 120); } .g6t { color: rgb(200, 210, 120); }
  .ray { fill: none; stroke: rgb(255, 120, 60); stroke-width: 2.2; stroke-linejoin: round; }
  .land { fill: rgb(255, 120, 60); stroke: #000; stroke-width: 1; }
  .me { fill: var(--gold); stroke: #000; stroke-width: 1; }
  .lt { fill: var(--text); font-size: calc(12px / var(--z)); font-weight: 600; paint-order: stroke; stroke: rgba(0, 0, 0, 0.7); stroke-width: calc(3px / var(--z)); }
  .res { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 4px 20px; font-size: 0.95rem; }
  .res div { display: flex; justify-content: space-between; gap: 10px; border-bottom: 1px solid rgba(207, 181, 59, 0.08); padding: 2px 0; }
  .res span { color: var(--muted); }
  .res b { font-weight: 500; text-align: right; }
  .res b.big { color: rgb(255, 140, 80); font-size: 1.15rem; font-weight: 700; }
  .res b.bad { color: var(--warn); }
  .src { font-size: 0.75rem; color: var(--muted); margin: 0; }
  .muted { color: var(--muted); }
</style>
