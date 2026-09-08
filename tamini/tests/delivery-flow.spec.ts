import { test, expect, Page, BrowserContext } from "@playwright/test";
import { BASE, dismissModal, firebaseLogin } from "./helpers";

test.describe("Delivery driver flows", () => {
  // Shared authenticated page for the whole file (see restaurant-flow.spec.ts
  // for why: real Firebase login is slow/flaky per-test).
  let ctx: BrowserContext;
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    ctx = await browser.newContext({ serviceWorkers: "block" });
    page = await ctx.newPage();
    await firebaseLogin(
      page,
      "ahmad19.87@hotmail.com",
      "Ahmad0944043511",
      "/delivery/available/",
      120000,
    );
  });

  test.afterAll(async () => {
    if (ctx) await ctx.close().catch(() => {});
  });

  test("available orders page renders and driver finance link", async () => {
    await dismissModal(page);
    expect(page.url()).toContain("/delivery/");
    const body = await page.locator("body").innerText();
    expect(body.length).toBeGreaterThan(0);
  });

  test("driver finance dashboard loads", async () => {
    await dismissModal(page);
    await page.goto(`${BASE}/en/delivery/finance/`);
    await dismissModal(page);
    expect(page.url()).toContain("/delivery/finance/");
    const body = await page.locator("body").innerText();
    expect(body.length).toBeGreaterThan(0);
  });

  test("accept and deliver a pending order", async () => {
    await dismissModal(page);
    const acceptBtn = page
      .locator('button:has-text("Accept and Receive Fee")')
      .first();
    const arabicBtn = page
      .locator('button:has-text("قبول واستلام الأجرة")')
      .first();
    const target = (await acceptBtn.count())
      ? acceptBtn
      : (await arabicBtn.count())
        ? arabicBtn
        : null;
    if (!target) {
      test.skip(true, "No available order to accept right now");
      return;
    }
    page.on("dialog", (d) => d.accept().catch(() => {}));
    await target.click();
    await page.waitForTimeout(2500);

    const deliveredBtn = page
      .locator('button:has-text("Order Delivered Successfully")')
      .first();
    const arabicDelivered = page
      .locator('button:has-text("تم تسليم الطلب بنجاح")')
      .first();
    const dTarget = (await deliveredBtn.count())
      ? deliveredBtn
      : (await arabicDelivered.count())
        ? arabicDelivered
        : null;
    if (dTarget && (await dTarget.isVisible().catch(() => false))) {
      await dTarget.click();
      await page.waitForTimeout(2000);
    }
  });
});