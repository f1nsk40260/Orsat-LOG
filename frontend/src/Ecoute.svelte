<script>
  // Page publique « écoute » : affichable depuis la page du WebSDR (lien ou cadre intégré)
  import SkipMap from './SkipMap.svelte';
  import { TXT, PAGE_LANG } from './ecouteI18n.js';
  const TX = TXT[PAGE_LANG];
  document.documentElement.lang = PAGE_LANG;
  document.title = TX.title;
  let map = $state();
  $effect(() => {
    const t = setInterval(() => map?.refresh(), 15 * 60 * 1000);   // nouvelles mesures toutes les 15 min
    return () => clearInterval(t);
  });
</script>

<main class="ec">
  <section class="panel">
    <h2 class="panel-title">{TX.title}</h2>
    <p class="intro">{TX.intro}</p>
    <SkipMap bind:this={map} publicView />
  </section>
</main>

<style>
  .ec { padding: 14px; max-width: 1200px; margin: 0 auto; }
  .intro { color: var(--text); font-size: 0.9rem; margin: 0 0 10px; }
</style>
