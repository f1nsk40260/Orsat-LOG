import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// En développement (npm run dev), l'API est servie par `python3 run.py --server` sur le port 8740.
export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8740',
      '/ws': { target: 'ws://127.0.0.1:8740', ws: true },
    },
  },
});
