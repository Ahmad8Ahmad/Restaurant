import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

/**
 * 1000-order load-test runner: 100 restaurants / 100 drivers /
 * 100 customers / 1000 orders, exercising the full lifecycle (payment,
 * dispatch, delivery tracking, commissions).
 *
 * Separate config + port (8002) so the regular E2E suite, the 300-order
 * load test (8001) and this 1000-order test can run independently.
 */
export default defineConfig({
  ...baseConfig,
  testMatch: /order-load-1000\.spec\.ts/,
  globalSetup: "./tests/load-1000-global-setup",
  globalTeardown: "./tests/load-1000-global-setup", // exports globalTeardown
  timeout: 1200000,
  expect: { timeout: 60000 },
  retries: 0,
  workers: 1,
  reporter: [
    ["html", { open: "never", outputFolder: "playwright-report-load-1000" }],
    ["list"],
  ],
  use: {
    ...baseConfig.use,
    serviceWorkers: "block",
  },
});
