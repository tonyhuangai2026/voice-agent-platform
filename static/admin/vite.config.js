import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// Mounted at the site root / by FastAPI StaticFiles (single-page merge,
// tech_design §2). Hash-mode router avoids the need for a server catch-all
// rewrite.
export default defineConfig({
  base: '/',
  plugins: [vue()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
});
