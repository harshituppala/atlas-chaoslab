import { defineConfig } from "vite";
export default defineConfig({
  root: "replay",
  base: "./",
  build: { outDir: "../dist-replay", emptyOutDir: true },
});
