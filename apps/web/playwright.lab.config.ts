import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "lab-e2e",
  workers: 1,
  timeout: 45000,
  use: { baseURL: "http://127.0.0.1:8134" },
  webServer: {
    command: `cd ../.. && PYTHONPATH=src ${process.env.ATLAS_TEST_PYTHON ?? ".runtime/bin/python"} -m atlas.synthetic_lab --port 8134 --web-root apps/web/dist-lab`,
    url: "http://127.0.0.1:8134/healthz",
    reuseExistingServer: false,
  },
  reporter: [["list"], ["json", { outputFile: "../../var/lab-browser.json" }]],
});
