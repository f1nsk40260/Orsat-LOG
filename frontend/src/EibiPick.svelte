<script>
  // Suggestions de la grille EiBi pour une écoute : qui émet sur cette fréquence à cette heure,
  // depuis quel site. Un clic sur une ligne la retient (onpick).
  import { api } from './api.js';

  let { freq, date = '', time = '', onpick, compact = false } = $props();

  let res = $state(null);
  let busy = $state(false);
  let lastKey = '';

  const LANG = { E: 'anglais', F: 'français', G: 'allemand', S: 'espagnol', R: 'russe', A: 'arabe',
                 P: 'portugais', I: 'italien', J: 'japonais', M: 'mandarin' };
  const lang = (l) => LANG[l] || l || '';

  async function load(key) {
    busy = true;
    try {
      const r = await api.eibi(freq, date, time);
      if (key === lastKey) res = r;
    } catch (err) {
      if (key === lastKey) res = { ok: false, msg: err.message };
    } finally {
      busy = false;
    }
  }

  // Nouvelle recherche quand la fréquence change d'au moins 1 kHz (ou la date / l'heure)
  $effect(() => {
    if (!freq) { res = null; lastKey = ''; return; }
    const key = `${Math.round(freq / 1000)}|${date}|${time}`;
    if (key === lastKey) return;
    lastKey = key;
    const t = setTimeout(() => load(key), 400);
    return () => clearTimeout(t);
  });
</script>

{#if freq}
  <div class="eibi" class:compact>
    <div class="head">
      <b>EiBi</b>
      {#if busy}<span class="muted">recherche…</span>
      {:else if res?.ok}
        <span class="muted">{res.candidates.length ? `${res.candidates.length} station(s) prévue(s) sur ${(freq / 1e3).toFixed(0)} kHz` : `rien de prévu sur ${(freq / 1e3).toFixed(0)} kHz à cette heure`}
          {#if !res.exact_season} · grille {res.season}, pas celle de l’époque{/if}</span>
      {:else if res}<span class="err">{res.msg}</span>{/if}
    </div>
    {#if res?.ok && res.candidates.length}
      <ul>
        {#each res.candidates as c}
          <li>
            <button type="button" onclick={() => onpick?.(c)} title={c.site ? `Retenir : site ${c.site}, locator ${c.locator}` : 'Retenir (site d’émission inconnu de la grille)'}>
              <span class="st">{c.station}</span>
              <span class="muted">{c.khz} kHz · {c.time}{c.days ? ` · ${c.days}` : ''} · {lang(c.lang)}{c.target ? ` → ${c.target}` : ''}</span>
              <span class="site">{c.site ? `${c.site} (${c.site_country}) ${c.locator}` : 'site inconnu'}</span>
              {#if !c.sure}<span class="muted">· horaire irrégulier</span>{/if}
            </button>
          </li>
        {/each}
      </ul>
      <p class="credit">{res.credit}</p>
    {/if}
  </div>
{/if}

<style>
  .eibi { border: 1px dashed var(--panel-edge); border-radius: 6px; padding: 6px 10px; margin-top: 8px; font-size: 0.8rem; }
  .head { display: flex; gap: 8px; align-items: baseline; }
  .head b { color: rgb(110, 170, 230); letter-spacing: 0.08em; }
  ul { list-style: none; margin: 4px 0 0; padding: 0; max-height: 170px; overflow-y: auto; }
  li button { width: 100%; text-align: left; display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline;
              background: transparent; border: 1px solid transparent; padding: 2px 6px; border-radius: 4px; cursor: pointer; color: var(--text); }
  li button:hover { border-color: var(--gold); background: rgba(207, 181, 59, 0.08); }
  .st { color: var(--gold); font-weight: 600; }
  .site { color: rgb(110, 170, 230); }
  .muted { color: var(--muted); }
  .err { color: var(--bad); }
  .credit { margin: 4px 0 0; font-size: 0.68rem; color: var(--muted); }
  .compact ul { max-height: 140px; }
</style>
