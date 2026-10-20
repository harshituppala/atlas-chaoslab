import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "presentation-e2e",
  use: { baseURL: "http://127.0.0.1:8131" },
  webServer: {
    command: "python3 -m http.server 8131 --bind 127.0.0.1 --directory dist",
    url: "http://127.0.0.1:8131",
    reuseExistingServer: false,
  },
  reporter: [
    ["list"],
    ["json", { outputFile: "../../var/presentation-browser.json" }],
  ],
});
