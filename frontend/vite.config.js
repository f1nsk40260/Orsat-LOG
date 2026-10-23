import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// En développement (npm run dev), l'API est servie par `python3 run.py --server` sur le port 8740.
export default defineConfig({
  plugins: [svelte()],
  base: './',            // chemins relatifs : marche à la racine comme derrière /log/
  // fonds de carte détaillés (jusqu'à 3,7 Mo) : chargés à la demande au zoom, gros par nature
  build: {
    chunkSizeWarningLimit: 4000,
    // deux pages : le carnet (index.html, connexion requise) et la page publique « écoute » du WebSDR
    rollupOptions: { input: { main: 'index.html', ecoute: 'ecoute.html' } },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8740',
      '/ws': { target: 'ws://127.0.0.1:8740', ws: true },
    },
  },
});
