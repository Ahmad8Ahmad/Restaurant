import { test, expect, Page, BrowserContext } from "@playwright/test";
import { BASE, dismissModal, firebaseLogin, logout } from "./helpers";

test.describe("Admin flows", () => {
  // Shared authenticated page for the whole file (see restaurant-flow.spec.ts
  // for why: real Firebase login is slow/flaky per-test, and opening a second
  // browser context alongside heavy pages is not reliable on this machine).
  let ctx: BrowserContext;
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    ctx = await browser.newContext({ serviceWorkers: "block" });
    page = await ctx.newPage();
    await firebaseLogin(
      page,
      "ahmad19.8722.2@gmail.com",
      "Admin123",
      "/restaurants/dashboard/",
      120000,
    );
  });

  test.afterAll(async () => {
    if (ctx) await ctx.close().catch(() => {});
  });

  test("admin dashboard loads KPIs and recent orders", async () => {
    await dismissModal(page);
    await page.goto(`${BASE}/en/restaurants/admin-dashboard/`);
    await dismissModal(page);
    expect(page.url()).toContain("admin-dashboard");
    const body = await page.locator("body").innerText();
    expect(body).toMatch(/لوحة التحكم|Control Panel|Platform Overview|نظرة عامة/i);
  });

  test("non-superuser cannot open admin dashboard", async () => {
    // Switch role on the existing shared page: log out, then log in as the
    // delivery driver (avoids spawning a second browser context).
    await logout(page).catch(() => {});
    await firebaseLogin(
      page,
      "ahmad19.87@hotmail.com",
      "Ahmad0944043511",
      "/delivery/available/",
      120000,
    );
    await dismissModal(page);
    await page.goto(`${BASE}/en/restaurants/admin-dashboard/`);
    await dismissModal(page);
    await page
      .waitForURL((url) => !url.pathname.includes("admin-dashboard"), {
        timeout: 15000,
      })
      .catch(() => {});
    expect(page.url()).not.toContain("admin-dashboard");
  });
});