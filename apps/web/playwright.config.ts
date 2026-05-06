import { defineConfig, devices } from "@playwright/test";


export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  timeout: 45_000,
  use: {
    baseURL: "http://127.0.0.1:13000",
    headless: true,
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 960 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "node ./e2e/run-smoke-api.mjs",
      url: "http://127.0.0.1:18000/api/health",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        SMOKE_API_PORT: "18000",
        SMOKE_WEB_ORIGIN: "http://127.0.0.1:13000",
      },
    },
    {
      command: "npm run build && npm run start:smoke",
      url: "http://127.0.0.1:13000/jobs",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        NEXT_PUBLIC_API_URL: "http://127.0.0.1:18000",
      },
    },
  ],
});