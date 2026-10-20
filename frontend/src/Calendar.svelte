<script>
  import { untrack } from 'svelte';
  import { api } from './api.js';
  import { MOIS, pad } from './util.js';

  let { day, today, onpick, onclose } = $props();

  let year = $state(untrack(() => +day.slice(0, 4)));
  let month = $state(untrack(() => +day.slice(4, 6)));   // 1..12
  let activity = $state({});

  const key = $derived(`${year}${pad(month)}`);
  $effect(() => {
    const k = key;
    api.month(k).then((a) => (activity = a)).catch(() => (activity = {}));
  });

  // grille : semaines commençant le lundi
  const cells = $derived.by(() => {
    const first = new Date(Date.UTC(year, month - 1, 1));
    const offset = (first.getUTCDay() + 6) % 7;
    const n = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const out = Array(offset).fill(null);
    for (let d = 1; d <= n; d++) out.push(`${key}${pad(d)}`);
    return out;
  });

  function shift(n) {
    month += n;
    if (month < 1) { month = 12; year--; }
    if (month > 12) { month = 1; year++; }
  }
</script>

<div class="backdrop" onclick={onclose} role="presentation"></div>
<div class="panel cal" role="dialog" aria-label="Calendrier">
  <div class="nav">
    <button class="ghost" onclick={() => shift(-1)} title="Mois précédent">◀</button>
    <b>{MOIS[month - 1]} {year}</b>
    <button class="ghost" onclick={() => shift(1)} title="Mois suivant">▶</button>
  </div>
  <div class="grid">
    {#each ['lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim'] as j}<span class="dow">{j}</span>{/each}
    {#each cells as c}
      {#if c}
        {@const a = activity[c]}
        <button class="d" class:sel={c === day} class:today={c === today} class:future={c > today}
                disabled={c > today} onclick={() => onpick(c)}
                title={a ? `${a.qso} QSO · ${a.swl} SWL${a.note ? ' · note' : ''}` : ''}>
          {+c.slice(6)}
          {#if a}
            <span class="marks">
              {#if a.qso}<i class="m-qso"></i>{/if}
              {#if a.swl}<i class="m-swl"></i>{/if}
              {#if a.note}<i class="m-note"></i>{/if}
            </span>
          {/if}
        </button>
      {:else}
        <span></span>
      {/if}
    {/each}
  </div>
  <div class="legend">
    <span><i class="m-qso"></i>QSO</span><span><i class="m-swl"></i>SWL</span><span><i class="m-note"></i>note</span>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; z-index: 20; }
  .cal { position: fixed; z-index: 21; top: 58px; left: 50%; transform: translateX(-50%); width: 320px;
         background: #1e1d18; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.7); }
  .nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .nav b { color: var(--gold); text-transform: capitalize; }
  .grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
  .dow { text-align: center; font-size: 0.7rem; color: var(--gold-soft); }
  .d { padding: 6px 0 10px; position: relative; font-size: 0.88rem; color: var(--text);
       background: rgba(0, 0, 0, 0.3); border-color: rgba(207, 181, 59, 0.15); }
  .d.today { border-color: var(--gold); color: var(--gold); font-weight: 700; }
  .d.sel { background: linear-gradient(180deg, rgba(207, 181, 59, 0.4), rgba(207, 181, 59, 0.15)); }
  .d.future { opacity: 0.3; }
  .marks { position: absolute; bottom: 2px; left: 0; right: 0; display: flex; justify-content: center; gap: 2px; }
  i { display: inline-block; width: 5px; height: 5px; border-radius: 50%; }
  .m-qso { background: var(--gold); } .m-swl { background: rgb(140, 185, 230); } .m-note { background: var(--text); }
  .legend { display: flex; gap: 12px; justify-content: center; margin-top: 8px; font-size: 0.74rem; color: var(--muted); }
  .legend i { margin-right: 4px; }
</style>
