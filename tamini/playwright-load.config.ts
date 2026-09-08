import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

/**
 * Load-test runner: a separate config so the regular E2E suite and the
 * 300-account / 100-order load test can run independently.
 */
export default defineConfig({
  ...baseConfig,
  testMatch: /order-load-300\.spec\.ts/,
  globalSetup: "./tests/load-global-setup",
  globalTeardown: "./tests/load-global-setup", // exports globalTeardown
  timeout: 900000,
  expect: { timeout: 30000 },
  retries: 0,
  reporter: [["html", { open: "never", outputFolder: "playwright-report-load" }], ["list"]],
  use: {
    ...baseConfig.use,
    serviceWorkers: "block",
  },
});