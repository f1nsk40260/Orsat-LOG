<script>
  // Carte des stations décodées par l'autorun du WebSDR un jour donné, filtrable par bande et
  // par heure (choix faits à la souris dans la grille). Une heure choisie : ligne grise et nuit
  // dessinées au milieu de cette heure.
  import { onMount, onDestroy } from 'svelte';
  import L from 'leaflet';
  import 'leaflet/dist/leaflet.css';
  import { api } from './api.js';
  import { addFonds } from './mapbase.js';
  import { shadeImage, MERCATOR_LAT } from './sun.js';

  let { day, band = '', hour = null, colors = {} } = $props();

  let el = $state();
  let map, dots, shade;
  let count = $state(null);
  let busy = $state(false);
  let home = null;
  let lastKey = '';

  async function load() {
    if (!map) return;
    busy = true;
    try {
      const r = await api.dayHeard(day, band, hour);
      home = r.home;
      dots.clearLayers();
      if (home) {
        L.circleMarker(home, { radius: 6, color: '#cfb53b', fillColor: '#cfb53b', fillOpacity: 1, weight: 2 })
          .bindTooltip('WebSDR ORSAT').addTo(dots);
      }
      for (const p of r.points) {
        const c = colors[p.band] || '#e07a5f';
        const hh = p.h1 === p.h2 ? `${String(p.h1).padStart(2, '0')} h` : `${String(p.h1).padStart(2, '0')}–${String(p.h2).padStart(2, '0')} h`;
        L.circleMarker([p.lat, p.lon], { radius: 3.5, color: c, fillColor: c, fillOpacity: 0.85, weight: 0 })
          .bindTooltip(`<b>${p.call}</b> ${p.grid} · ${p.band} ${p.mode.toUpperCase()}<br>${p.km?.toLocaleString('fr-FR') ?? '?'} km · ${p.snr ?? '?'} dB · ${hh} UTC · ${p.n} décodage${p.n > 1 ? 's' : ''}`)
          .addTo(dots);
      }
      count = r.points.length;
      shade?.remove();
      shade = null;
      if (hour != null) {
        const t = new Date(Date.UTC(+day.slice(0, 4), +day.slice(4, 6) - 1, +day.slice(6, 8), hour, 30));
        shade = L.imageOverlay(shadeImage(t), [[-MERCATOR_LAT, -180], [MERCATOR_LAT, 180]]).addTo(map);
        dots.eachLayer((m) => m.bringToFront && m.bringToFront());
      }
    } catch (err) {
      count = null;
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    map = L.map(el, { minZoom: 1, worldCopyJump: false });
    addFonds(L, map);
    map.setView([30, 0], 2);
    dots = L.layerGroup().addTo(map);
    lastKey = `${day}|${band}|${hour}`;
    load();
  });
  onDestroy(() => map?.remove());

  // Nouveau filtre -> nouvelle carte
  $effect(() => {
    const key = `${day}|${band}|${hour}`;
    if (key !== lastKey && map) { lastKey = key; load(); }
  });
</script>

<div class="wrap">
  <div class="map" bind:this={el}></div>
  <div class="cap">
    {#if busy}chargement…{:else if count != null}{count} station{count > 1 ? 's' : ''} localisée{count > 1 ? 's' : ''}{band ? ` sur ${band}` : ', toutes bandes'}{hour != null ? ` · ${String(hour).padStart(2, '0')} h UTC (ligne grise à ${String(hour).padStart(2, '0')}:30)` : ' · toute la journée'}{/if}
  </div>
</div>

<style>
  .map { height: 440px; border: 1px solid var(--panel-edge); border-radius: 6px; background: #0b0d12; }
  .cap { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
</style>
