// @ts-check
import { defineConfig } from "astro/config";
import svelte from "@astrojs/svelte";
import tailwindcss from "@tailwindcss/vite";

// Loomcast Studio (Astro + Svelte islands + Tailwind v4).
// Build 100% estático a `dist/`; en producción lo sirve el mismo FastAPI.
// En dev, Vite hace de proxy de `/api` hacia el backend (uvicorn en 8700),
// así las islas llaman a las mismas rutas que en producción.
const BACKEND = process.env.LOOMCAST_API ?? "http://127.0.0.1:8700";

export default defineConfig({
  integrations: [svelte()],
  output: "static",
  server: { port: 4321 },
  vite: {
    plugins: [tailwindcss()],
    server: {
      proxy: {
        "/api": { target: BACKEND, changeOrigin: true },
      },
    },
  },
});
