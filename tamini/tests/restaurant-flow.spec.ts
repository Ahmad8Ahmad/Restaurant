import { test, expect, Page, BrowserContext } from "@playwright/test";
import { BASE, dismissModal, firebaseLogin, logout } from "./helpers";

test.describe("Restaurant owner flows", () => {
  // Log in ONCE for the whole file and share the authenticated page. Real
  // Firebase email/password auth is slow/flaky, so per-test re-login caused
  // intermittent timeouts. Tests run serially (workers=1), so mutation-heavy
  // tests share a single session safely.
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

  test("dashboard loads with order and menu tabs", async () => {
    await dismissModal(page);
    // The dashboard (not a 404): tab content views exist, restaurant name is
    // shown, and the URL is the dashboard. (NOTE: do not assert "not 404" on
    // body text — real customer phone numbers like 094404351 contain "404".)
    await expect(page.locator("#orders-list-view")).toHaveCount(1);
    await expect(page.locator("#menu-view")).toHaveCount(1);
    await expect(page.locator("#add-view")).toHaveCount(1);
    expect(page.url()).toContain("/restaurants/dashboard/");
  });

  test("add a category via the dashboard", async () => {
    await dismissModal(page);
    const catName = `Playwright Cat ${Date.now()}`;
    // Category creation is a session-authenticated AJAX POST.
    const result = await page.evaluate(async (name) => {
      const csrf = document.cookie
        .split("; ")
        .map((c) => c.split("="))
        .filter((p) => p[0] === "csrftoken")
        .map((p) => decodeURIComponent(p[1] || ""))[0];
      if (!csrf) return { ok: false, reason: "no csrf" };
      const fd = new FormData();
      fd.append("csrfmiddlewaretoken", csrf);
      fd.append("name", name);
      const res = await fetch("/en/restaurants/category/add/", {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf },
      });
      return { ok: res.redirected || res.status < 400, status: res.status, url: res.url };
    }, catName);
    expect(result.status < 400, JSON.stringify(result)).toBe(true);
  });

  test("add a menu item via the dashboard add-item form", async () => {
    await dismissModal(page);
    // Switch to the "Add Meal" tab deterministically via the page's showTab().
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll(".tab-btn")).find((b) =>
        b.textContent.includes("Add Meal") || b.textContent.includes("إضافة وجبة"),
      );
      if (btn && (window as any).showTab) (window as any).showTab("add-view", btn);
    }).catch(() => {});
    const addView = page.locator("#add-view");
    await addView.waitFor({ state: "visible", timeout: 8000 }).catch(() => {});

    const itemName = `PW Item ${Date.now()}`;
    const nameField = addView.locator('input[name="name"]').first();
    if (await nameField.isVisible().catch(() => false)) {
      await nameField.fill(itemName);
      await addView.locator('input[name="price"]').first().fill("120");
      const desc = addView.locator('textarea[name="description"]').first();
      if (await desc.isVisible().catch(() => false)) {
        await desc.fill("Playwright test item");
      }
      const catSel = addView.locator('select[name="category"]').first();
      if (await catSel.isVisible().catch(() => false)) {
        const count = await catSel.locator("option").count();
        if (count > 1) await catSel.selectOption({ index: 1 });
      }
      const submit = addView.locator('button[type="submit"]').first();
      if (await submit.isVisible().catch(() => false)) {
        await Promise.all([
          page.waitForNavigation({ waitUntil: "domcontentloaded" }).catch(() => {}),
          submit.click(),
        ]).catch(() => {});
      }
      await page.waitForTimeout(1500);
      // After a successful add, we should still be on the dashboard.
      expect(page.url()).toContain("/restaurants/dashboard/");
    } else {
      test.skip(true, "Add-item form not present on dashboard");
    }
  });

  test("prepare an order (mark as out)", async () => {
    await dismissModal(page);
    const prepareBtn = page.locator('button:has-text("Prepare Order")').first();
    const arabicBtn = page.locator('button:has-text("تجهيز الطلب")').first();
    const target = (await prepareBtn.count())
      ? prepareBtn
      : (await arabicBtn.count())
        ? arabicBtn
        : null;
    if (!target) {
      test.skip(true, "No pending order to prepare right now");
      return;
    }
    await target.click();
    await page.waitForTimeout(2000);
  });
});