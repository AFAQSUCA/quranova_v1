import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// Le build écrit dans static/frontend/ avec des noms FIXES : le gabarit Django
// templates/tirage.html, scene.html et commande.html les référencent directement (pas de manifeste à lire).
export default defineConfig({
  plugins: [vue()],
  base: "/static/frontend/",
  build: {
    outDir: "../static/frontend",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: { tirage: "src/tirage/main.ts", scene: "src/scene/main.ts", commande: "src/commande/main.ts" },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "partage-[hash].js",
        assetFileNames: "frontend[extname]", // un seul fichier de style pour les trois écrans
      },
    },
  },
  server: {
    // En développement (npm run dev), l'API est celle de Django.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: { environment: "jsdom", globals: true, include: ["src/**/*.test.ts"] },
});
