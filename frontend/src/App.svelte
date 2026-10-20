<script>
  import { onMount } from 'svelte';
  import { api, liveSocket } from './api.js';
  import { pad, dayOf, addDays, longDay, kClass } from './util.js';
  import Settings from './Settings.svelte';
  import DayPage from './DayPage.svelte';
  import LogBook from './LogBook.svelte';
  import Calendar from './Calendar.svelte';

  let settings = $state({});
  let radio = $state({ connected: false, freq: 0, mode: '', submode: '', ptt: false, device: '' });
  let websdr = $state({ listening: false, connected: false, freq: 0, mode: '', submode: '', ptt: false, device: 'WebSDR' });
  let solar = $state(null);
  let showSettings = $state(false);
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
    if (showSettings || showCalendar) {
      if (e.key === 'Escape') { showSettings = false; showCalendar = false; }
      return;
    }
    if (e.key === 'Escape' && view === 'day') dayPage?.clearForm();
    // Alt+← / Alt+→ : jour précédent / suivant ; Alt+↓ : aujourd'hui ; Alt+C : carnet
    if (e.altKey && view === 'day' && e.key === 'ArrowLeft') openDay(addDays(day, -1));
    if (e.altKey && view === 'day' && e.key === 'ArrowRight' && !isToday) openDay(addDays(day, 1));
    if (e.altKey && e.key === 'ArrowDown') openDay(today);
    if (e.altKey && (e.key === 'c' || e.key === 'C')) view = view === 'log' ? 'day' : 'log';
  }

  async function refreshSolar() { solar = await api.solar().catch(() => solar); }

  onMount(() => {
    api.settings().then((s) => {
      settings = s;
      if (!s.callsign || !s.locator) showSettings = true;
    });
    refreshSolar();
    const stop = liveSocket((msg) => { if (msg.type === 'radio') radio = msg.data;
      else if (msg.type === 'websdr') websdr = msg.data; });
    const clock = setInterval(() => {
      utc = new Date();
      const t = dayOf(utc);
      if (t !== today) {             // passage à 00:00 UTC : on tourne la page si on était sur « aujourd'hui »
        const wasToday = day === today;
        today = t;
        if (wasToday) day = t;
      }
    }, 1000);
    const sol = setInterval(refreshSolar, 15 * 60 * 1000);
    return () => { stop(); clearInterval(clock); clearInterval(sol); };
  });
</script>

<svelte:window onkeydown={onKey} />

<header class="topbar">
  <div class="brand">
    <span class="logo">ORSAT</span><span class="logo-sub">-LOG</span>
    {#if settings.callsign}
      <span class="station mono">{settings.callsign}{settings.locator ? ` · ${settings.locator}` : ''}</span>
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

  <div class="solar" title="Données solaires actuelles (hamqsl.com)">
    {#if solar}
      <span>SFI <b>{solar.sfi ?? '—'}</b></span>
      <span>A <b>{solar.a_index ?? '—'}</b></span>
      <span>K <b class={kClass(solar.k_index)}>{solar.k_index ?? '—'}</b></span>
    {/if}
  </div>

  <div class="right">
    <span class="clock mono" title="Heure UTC">{pad(utc.getUTCHours())}:{pad(utc.getUTCMinutes())}:{pad(utc.getUTCSeconds())} UTC</span>
    <button class:active={view === 'log'} onclick={() => (view = view === 'log' ? 'day' : 'log')}
            title="Ouvrir / fermer le carnet de trafic complet (Alt+C)">
      {view === 'log' ? 'Agenda' : 'Carnet'}
    </button>
    <a class="btn" href="/api/export/adif" title="Exporter tout le carnet au format ADIF">ADIF</a>
    <button onclick={() => (showSettings = true)} title="Réglages de la station et de la connexion TCI">Réglages</button>
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

{#if showSettings}
  <Settings {settings} onclose={() => (showSettings = false)}
            onsaved={(s) => { settings = s; showSettings = false; }} />
{/if}

<style>
  .topbar {
    display: flex; align-items: center; gap: 20px;
    padding: 10px 18px; height: 62px;
    border-bottom: 1px solid var(--panel-edge);
    background: linear-gradient(180deg, rgba(207, 181, 59, 0.1), transparent);
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

  .solar { display: flex; gap: 14px; font-size: 0.9rem; color: var(--muted); }
  .solar b { color: var(--text); }
  .right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
  .clock { color: var(--gold); font-size: 1.05rem; margin-right: 6px; }
  button.active { color: #1a1606; background: linear-gradient(180deg, #e2c95a, var(--gold)); font-weight: 600; }
  :global(.ok) { color: var(--ok); } :global(.warn) { color: var(--warn); } :global(.bad) { color: var(--bad); }
</style>
