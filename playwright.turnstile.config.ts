import { defineConfig, devices } from "@playwright/test";

const port = 3102;
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "turnstile.spec.ts",
  fullyParallel: true,
  workers: 1,
  reporter: "list",
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "turnstile-enabled", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1100 } } }],
  webServer: {
    command: `node node_modules/next/dist/bin/next dev -H 127.0.0.1 -p ${port}`,
    env: {
      ADMIN_KEY: "test-admin-key-only-not-a-secret",
      API_INTERNAL_URL: "",
      HEARDIT_E2E_DEMO_TESTING: "1",
      NEXT_PUBLIC_TURNSTILE_SITE_KEY: "heardit-playwright-site-key",
    },
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
