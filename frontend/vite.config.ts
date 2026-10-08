import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// Le build écrit dans static/frontend/ avec des noms FIXES : le gabarit Django
// templates/tirage.html les référence directement (pas de manifeste à lire).
export default defineConfig({
  plugins: [vue()],
  base: "/static/frontend/",
  build: {
    outDir: "../static/frontend",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: "src/tirage/main.ts",
      output: {
        entryFileNames: "tirage.js",
        chunkFileNames: "tirage-[name].js",
        assetFileNames: "tirage[extname]",
      },
    },
  },
  server: {
    // En développement (npm run dev), l'API est celle de Django.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: { environment: "jsdom", globals: true, include: ["src/**/*.test.ts"] },
});
