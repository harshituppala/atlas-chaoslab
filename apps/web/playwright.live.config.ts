import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "live-validation",
  workers: 1,
  retries: 0,
  timeout: 300000,
  use: { baseURL: process.env.ATLAS_TEST_URL ?? "http://127.0.0.1:8003" },
  reporter: "list",
});
