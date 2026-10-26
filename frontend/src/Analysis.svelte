<script>
  // Analyse du carnet : distances obtenues selon le Kp, le SFI, l'heure et la direction
  import { api } from './api.js';

  let kind = $state('QSO');
  let band = $state('');
  let data = $state(null);
  let error = $state('');

  $effect(() => {
    const k = kind, b = band;
    error = '';
    if (k === 'QRN') return;
    api.analysis(k, b).then((d) => (data = d)).catch((e) => (error = e.message));
  });

  // bruit de fond d'ORSAT selon la foudre, le Kp et la pression
  let days = $state(90);
  let qrn = $state(null);
  $effect(() => {
    if (kind !== 'QRN') return;
    const d = days;
    error = '';
    api.analysisQrn(d).then((r) => (qrn = r)).catch((e) => (error = e.message));
  });
  const exColor = (e) => {
    if (e == null) return 'transparent';
    const a = Math.min(0.85, Math.abs(e) / 8);
    return e > 0 ? `rgba(214, 80, 80, ${a})` : `rgba(140, 185, 230, ${a})`;
  };

  const km = (v) => (v == null ? '—' : `${v.toLocaleString('fr-FR')}`);
  const maxN = (list) => Math.max(1, ...list.map((x) => x.n));
  const gridMax = $derived(data ? Math.max(1, ...data.band_hour.flatMap((r) => r.hours)) : 1);
  const hourMaxN = $derived(data ? maxN(data.by_hour) : 1);
  const hourMaxKm = $derived(data ? Math.max(1, ...data.by_hour.map((h) => h.median_km || 0)) : 1);
  const heat = (n) => (n ? `rgba(207, 181, 59, ${0.15 + 0.85 * (n / gridMax)})` : 'rgba(255,255,255,0.03)');

  const TABLES = [
    { key: 'by_kp', title: 'Selon le Kp', tip: 'Kp du créneau de 3 h du contact (archive GFZ ou relevé du carnet).' },
    { key: 'by_sfi', title: 'Selon le flux solaire (SFI)', tip: 'Flux solaire à 10,7 cm du jour du contact.' },
    { key: 'by_dir', title: 'Selon la direction', tip: 'Azimut depuis le QTH d\'émission, en 8 secteurs de 45°.' },
  ];
</script>

<div class="an">
  <div class="bar">
    <div class="seg" role="group" aria-label="Type d'entrées">
      <button type="button" class:on={kind === 'QSO'} onclick={() => { kind = 'QSO'; band = ''; }}
              title="Contacts réalisés (QSO et QSO de groupe)">Contacts</button><button
              type="button" class:on={kind === 'SWL'} onclick={() => { kind = 'SWL'; band = ''; }}
              title="Écoutes SWL">Écoutes SWL</button><button
              type="button" class:on={kind === 'QRN'} onclick={() => (kind = 'QRN')}
              title="Bruit de fond mesuré par ORSAT selon la foudre, le Kp et la pression">Bruit / QRN</button>
    </div>
    {#if kind === 'QRN'}
      <div class="seg" role="group" aria-label="Période">
        {#each [[30, '30 j'], [90, '90 j'], [365, '1 an']] as [d, l]}<button type="button" class:on={days === d} onclick={() => (days = d)}>{l}</button>{/each}
      </div>
      {#if qrn}<span class="tot"><b>{qrn.n.toLocaleString('fr-FR')}</b> mesures de bruit · foudre connue pour {qrn.with_storm.toLocaleString('fr-FR')}
        · Kp pour {qrn.with_kp.toLocaleString('fr-FR')} · pression pour {qrn.with_bar.toLocaleString('fr-FR')}</span>{/if}
    {:else}
    <label>Bande
      <select bind:value={band}>
        <option value="">toutes</option>
        {#each data?.bands ?? [] as b}<option value={b}>{b}</option>{/each}
      </select>
    </label>
    {#if data}
      <span class="tot"><b>{data.total.n}</b> entrées · distance connue pour {data.total.with_km} ·
        médiane <b>{km(data.total.median_km)} km</b> · max <b>{km(data.total.max_km)} km</b>
        {#if data.missing_solar}<span class="muted"> · {data.missing_solar} sans indices solaires</span>{/if}</span>
    {/if}
    {/if}
  </div>

  {#if error}<p class="err">{error}</p>{/if}

  {#if kind === 'QRN'}
    {#if qrn && !qrn.n}
      <p class="muted">Pas encore assez de mesures de bruit sur cette période.</p>
    {:else if qrn}
      <p class="muted small">Chaque case : écart moyen du bruit de fond mesuré par ORSAT par rapport à son niveau habituel à la même heure UTC
        (rouge = plus de bruit, bleu = moins). Une case vide = moins d'une heure de mesures. Survolez une case pour le nombre de mesures.</p>
      <div class="cols">
        {#each qrn.tables as t}
          <section class="panel">
            <h2 class="panel-title" title={t.tip}>{t.title}</h2>
            <table>
              <thead><tr><th></th>{#each qrn.bands as b}<th>{b}</th>{/each}</tr></thead>
              <tbody>
                {#each t.rows as r}
                  <tr>
                    <td class="lab">{r.label}</td>
                    {#each r.cells as c}
                      <td class="ex" style="background:{exColor(c.excess)}" title="{c.band} · {r.label} : {c.n} mesure(s)">
                        {c.excess == null ? '' : `${c.excess > 0 ? '+' : ''}${c.excess}`}</td>
                    {/each}
                  </tr>
                {/each}
              </tbody>
            </table>
            <p class="tip">{t.tip}</p>
          </section>
        {/each}
      </div>
    {/if}
  {:else if data}
    <div class="cols">
      {#each TABLES as t}
        {@const list = data[t.key]}
        {@const m = maxN(list)}
        <section class="panel">
          <h2 class="panel-title" title={t.tip}>{t.title}</h2>
          <table>
            <thead><tr><th></th><th>Entrées</th><th>Médiane</th><th>Max</th><th title="Part des distances au-delà de 3000 km">&gt; 3000 km</th></tr></thead>
            <tbody>
              {#each list as r}
                <tr>
                  <td class="lab">{r.label}</td>
                  <td class="n"><i style="width:{(r.n / m) * 60}px"></i>{r.n}</td>
                  <td>{km(r.median_km)}</td>
                  <td>{km(r.max_km)}</td>
                  <td>{r.dx_pct == null ? '—' : `${r.dx_pct} %`}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </section>
      {/each}
    </div>

    <section class="panel">
      <h2 class="panel-title">Selon l'heure UTC <span class="count">barres = nombre d'entrées · ligne = distance médiane</span></h2>
      <svg viewBox="0 0 960 170" preserveAspectRatio="xMidYMid meet" style="max-height:220px" class="chart" role="img" aria-label="Entrées et distance médiane par heure">
        {#each data.by_hour as h}
          {@const x = 30 + h.hour * 38}
          {@const bh = (h.n / hourMaxN) * 120}
          <rect {x} y={140 - bh} width="30" height={bh} rx="2" class="barh">
            <title>{String(h.hour).padStart(2, '0')} h UTC : {h.n} entrée(s), médiane {km(h.median_km)} km, max {km(h.max_km)} km</title>
          </rect>
          <text x={x + 15} y="156" class="axis" text-anchor="middle">{String(h.hour).padStart(2, '0')}</text>
        {/each}
        <path class="med" d={data.by_hour.filter((h) => h.median_km).map((h, i) => `${i ? 'L' : 'M'}${45 + h.hour * 38},${140 - (h.median_km / hourMaxKm) * 120}`).join(' ')} />
        <text x="4" y="16" class="axis">{km(hourMaxKm)} km</text>
      </svg>
    </section>

    {#if data.band_hour.length}
      <section class="panel">
        <h2 class="panel-title">Bande × heure UTC <span class="count">tous types de conditions · plus c'est doré, plus il y a d'entrées</span></h2>
        <table class="heat">
          <thead><tr><th></th>{#each Array(24) as _, h}<th>{String(h).padStart(2, '0')}</th>{/each}</tr></thead>
          <tbody>
            {#each data.band_hour as r}
              <tr>
                <td class="lab">{r.band}</td>
                {#each r.hours as n, h}<td style="background:{heat(n)}" title="{r.band} · {String(h).padStart(2, '0')} h UTC : {n} entrée(s)">{n || ''}</td>{/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {/if}
  {/if}
</div>

<style>
  .an { padding: 14px; display: flex; flex-direction: column; gap: 14px; height: calc(100vh - 62px); overflow-y: auto; }
  .bar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
  label { color: var(--muted); font-size: 0.85rem; display: flex; gap: 6px; align-items: center; }
  .tot { font-size: 0.85rem; background: rgba(0, 0, 0, 0.6); border-radius: 6px; padding: 4px 10px; }
  .tot b { color: var(--gold); }
  .cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th { color: var(--gold-soft); font-weight: 600; text-align: right; padding: 3px 6px; cursor: help; }
  td { text-align: right; padding: 3px 6px; border-top: 1px solid rgba(207, 181, 59, 0.08); }
  td.lab { text-align: left; color: var(--text); }
  td.n { white-space: nowrap; }
  td.n i { display: inline-block; height: 8px; background: var(--gold-soft); border-radius: 2px; margin-right: 6px; vertical-align: 0; }
  .count { color: var(--muted); font-weight: 400; margin-left: 8px; text-transform: none; letter-spacing: 0; font-size: 0.75rem; }
  .chart { width: 100%; height: auto; }
  .barh { fill: var(--gold-soft); }
  .barh:hover { fill: var(--gold); }
  .med { fill: none; stroke: var(--ok); stroke-width: 2; }
  .axis { fill: var(--muted); font-size: 11px; }
  .heat { font-size: 0.72rem; }
  .heat th { text-align: center; padding: 2px; }
  .heat td { text-align: center; padding: 3px 0; color: #111; border: 1px solid rgba(0, 0, 0, 0.4); cursor: help; }
  .heat td.lab { color: var(--text); padding-right: 6px; text-align: left; }
  .muted { color: var(--muted); }
  .seg { display: inline-flex; border: 1px solid rgba(207, 181, 59, 0.6); border-radius: 999px; overflow: hidden; }
  .seg button { border: 0; border-radius: 0; background: rgba(0, 0, 0, 0.3); padding: 5px 14px; }
  .seg button + button { border-left: 1px solid rgba(207, 181, 59, 0.3); }
  .seg button.on { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); font-weight: 600; }
  .err { color: var(--bad); }
  td.ex { text-align: center; cursor: help; }
  .tip { color: var(--muted); font-size: 0.72rem; margin: 6px 0 0; }
  .small { font-size: 0.8rem; margin: 0; }
</style>
