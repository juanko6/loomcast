import { svelte } from "@sveltejs/vite-plugin-svelte";
import { svelteTesting } from "@testing-library/svelte/vite";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Config aparte de astro.config.mjs a propósito: los tests solo necesitan el
// compilador de Svelte y el alias `@/`, no Astro ni Tailwind.
export default defineConfig({
  plugins: [svelte(), svelteTesting()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    setupFiles: ["./vitest.setup.ts"],
    clearMocks: true,
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["src/lib/**/*.ts", "src/components/**/*.svelte"],
      reporter: ["text", "html"],
      // Suelo para no retroceder, no una meta (al crear la suite: 96 % de líneas).
      thresholds: { statements: 90, lines: 90, functions: 90, branches: 80 },
    },
  },
});
