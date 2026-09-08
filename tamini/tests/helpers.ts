import { Page, expect } from "@playwright/test";

export const BASE = "http://127.0.0.1:8000";

/**
 * Reduce flakiness and server/browser load for a page:
 *  - Never load /sw.js (its cache serves stale "offline"/404 pages to E2E).
 *  - Skip heavy third-party resources (Google Maps, font CDNs, audio) that
 *    are cosmetic and can hang on a strained network.
 * Call once per Page (idempotent).
 */
export async function harden(page: Page) {
  const targets = [
    "**/sw.js",
    "https://maps.googleapis.com/**",
    "https://*.googleapis.com/css?**",
    "https://fonts.googleapis.com/**",
    "https://fonts.gstatic.com/**",
    "https://*.tapmaps.app/**",
    "https://*.soundjay.com/**",
    "https://unpkg.com/**",
    "https://cdn.jsdelivr.net/**",
  ];
  for (const pat of targets) {
    await page
      .route(pat, (route) => route.abort("aborted").catch(() => {}))
      .catch(() => {});
  }
  // Keep Firebase auth endpoints reachable even though fonts/maps are blocked.
  await page
    .route("https://identitytoolkit.googleapis.com/**", (route) => route.continue())
    .catch(() => {});
}

/**
 * Dismiss the "download our app" modal if it appears. The modal lives in
 * base.html and is gated by sessionStorage so it persists across reloads.
 */
export async function dismissModal(page: Page) {
  await page.evaluate(() => {
    try {
      sessionStorage.setItem("tamini_app_download_dismissed", "1");
    } catch (e) {}
    const m = document.getElementById("appDownloadModal") as HTMLElement | null;
    if (m) {
      m.classList.add("hidden");
      m.classList.remove("flex");
    }
  });
}

/**
 * Log in via the Firebase email/password form and wait for a redirect that
 * matches `expectedFragment`. Fire a small delay first to let the auth form
 * render, and reuse a single tab (sessionStorage kept).
 */
export async function firebaseLogin(
  page: Page,
  email: string,
  password: string,
  expectedFragment?: string,
  timeout = 60000,
) {
  // Real Firebase email/password auth is occasionally slow/flaky. Retry the
  // same credentials up to 3 times before giving up.
  const attempts = 3;
  for (let i = 0; i < attempts; i++) {
    const landed = await attemptLogin(page, email, password, expectedFragment, timeout);
    if (landed) return;
  }
  throw new Error(
    `firebaseLogin failed after ${attempts} attempts for ${email} (expected ${expectedFragment})`,
  );
}

async function attemptLogin(
  page: Page,
  email: string,
  password: string,
  expectedFragment: string | undefined,
  timeout: number,
): Promise<boolean> {
  await harden(page);
  await page.goto(`${BASE}/en/accounts/login/`, { waitUntil: "domcontentloaded" });
  await dismissModal(page);
  await page.locator("#tfa-login-email").waitFor({ state: "visible", timeout: 20000 });
  await page.locator("#tfa-login-email").fill(email);
  await page.locator("#tfa-login-password").fill(password);
  await dismissModal(page);
  await page.locator("#tfa-login-btn").click({ force: true });
  try {
    if (expectedFragment) {
      await page.waitForURL((url) => url.pathname.includes(expectedFragment), {
        timeout,
      });
    } else {
      await page.waitForURL((url) => !url.pathname.includes("/login/"), {
        timeout,
      });
    }
    await dismissModal(page);
    return true;
  } catch {
    return false;
  }
}

export async function logout(page: Page) {
  // Perform a real logout via the logout POST endpoint using the CSRF cookie.
  // This is fast and deterministic (avoids menu/dropdown UI flakiness).
  await harden(page).catch(() => {});
  await page.evaluate(async () => {
    const csrf = document.cookie
      .split("; ")
      .map((c) => c.split("="))
      .filter((p) => p[0] === "csrftoken")
      .map((p) => decodeURIComponent(p[1] || ""))[0];
    const body = new URLSearchParams();
    if (csrf) body.append("csrfmiddlewaretoken", csrf);
    await fetch("/en/accounts/logout/", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
      credentials: "same-origin",
    });
  }).catch(() => {});
  await page.waitForTimeout(300);
}

/**
 * Establish a session + CSRF cookie by visiting the cart page, then add a
 * menu item to the cart via a direct fetch (mirrors the add-to-cart AJAX).
 */
export async function addItemToCart(
  page: Page,
  menuItemId: number,
  quantity = 1,
): Promise<{ ok: boolean; reason?: string; data?: any }> {
  await harden(page).catch(() => {});
  await page.goto(`${BASE}/en/orders/cart/`, { waitUntil: "domcontentloaded" });
  await dismissModal(page);

  const result = await page.evaluate(
    async ({ itemId, qty }) => {
      const csrf = document.cookie
        .split("; ")
        .map((c) => c.split("="))
        .filter((p) => p[0] === "csrftoken")
        .map((p) => decodeURIComponent(p[1] || ""))[0];
      if (!csrf) return { ok: false, reason: "no csrf cookie" };
      const fd = new FormData();
      fd.append("csrfmiddlewaretoken", csrf);
      fd.append("quantity", String(qty));
      const res = await fetch(`/en/orders/add-to-cart/${itemId}/`, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrf,
        },
      });
      const ct = res.headers.get("content-type") || "";
      if (ct.includes("json")) return { ok: true, data: await res.json() };
      return { ok: false, reason: `status ${res.status}` };
    },
    { itemId: menuItemId, qty: quantity },
  );
  await dismissModal(page);
  return result;
}
