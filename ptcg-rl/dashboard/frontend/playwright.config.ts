import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "cd ../.. && UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run --no-sync ptcg dashboard serve --host 127.0.0.1 --port 8765",
    url: "http://127.0.0.1:8765/api/v1/data-health",
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
