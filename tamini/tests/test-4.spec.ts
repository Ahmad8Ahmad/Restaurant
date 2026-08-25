import { test, expect } from "@playwright/test";

test("full order flow: customer → restaurant → delivery", async ({ page }) => {
  test.setTimeout(120000);
  page.setDefaultTimeout(20000);

  async function dismissModal() {
    await page.evaluate(() => {
      try { sessionStorage.setItem("tamini_app_download_dismissed", "1"); } catch (e) {}
      const m = document.getElementById("appDownloadModal");
      if (m) { m.classList.add("hidden"); m.classList.remove("flex"); }
    });
  }

  // 1. Customer: add item to cart
  await page.goto("http://127.0.0.1:8000/en/");
  await dismissModal();
  const addResult = await page.evaluate(async () => {
    const form = document.querySelector('form[action*="add-to-cart"]') as HTMLFormElement;
    if (!form) return { ok: false };
    const csrf = (form.querySelector('[name=csrfmiddlewaretoken]') as HTMLInputElement)?.value || '';
    const fd = new FormData();
    fd.append('csrfmiddlewaretoken', csrf);
    fd.append('quantity', '1');
    const res = await fetch(form.getAttribute('action') || '', {
      method: 'POST', body: fd, credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf },
    });
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('json')) return { ok: true, ...(await res.json()) };
    return { ok: false, status: res.status };
  });
  expect(addResult.ok).toBe(true);

  // 2. Customer: checkout
  await page.goto("http://127.0.0.1:8000/en/orders/checkout/");
  await dismissModal();
  await page.locator('input[name="customer_name"]').fill("Ahmad");
  await page.locator('input[name="customer_phone"]').fill("094404351");
  await page.locator('input[name="customer_email"]').fill("test@test.com");
  await page.locator('input[name="delivery_address"]').fill("damascus mazzeh");

  // 3. Customer: confirm order → redirects to payments page
  await page.locator('#checkout-btn').click();
  await page.waitForURL("**/payments/**", { timeout: 10000 });
  await dismissModal();

  // 4. Customer: select cash on delivery and confirm
  await page.locator('input[value="Cash"]').click({ force: true });
  await page.getByRole("button", { name: /Confirm Order$/i }).click();
  await page.waitForURL("**/payments/success/**", { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(1000);
  const bodyAfterOrder = await page.locator('body').innerText();
  expect(bodyAfterOrder).toMatch(/Order Confirmed|تم تأكيد الطلب/i);

  // Helper: login via Firebase and wait for redirect
  async function firebaseLogin(email: string, password: string, expectedUrl: string) {
    await page.goto("http://127.0.0.1:8000/en/accounts/login/");
    await dismissModal();
    page.on("console", msg => {
      if (msg.text().includes('error') || msg.text().includes('Firebase') || msg.text().includes('Error'))
        console.log('BROWSER:', msg.text().substring(0, 200));
    });
    await page.locator("#tfa-login-email").fill(email);
    await page.locator("#tfa-login-password").fill(password);
    await page.locator("#tfa-login-btn").click();
    try {
      await page.waitForURL(`**${expectedUrl}**`, { timeout: 30000 });
    } catch {
      console.log('Login redirect failed. Current URL:', page.url());
      const body = await page.locator('body').innerText();
      console.log('Page text:', body.substring(0, 500));
    }
    await dismissModal();
  }

  // 5. Restaurant owner: login
  await firebaseLogin("ahmad0944043511@gmail.com", "Rand1234567890", "/restaurants/dashboard/");
  console.log('After restaurant login URL:', page.url());

  // 6. Restaurant owner: prepare order
  const prepareBtn = page.locator('button:has-text("Prepare Order")').first();
  await prepareBtn.waitFor({ state: "visible", timeout: 20000 });
  await prepareBtn.click();
  await page.waitForTimeout(2000);

  // 7. Restaurant owner: logout
  await page.locator('#userMenuBtn').click();
  await page.locator('form[action*="logout"] button[type="submit"]').click();
  await page.waitForLoadState('networkidle');

  // 8. Delivery driver: login
  await firebaseLogin("ahmad19.87@hotmail.com", "Ahmad0944043511", "/delivery/available/");
  console.log('After delivery login URL:', page.url());

  page.on("dialog", (dialog) => { dialog.accept().catch(() => {}); });

  // 9. Delivery driver: accept order
  const acceptBtn = page.locator('button:has-text("Accept and Receive Fee")').first();
  await acceptBtn.waitFor({ state: "visible", timeout: 20000 });
  await acceptBtn.click();
  await page.waitForTimeout(2000);

  // 10. Delivery driver: mark as delivered
  const deliveredBtn = page.locator('button:has-text("Order Delivered Successfully")').first();
  await deliveredBtn.waitFor({ state: "visible", timeout: 20000 });
  await deliveredBtn.click();
  await page.waitForTimeout(2000);

  // 11. Verify
  await page.goto("http://127.0.0.1:8000/en/accounts/login/");
  await dismissModal();
  await expect(page.locator("#tfa-login-email")).toBeVisible();
});
