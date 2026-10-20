import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "replay-e2e",
  use: { baseURL: "http://127.0.0.1:8127" },
  webServer: {
    command:
      "python3 -m http.server 8127 --bind 127.0.0.1 --directory dist-replay",
    url: "http://127.0.0.1:8127",
    reuseExistingServer: false,
  },
  reporter: [
    ["list"],
    ["json", { outputFile: "../../var/replay-browser.json" }],
  ],
});
