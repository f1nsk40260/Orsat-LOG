<script>
  // Horloge du header, reprise de PhantomSDR-ORSAT (lib/HeaderClock.svelte) : afficheur ambre façon
  // transceiver, bascule TU / LOCAL à la souris ; le choix est commun avec la page du WebSDR
  // (même clé du navigateur, même origine orsat.ddns.net).
  import { onMount } from 'svelte';

  const KEY = 'phantom.clockUtc';
  let utc = $state(true);
  try { if (localStorage.getItem(KEY) === '0') utc = false; } catch (e) {}
  let now = $state(new Date());

  onMount(() => {
    let timer;
    const align = setTimeout(() => {
      now = new Date();
      timer = setInterval(() => (now = new Date()), 1000);
    }, 1000 - new Date().getMilliseconds());
    return () => { clearTimeout(align); clearInterval(timer); };
  });

  function setMode(u) {
    utc = u;
    try { localStorage.setItem(KEY, u ? '1' : '0'); } catch (e) {}
  }

  const p2 = (n) => String(n).padStart(2, '0');
  const h = $derived(utc ? now.getUTCHours() : now.getHours());
  const m = $derived(utc ? now.getUTCMinutes() : now.getMinutes());
  const s = $derived(utc ? now.getUTCSeconds() : now.getSeconds());
  const dateTxt = $derived(utc
    ? `${p2(now.getUTCDate())}/${p2(now.getUTCMonth() + 1)}/${now.getUTCFullYear()}`
    : `${p2(now.getDate())}/${p2(now.getMonth() + 1)}/${now.getFullYear()}`);
</script>

<div class="hclock" role="group" aria-label="Horloge">
  <span class="hclock-face" title={utc ? 'Temps universel (UTC)' : 'Heure locale de votre ordinateur'}>
    <span class="hclock-time">{p2(h)}:{p2(m)}<span class="hclock-sec">:{p2(s)}</span></span>
    <span class="hclock-date">{dateTxt}</span>
  </span>
  <button type="button" class="hclock-btn" class:active={utc} aria-pressed={utc}
          title="Temps universel (UTC)" onclick={() => setMode(true)}>TU</button><button
          type="button" class="hclock-btn" class:active={!utc} aria-pressed={!utc}
          title="Heure locale de votre ordinateur" onclick={() => setMode(false)}>LOCAL</button>
</div>

<style>
  /* Même pastille que le sélecteur de langue : bord vieil or, fond sombre. */
  .hclock {
    display: inline-flex;
    align-items: stretch;
    flex-shrink: 0;
    border: 1px solid rgba(207, 181, 59, 0.6);
    border-radius: 999px;
    overflow: hidden;
    background: rgba(0, 0, 0, 0.3);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
  }
  /* Afficheur façon LED ambre, comme un transceiver. */
  .hclock-face {
    display: inline-flex;
    align-items: baseline;
    gap: 8px;
    padding: 3px 12px 3px 14px;
    background: rgba(0, 0, 0, 0.45);
    border-right: 1px solid rgba(207, 181, 59, 0.35);
    cursor: default;
  }
  .hclock-time {
    font-family: "Courier New", monospace;
    font-variant-numeric: tabular-nums;
    font-weight: 700;
    font-size: 1.05rem;
    letter-spacing: 0.06em;
    color: #ffd166;
    text-shadow:
      0 0 4px rgba(255, 190, 70, 0.55),
      0 0 10px rgba(255, 170, 40, 0.25);
  }
  .hclock-sec {
    opacity: 0.7;
    font-size: 0.85em;
  }
  .hclock-date {
    font-family: "Courier New", monospace;
    font-variant-numeric: tabular-nums;
    font-size: 0.72rem;
    color: rgba(207, 181, 59, 0.8);
  }
  .hclock-btn {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    color: rgba(207, 181, 59, 0.8);
    background: transparent;
    border: 0;
    border-radius: 0;
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease;
  }
  .hclock-btn + .hclock-btn {
    border-left: 1px solid rgba(207, 181, 59, 0.25);
  }
  .hclock-btn:hover {
    background: rgba(207, 181, 59, 0.18);
    color: rgb(230, 205, 90);
  }
  .hclock-btn.active {
    background: rgb(207, 181, 59);
    color: #1a1405;
    cursor: default;
  }
  .hclock-btn:focus-visible {
    outline: 2px solid #fff8d6;
    outline-offset: -2px;
  }
</style>
