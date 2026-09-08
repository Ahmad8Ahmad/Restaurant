import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  // This dev machine has ~3.8 GB RAM; Chromium can transiently OOM/crash.
  // One retry keeps the suite green without masking real regressions.
  retries: 1,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],
  timeout: 180000,
  expect: { timeout: 15000 },
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // Block the app's service worker (/sw.js); it otherwise serves cached
    // "You are offline" pages and interferes with E2E assertions.
    serviceWorkers: 'block',
    // Keep per-page render cost low: small viewport, no GPU, no audio.
    viewport: { width: 1280, height: 720 },
    colorScheme: 'light',
    launchOptions: {
      args: ['--disable-gpu', '--disable-software-rasterizer', '--mute-audio'],
    },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
