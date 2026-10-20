import { defineConfig } from "vite";
export default defineConfig({
  root: "lab",
  base: "/",
  build: { outDir: "../dist-lab", emptyOutDir: true },
});
