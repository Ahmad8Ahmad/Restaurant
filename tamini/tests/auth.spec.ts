import { test, expect } from "@playwright/test";
import { BASE, dismissModal, firebaseLogin, harden, logout } from "./helpers";

test.describe("Authentication", () => {
  test.beforeEach(async ({ page }) => {
    await harden(page);
  });

  test("login page renders all auth options", async ({ page }) => {
    await page.goto(`${BASE}/en/accounts/login/`);
    await dismissModal(page);
    await expect(page.locator("#tfa-login-email")).toBeVisible();
    await expect(page.locator("#tfa-login-password")).toBeVisible();
    await expect(page.locator("#tfa-login-btn")).toBeVisible();
    await expect(page.locator("#login-google-auth")).toBeVisible();
    // Register link resolves to top-level /register/
    const regLink = page.locator('a[href*="/register/"]').first();
    await expect(regLink).toBeVisible();
  });

  test("wrong password shows a helpful message (not generic)", async ({
    page,
  }) => {
    await page.goto(`${BASE}/en/accounts/login/`);
    await dismissModal(page);
    await page.locator("#tfa-login-email").fill("ahmad19.8722.2@gmail.com");
    await page
      .locator("#tfa-login-password")
      .fill("DefinitelyWrongPassword123");
    await page.locator("#tfa-login-btn").click();
    // The error message is rendered as a .tfa-msg element (sibling of
    // #tfa-login-msg), so look for it and assert on its text.
    const msg = page.locator("#tfa-login-msg + .tfa-msg, .tfa-msg").first();
    await expect(msg).toBeVisible({ timeout: 45000 });
    const text = (await msg.innerText().catch(() => "")) || "";
    expect(text.length).toBeGreaterThan(0);
    expect(text.toLowerCase()).not.toContain("something went wrong");
  });

  test("forgot password panel opens with email field", async ({ page }) => {
    await page.goto(`${BASE}/en/accounts/login/`);
    await dismissModal(page);
    await page.locator("#show-forgot-btn").click().catch(async () => {
      await page.getByText(/نسيت كلمة المرور|forgot/i).first().click();
    });
    await page.waitForTimeout(800);
    await expect(page.locator("#tfa-forgot-email")).toBeVisible({
      timeout: 10000,
    });
  });

  test("restaurant owner logs in and lands on the restaurant dashboard", async ({
    page,
  }) => {
    await firebaseLogin(
      page,
      "ahmad19.8722.2@gmail.com",
      "Admin123",
      "/restaurants/dashboard/",
      60000,
    );
    await expect
      .poll(() => page.url(), { timeout: 15000 })
      .toContain("/restaurants/dashboard/");
  });

  test("delivery driver logs in and lands on available orders", async ({
    page,
  }) => {
    await firebaseLogin(
      page,
      "ahmad19.87@hotmail.com",
      "Ahmad0944043511",
      "/delivery/available/",
      60000,
    );
    await expect
      .poll(() => page.url(), { timeout: 15000 })
      .toContain("/delivery/available/");
  });

  test("customer logs in and lands on home (not a role dashboard)", async ({
    page,
  }) => {
    await firebaseLogin(
      page,
      "ahmad0944043511@gmail.com",
      "Rand1234567890",
      "/",
      60000,
    );
    const url = await expect
      .poll(() => page.url(), { timeout: 15000 })
      .not.toContain("/delivery/available/");
  });

  test("logout clears the session", async ({ page, context }) => {
    await firebaseLogin(
      page,
      "ahmad19.8722.2@gmail.com",
      "Admin123",
      "/restaurants/dashboard/",
      60000,
    );
    // Perform a real logout via the logout POST endpoint using the CSRF
    // cookie, then confirm a protected page no longer lets us through.
    const ok = await page.evaluate(async () => {
      const csrf = document.cookie
        .split("; ")
        .map((c) => c.split("="))
        .filter((p) => p[0] === "csrftoken")
        .map((p) => decodeURIComponent(p[1] || ""))[0];
      const body = new URLSearchParams();
      if (csrf) body.append("csrfmiddlewaretoken", csrf);
      const res = await fetch("/en/accounts/logout/", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
        credentials: "same-origin",
      });
      return res.status;
    });
    expect(Number(ok)).toBeGreaterThanOrEqual(200, `logout status was ${ok}`);

    // Visiting a protected page should now redirect to the login page.
    await page.goto(`${BASE}/en/restaurants/dashboard/`);
    await page.waitForURL((url) => url.pathname.includes("/login/"), {
      timeout: 20000,
    });
    expect(page.url()).toContain("/login/");
  });
});
