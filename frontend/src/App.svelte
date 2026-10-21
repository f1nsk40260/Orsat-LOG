<script>
  import { onMount } from 'svelte';
  import { api, liveSocket } from './api.js';
  import { startTci, stopTci } from './tciBrowser.js';
  import { dayOf, addDays, longDay } from './util.js';
  import HeaderClock from './HeaderClock.svelte';
  import DayPage from './DayPage.svelte';
  import LogBook from './LogBook.svelte';
  import Calendar from './Calendar.svelte';

  let settings = $state({});
  let radio = $state({ connected: false, freq: 0, mode: '', submode: '', ptt: false, device: '' });
  let websdr = $state({ listening: false, connected: false, freq: 0, mode: '', submode: '', ptt: false, device: 'WebSDR' });
  let showCalendar = $state(false);
  let view = $state('day');              // 'day' = page d'agenda, 'log' = carnet complet
  let utc = $state(new Date());
  let today = $state(dayOf());           // jour UTC en cours
  let day = $state(dayOf());             // jour affiché
  let dayPage = $state();

  const isToday = $derived(day === today);

  function openDay(d) {
    day = d > today ? today : d;
    view = 'day';
    showCalendar = false;
  }

  function onKey(e) {
    if (showCalendar) {
      if (e.key === 'Escape') showCalendar = false;
      return;
    }
    if (e.key === 'Escape' && view === 'day') dayPage?.clearForm();
    // Alt+← / Alt+→ : jour précédent / suivant ; Alt+↓ : aujourd'hui ; Alt+C : carnet
    if (e.altKey && view === 'day' && e.key === 'ArrowLeft') openDay(addDays(day, -1));
    if (e.altKey && view === 'day' && e.key === 'ArrowRight' && !isToday) openDay(addDays(day, 1));
    if (e.altKey && e.key === 'ArrowDown') openDay(today);
    if (e.altKey && (e.key === 'c' || e.key === 'C')) view = view === 'log' ? 'day' : 'log';
  }

  // Liaison TCI avec AetherSDR, ouverte par ce navigateur (sur le PC de l'opérateur)
  function browserTci(s) {
    if (s.tci_enabled === '1') {
      let lastF = null, lastM = null;
      startTci({ host: s.tci_host || '127.0.0.1', port: s.tci_port || 50001, trx: s.tci_trx || 0 },
               (st) => {
                 radio = st;
                 // La page WebSDR suit AetherSDR (CAT Sync) sans le relayer au carnet : on le lui dit
                 if (st.connected && (st.freq !== lastF || st.modulation !== lastM)) {
                   if (st.freq) api.websdrMirror(st.freq, st.modulation !== lastM ? st.modulation : '').catch(() => {});
                   lastF = st.freq; lastM = st.modulation;
                 }
               });
    } else {
      stopTci();
    }
  }

  async function logout() {
    await api.logout().catch(() => {});
    location.href = 'login';
  }


  onMount(() => {
    api.settings().then((s) => {
      settings = s;
      browserTci(s);
    });
    const stop = liveSocket((msg) => { if (msg.type === 'websdr') websdr = msg.data; });
    const clock = setInterval(() => {
      utc = new Date();
      const t = dayOf(utc);
      if (t !== today) {             // passage à 00:00 UTC : on tourne la page si on était sur « aujourd'hui »
        const wasToday = day === today;
        today = t;
        if (wasToday) day = t;
      }
    }, 1000);
    return () => { stop(); stopTci(); clearInterval(clock); };
  });
</script>

<svelte:window onkeydown={onKey} />

<header class="topbar">
  <div class="brand">
    <span class="logo">ORSAT</span><span class="logo-sub">-LOG</span>
    {#if settings.callsign}
      <span class="station mono">{settings.callsign}{settings.locator ? ` · ${settings.locator}` : ''}</span>
    {:else if settings.tci_port}
      <span class="station setup" title="Indicatif, locators, TCI et météo se règlent dans le panneau admin du WebSDR">
        À régler : panneau admin → Carnet ORSAT-LOG</span>
    {/if}
  </div>

  <nav class="datenav" class:dim={view !== 'day'}>
    <button class="ghost arrow" onclick={() => openDay(addDays(day, -1))} title="Jour précédent (Alt+←)">◀</button>
    <button class="date" onclick={() => (showCalendar = !showCalendar)} title="Ouvrir le calendrier">
      <span class="date-txt">{longDay(day)}</span>
      {#if isToday}<span class="badge">aujourd'hui</span>{/if}
    </button>
    <button class="ghost arrow" onclick={() => openDay(addDays(day, 1))} disabled={isToday}
            title="Jour suivant (Alt+→)">▶</button>
    {#if !isToday}
      <button class="small" onclick={() => openDay(today)} title="Revenir à la page du jour (Alt+↓)">Aujourd'hui</button>
    {/if}
  </nav>

  <div class="right">
    <HeaderClock />
    <button class:active={view === 'log'} onclick={() => (view = view === 'log' ? 'day' : 'log')}
            title="Ouvrir / fermer le carnet de trafic complet (Alt+C)">
      {view === 'log' ? 'Agenda' : 'Carnet'}
    </button>
    <button onclick={logout} title="Fermer la session du carnet sur ce navigateur">Déconnexion</button>
  </div>
</header>

{#if view === 'day'}
  <DayPage bind:this={dayPage} {day} {isToday} {radio} {websdr} {settings} />
{:else}
  <LogBook onopenday={openDay} />
{/if}

{#if showCalendar}
  <Calendar {day} {today} onpick={openDay} onclose={() => (showCalendar = false)} />
{/if}


<style>
  .topbar {
    display: flex; align-items: center; gap: 20px;
    padding: 10px 18px; height: 62px;
    border-bottom: 1px solid var(--panel-edge);
    /* Bandeau semi-opaque au-dessus du fond d'écran ORSAT, pour la lisibilité */
    background: linear-gradient(180deg, rgba(40, 34, 14, 0.82), rgba(12, 12, 14, 0.78));
    backdrop-filter: blur(6px);
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.55);
    position: relative; z-index: 5;
  }
  .brand { display: flex; align-items: baseline; gap: 4px; white-space: nowrap; }
  .logo { color: var(--gold); font-size: 1.5rem; font-weight: 700; letter-spacing: 0.1em; }
  .logo-sub { color: var(--gold-soft); font-size: 1.1rem; font-weight: 600; }
  .station { margin-left: 14px; color: var(--text); }

  .datenav { display: flex; align-items: center; gap: 6px; margin-left: auto; }
  .datenav.dim { opacity: 0.45; }
  .arrow { font-size: 0.9rem; padding: 4px 8px; }
  .date { display: flex; align-items: center; gap: 10px; padding: 5px 16px; min-width: 300px; justify-content: center; }
  .date-txt { font-size: 1.05rem; font-weight: 600; text-transform: capitalize; }
  .badge { font-size: 0.68rem; color: #1a1606; background: var(--gold); border-radius: 10px; padding: 1px 8px; font-weight: 700; }
  .small { padding: 4px 10px; font-size: 0.82rem; }

  .right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
  button.active { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); font-weight: 600; }
  :global(.ok) { color: var(--ok); } :global(.warn) { color: var(--warn); } :global(.bad) { color: var(--bad); }
  .station.setup { color: var(--warn); font-family: inherit; font-size: 0.82rem; }
</style>
