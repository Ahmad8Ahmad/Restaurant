import { test, expect } from "@playwright/test";

test("test", async ({ page }) => {
  // تفعيل خاصية التروي في الكبس داخل الفايرفوكس تلقائياً بدون إبطاء الكروم
  page.setDefaultTimeout(15000);

  // 1. مرحلة الزبون: عمل الطلب (بأقصى سرعة)
  await page.goto("http://127.0.0.1:8000/en/");
  await page.getByRole("link", { name: "View Menu " }).first().click();
  await page.getByRole("button", { name: "+ Add" }).first().click();

  await page.getByRole("textbox", { name: "اسمك الكامل" }).fill("Ahmad");
  await page
    .getByRole("textbox", { name: "مثال: 09XX XXX XXX" })
    .fill("094404351");
  await page
    .getByRole("textbox", { name: "Example: Damascus, Mazzeh, Al" })
    .fill("damascuse");

  await page.getByRole("button", { name: "Confirm Order and Pay" }).click();
  await page.getByText("الدفع عند الاستلام").click();
  await page.getByRole("button", { name: "تأكيد الطلب" }).click();

  // 2. مرحلة صاحب المطعم: تسجيل الدخول والتجهيز السريع
  await page.goto("http://127.0.0.1:8000/en/accounts/login/");
  await page
    .getByRole("textbox", { name: "Email" })
    .fill("ahmad0944043511@gmail.com");
  await page.getByRole("textbox", { name: "Password" }).fill("Rand1234567890");

  // ننتظر زر الـ Login ليصير قابل للضغط تماماً قبل الكبس (حل مشكلة الفايرفوكس)
  const loginBtn = page.getByRole("button", { name: "Login" });
  await loginBtn.waitFor({ state: "visible" });
  await loginBtn.click();

  // ننتظر ظهور عنصر داخل لوحة التحكم لنتأكد أن التحويل نجح، بدلاً من انتظار الرابط بالثواني
  const prepareBtn = page.locator('text="Prepare Order"').first();
  await prepareBtn.waitFor({ state: "visible" });
  await prepareBtn.click();

  // تسجيل الخروج السريع
  await page.getByRole("button", { name: "My Account" }).click();
  await page.getByRole("button", { name: "Logout" }).click();

  // 3. مرحلة الديلفري: قبول الطلب فوراً
  await page.goto("http://127.0.0.1:8000/en/accounts/login/");
  await page
    .getByRole("textbox", { name: "Email" })
    .fill("ahmad19.87@hotmail.com");
  await page.getByRole("textbox", { name: "Password" }).fill("Ahmad0944043511");
  await loginBtn.waitFor({ state: "visible" });
  await loginBtn.click();

  // التعامل المسبق والذكي مع نافذة التأكيد المنبثقة (Alert) بدون تأخير
  page.once("dialog", (dialog) => {
    dialog.accept().catch(() => {});
  });

  // ننتظر زر القبول يظهر في الصفحة ونكبس أول واحد فوراً
  const acceptBtn = page
    .getByRole("link", { name: "Accept and Receive Fee " })
    .first();
  await acceptBtn.waitFor({ state: "visible" });
  await acceptBtn.click();

  // إنهاء الطلب بنجاح
  const successBtn = page
    .getByRole("link", { name: "✅ Order Delivered Successfully" })
    .first();
  await successBtn.waitFor({ state: "visible" });
  await successBtn.click();

  await page.goto("http://127.0.0.1:8000/en/accounts/login/");
});
