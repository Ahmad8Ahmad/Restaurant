/**
 * 1000-order load test: 100 restaurants / 100 drivers / 100 customers /
 * 1000 orders through the full lifecycle.
 *
 * Runs against the dev server on 127.0.0.1:8002 (seeded + started by
 * load-1000-global-setup.ts) and exercises the real endpoints:
 *
 *   1. 100 customers place 1000 orders via `POST /api/orders/checkout/` (JWT).
 *   2. 1000 orders are paid as Cash through the web payment endpoint (CSRF).
 *   3. 100 restaurant owners mark orders as "Out" (web session login +
 *      `POST /en/orders/mark-as-out/<id>/`).
 *   4. 100 drivers accept & complete the deliveries (JWT API).
 *   5. All 1000 orders reach Delivered.
 *   6. Admin verifies all 1000 payments, deliveries and commissions.
 *   7. A browser walkthrough exercises the tracking + payment UI.
 */
import { test, expect, APIRequestContext } from "@playwright/test";
import {
  LOAD_BASE as BASE,
  ACCOUNTS,
  ORDERS,
} from "./load-1000-global-setup";

const PASSWORD = "LoadTest@123";
const N = ACCOUNTS;
const M = ORDERS;
const LAT = 33.5138;
const LNG = 36.2765;

const email = (role: string, i: number) =>
  `${role}${String(i).padStart(3, "0")}@loadtest.tamini`;
const auth = (tok: string) => ({ Authorization: `Bearer ${tok}` });

// SQLite dev DB serializes single writers per file; keep write-phase
// parallelism low (configurable) and read polls high for the large scale.
const WRITE_CONC = Number(process.env.LT_WRITE_CONC || 1);
const READ_CONC = 25;

const state = {
  owners: [] as { token: string; restId: number; itemId: number }[],
  customerTokens: [] as string[],
  driverTokens: [] as string[],
  adminToken: "",
};

// order j maps cyclically onto the N accounts:
//   restaurant = j % N, customer = j % N, driver = j % N
const ordersByIndex: { id: number; total: number; owner: number; driver: number }[] = [];

async function login(
  req: APIRequestContext,
  user: string,
  pwd = PASSWORD,
): Promise<string> {
  const res = await req.post(`${BASE}/api/auth/login/`, {
    data: { email: user, password: pwd },
  });
  if (res.status() !== 200) {
    throw new Error(`login ${user}: HTTP ${res.status()} ${await res.text()}`);
  }
  return (await res.json()).access as string;
}

async function chunked<T>(
  n: number,
  size: number,
  fn: (i: number) => Promise<T>,
): Promise<T[]> {
  const out: T[] = new Array<T>(n);
  for (let start = 0; start < n; start += size) {
    const batch = [];
    for (let i = start; i < Math.min(start + size, n); i++) {
      batch.push(fn(i).then((v) => ({ i, v })));
    }
    for (const r of await Promise.all(batch)) out[r.i] = r.v;
  }
  return out;
}

async function getOrder(
  request: APIRequestContext,
  id: number,
  custTok: string,
): Promise<any> {
  const res = await request.get(`${BASE}/api/orders/${id}/`, {
    headers: auth(custTok),
  });
  if (!res.ok()) throw new Error(`order fetch ${id}: HTTP ${res.status()}`);
  return res.json();
}

async function collectAll(
  request: APIRequestContext,
  url: string,
  headers: Record<string, string>,
): Promise<any[]> {
  const all: any[] = [];
  let page = 1;
  for (;;) {
    const res = await request.get(
      `${url}${url.includes("?") ? "&" : "?"}page=${page}`,
      { headers },
    );
    if (!res.ok())
      throw new Error(`collect ${url}: HTTP ${res.status()} ${await res.text()}`);
    const body = await res.json();
    all.push(...(body.results as any[]));
    if (!body.next) break;
    page += 1;
  }
  return all;
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ request }) => {
  state.adminToken = await login(request, email("admin", 0));
  await expect
    .poll(
      async () => {
        const res = await request.get(`${BASE}/api/restaurants/?search=LoadTest`, {
          headers: auth(state.adminToken),
        });
        return res.ok() ? (await res.json()).count : 0;
      },
      { timeout: 30000 },
    )
    .toBeGreaterThanOrEqual(N);

  await chunked(N, 4, async (i) => {
    const ownerTok = await login(request, email("restaurant", i));
    const [myRes, custTok, driverTok] = await Promise.all([
      request.get(`${BASE}/api/restaurants/my/`, { headers: auth(ownerTok) }),
      login(request, email("customer", i)),
      login(request, email("delivery", i)),
    ]);
    const my = (await myRes.json()) as any[];
    if (!my.length) throw new Error(`no restaurant for owner ${i}`);
    const menu = await request.get(
      `${BASE}/api/menu-items/?restaurant=${my[0].id}&available=true`,
      { headers: auth(ownerTok) },
    );
    const items = ((await menu.json()) as any).results as any[];
    if (!items.length) throw new Error(`no menu items for restaurant ${i}`);
    state.owners[i] = { token: ownerTok, restId: my[0].id, itemId: items[0].id };
    state.customerTokens[i] = custTok;
    state.driverTokens[i] = driverTok;
  });
});

test("1000 orders are placed by 100 customers via API checkout", async ({
  request,
}) => {
  const rows = await chunked(M, WRITE_CONC, async (j) => {
    const owner = state.owners[j % N];
    const res = await request.post(`${BASE}/api/orders/checkout/`, {
      headers: auth(state.customerTokens[j % N]),
      data: {
        restaurant_id: owner.restId,
        delivery_address: `Load Test Street ${j}, Damascus`,
        delivery_lat: LAT,
        delivery_lng: LNG,
        customer_name: `Customer ${j % N}`,
        customer_phone: `091${String(j % N).padStart(7, "0")}`,
        items: [{ menu_item_id: owner.itemId, quantity: (j % 3) + 1 }],
      },
    });
    if (res.status() !== 201) {
      throw new Error(`checkout ${j}: HTTP ${res.status()} ${await res.text()}`);
    }
    const body = await res.json();
    return { id: body.id, total: body.total_price, owner: j % N, driver: j % N };
  });
  ordersByIndex.length = 0;
  ordersByIndex.push(...rows);
  expect(ordersByIndex).toHaveLength(M);
  expect(new Set(ordersByIndex.map((o) => o.id)).size).toBe(M);
  for (const o of ordersByIndex) {
    expect(o.id).toBeGreaterThan(0);
    expect(Number(o.total)).toBeGreaterThan(0);
  }
});

test("1000 orders are confirmed by Cash payment (web, CSRF)", async ({
  browser,
}) => {
await chunked(M, WRITE_CONC, async (j) => {
    const { id } = ordersByIndex[j];
    const context = await browser.newContext();
    try {
      const processUrl = `${BASE}/en/payments/process/${id}/`;
      const getRes = await context.request.get(processUrl);
      expect(getRes.ok(), `payment page for order ${id}`).toBeTruthy();
      const csrf = (await context.cookies()).find(
        (c) => c.name === "csrftoken",
      )?.value;
      expect(csrf, `csrftoken for order ${id}`).toBeTruthy();
      const res = await context.request.post(processUrl, {
        form: { csrfmiddlewaretoken: csrf!, payment_method: "Cash" },
        headers: {
          "X-CSRFToken": csrf!,
          Referer: processUrl,
          Origin: BASE,
        },
      });
      if (!res.ok()) {
        throw new Error(`cash pay order ${id}: HTTP ${res.status()} ${await res.text()}`);
      }
      const html = await res.text();
      expect(html, `cash pay success page for order ${id}`).toMatch(
        /Order Confirmed|تم تأكيد الطلب/,
      );
    } finally {
      await context.close();
    }
  });
});

test("all 1000 orders are Confirmed after payment", async ({ request }) => {
  const statuses = await chunked(M, 25, async (j) => {
    return (await getOrder(request, ordersByIndex[j].id, state.customerTokens[j % N])).status;
  });
  for (let j = 0; j < M; j++) {
    expect(statuses[j], `order ${ordersByIndex[j].id} status`).toBe("Confirmed");
  }
});

test("100 owners mark orders Out + 100 drivers accept & deliver in batches", async ({
  browser,
  request,
}) => {
  // Process the 1000 orders in batches so only a small number of orders are
  // "Out" at any moment — the driver `available` endpoint can then lazily
  // create the searching Delivery rows for exactly the orders we need.
  const BATCH = 20; // orders per mark-out + deliver round
  for (let start = 0; start < M; start += BATCH) {
    const end = Math.min(start + BATCH, M);

    // 1) Owners mark this batch of orders as Out (web session + CSRF).
await chunked(end - start, WRITE_CONC, async (k) => {
      const j = start + k;
      const { id } = ordersByIndex[j];
      const ownerIdx = ordersByIndex[j].owner;
      const context = await browser.newContext();
      try {
const loginUrl = `${BASE}/en/accounts/login/`;
      // Prime the csrftoken cookie from the login page: it always renders
      // `{% csrf_token %}` (fine outside the shared page cache), unlike the
      // shared-cached home page which only sets the cookie on cache misses.
      const prime = await context.request.get(loginUrl);
      expect(prime.ok(), `prime login ${j}`).toBeTruthy();
        let csrf = (await context.cookies()).find(
          (c) => c.name === "csrftoken",
        )?.value;
        expect(csrf, `prime csrf ${j}`).toBeTruthy();
        const loginRes = await context.request.post(loginUrl, {
          form: {
            username: email("restaurant", ownerIdx),
            password: PASSWORD,
            csrfmiddlewaretoken: csrf!,
            next: "/en/",
          },
          headers: {
            "X-CSRFToken": csrf!,
            Referer: loginUrl,
            Origin: BASE,
          },
        });
        if (!loginRes.ok()) {
          throw new Error(
            `owner login ${j}: HTTP ${loginRes.status()} ${await loginRes.text()}`,
          );
        }
        const sess = (await context.cookies()).find(
          (c) => c.name === "sessionid",
        );
        expect(sess, `owner session established ${j}`).toBeTruthy();
        csrf = (await context.cookies()).find(
          (c) => c.name === "csrftoken",
        )?.value;
        const mark = await context.request.post(
          `${BASE}/en/orders/mark-as-out/${id}/`,
          {
            form: { csrfmiddlewaretoken: csrf! },
            headers: {
              "X-CSRFToken": csrf!,
              Referer: `${BASE}/en/restaurants/dashboard/`,
              Origin: BASE,
            },
          },
        );
        if (!mark.ok()) {
          throw new Error(
            `mark-out order ${id}: HTTP ${mark.status()} ${await mark.text()}`,
          );
        }
      } finally {
        await context.close();
      }
    });

    // 2) The matching drivers accept & complete their order's delivery.
    const delivered = await chunked(end - start, WRITE_CONC, async (k) => {
      const j = start + k;
      const { id, driver } = ordersByIndex[j];
      const headers = auth(state.driverTokens[driver]);
      const avail = await request.get(`${BASE}/api/deliveries/available/`, {
        headers,
      });
      if (!avail.ok()) throw new Error(`available ${j}: HTTP ${avail.status()}`);
      const list = (await avail.json()) as any[];
      const delivery = list.find((d: any) => d.order === id);
      if (!delivery) {
        throw new Error(`no searching delivery for order ${id} (got ${list.length})`);
      }
      const acceptRes = await request.post(
        `${BASE}/api/deliveries/${delivery.id}/accept/`,
        { headers },
      );
      if (!acceptRes.ok()) {
        throw new Error(
          `accept delivery ${delivery.id}: HTTP ${acceptRes.status()} ${await acceptRes.text()}`,
        );
      }
      const completeRes = await request.post(
        `${BASE}/api/deliveries/${delivery.id}/complete/`,
        { headers },
      );
      if (!completeRes.ok()) {
        throw new Error(
          `complete delivery ${delivery.id}: HTTP ${completeRes.status()} ${await completeRes.text()}`,
        );
      }
      return delivery.id;
    });
    expect(delivered).toHaveLength(end - start);
  }
});

test("all 1000 orders reach Delivered", async ({ request }) => {
  const statuses = await chunked(M, 25, async (j) => {
    return (await getOrder(request, ordersByIndex[j].id, state.customerTokens[j % N])).status;
  });
  for (let j = 0; j < M; j++) {
    expect(statuses[j], `order ${ordersByIndex[j].id} status`).toBe("Delivered");
  }
});

test("admin verifies 1000 payments, deliveries and commissions", async ({
  request,
}) => {
  const headers = auth(state.adminToken);
  const payments = await collectAll(request, `${BASE}/api/payments/`, headers);
  const deliveries = await collectAll(request, `${BASE}/api/deliveries/`, headers);
  const commissions = await collectAll(request, `${BASE}/api/commissions/`, headers);
  expect(payments.length, "payment rows").toBeGreaterThanOrEqual(M);
  expect(deliveries.length, "delivery rows").toBeGreaterThanOrEqual(M);
  expect(commissions.length, "commission rows").toBeGreaterThanOrEqual(M);
  for (const o of ordersByIndex) {
    const pay = payments.find((p: any) => p.order_id_display === o.id);
    expect(pay, `payment for order ${o.id}`).toBeTruthy();
    expect(pay!.payment_method).toBe("Cash");
    expect(pay!.status).toBe("Pending");
    expect(Number(pay!.amount)).toBeCloseTo(Number(o.total), 2);
    const dlv = deliveries.find((d: any) => d.order === o.id);
    expect(dlv, `delivery for order ${o.id}`).toBeTruthy();
    expect(dlv!.status).toBe("delivered");
    expect(dlv!.delivery_person).toBeTruthy();
    const restComm = commissions.find(
      (c: any) => c.commission_type === "restaurant" && c.order === o.id,
    );
    expect(restComm, `restaurant commission for order ${o.id}`).toBeTruthy();
    expect(restComm!.is_settled).toBe(false);
    // Delivery commissions are linked via the `delivery` FK (order is null).
    const delComm = commissions.find(
      (c: any) => c.commission_type === "delivery" && c.delivery === dlv!.id,
    );
    expect(delComm, `delivery commission for order ${o.id}`).toBeTruthy();
    expect(delComm!.is_settled).toBe(false);
  }
});

test("browser walkthrough: pay, owner marks out, driver delivers, customer tracks", async ({
  browser,
  request,
}) => {
  const w = 0; // first order's owner/driver/customer
  const custTok = state.customerTokens[w];
  const check = await request.post(`${BASE}/api/orders/checkout/`, {
    headers: auth(custTok),
    data: {
      restaurant_id: state.owners[w].restId,
      delivery_address: "Walkthrough Street, Damascus",
      delivery_lat: LAT,
      delivery_lng: LNG,
      customer_name: "Walkthrough",
      customer_phone: "0910000000",
      items: [{ menu_item_id: state.owners[w].itemId, quantity: 1 }],
    },
  });
  expect(check.status(), "walkthrough checkout - HTTP 201").toBe(201);
  const order = await check.json();

  // 1) Pay it via the real web UI (Cash radio + confirm button).
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    await page.goto(`${BASE}/en/payments/process/${order.id}/`, {
      waitUntil: "domcontentloaded",
    });
    await page.locator('input[name="payment_method"][value="Cash"]').check();
    await page.locator("#pay-btn").click();
    await expect(page.locator("body")).toContainText(/Order Confirmed|تم تأكيد الطلب/, {
      timeout: 30000,
    });
  } finally {
    await context.close();
  }
  expect((await getOrder(request, order.id, custTok)).status).toBe("Confirmed");

  // 2) Owner marks out via the real button.
  const ownerCtx = await browser.newContext();
  try {
    const page = await ownerCtx.newPage();
    const loginUrl = `${BASE}/en/accounts/login/`;
    await page.goto(loginUrl, { waitUntil: "domcontentloaded" });
    const csrf0 = (await ownerCtx.cookies()).find(
      (c) => c.name === "csrftoken",
    )?.value!;
    await ownerCtx.request.post(loginUrl, {
      form: {
        username: email("restaurant", w),
        password: PASSWORD,
        csrfmiddlewaretoken: csrf0,
        next: "/en/",
      },
      headers: { "X-CSRFToken": csrf0, Referer: loginUrl, Origin: BASE },
    });
    await page.goto(`${BASE}/en/restaurants/dashboard/`, {
      waitUntil: "domcontentloaded",
    });
    const markForm = page.locator(
      `form[action*="/en/orders/mark-as-out/${order.id}/"]`,
    );
    await expect(markForm, "dashboard shows mark-as-out form").toBeVisible({
      timeout: 30000,
    });
    await markForm.locator('button[type="submit"]').click();
    await expect(page.locator("body")).toContainText(
      /بالطريق|On the Way|Out for Delivery|خرج للتوصيل/,
      { timeout: 30000 },
    );
  } finally {
    await ownerCtx.close();
  }
  expect((await getOrder(request, order.id, custTok)).status).toBe("Out");

  // 3) A driver accepts & completes the delivery.
  const dlvList = await request.get(`${BASE}/api/deliveries/available/`, {
    headers: auth(state.driverTokens[w]),
  });
  const dlv = ((await dlvList.json()) as any[]).find(
    (d: any) => d.order === order.id,
  );
  expect(dlv, "delivery created for walkthrough order").toBeTruthy();
  const accept = await request.post(
    `${BASE}/api/deliveries/${dlv!.id}/accept/`,
    { headers: auth(state.driverTokens[w]) },
  );
  expect(accept.ok()).toBeTruthy();
  const complete = await request.post(
    `${BASE}/api/deliveries/${dlv!.id}/complete/`,
    { headers: auth(state.driverTokens[w]) },
  );
  expect(complete.ok()).toBeTruthy();
  expect((await getOrder(request, order.id, custTok)).status).toBe("Delivered");

  // 4) Customer sees the delivered order on the track-orders page.
  const custCtx = await browser.newContext();
  try {
    const page = await custCtx.newPage();
    const loginUrl = `${BASE}/en/accounts/login/`;
    await page.goto(loginUrl, { waitUntil: "domcontentloaded" });
    const csrf = (await custCtx.cookies()).find(
      (c) => c.name === "csrftoken",
    )?.value!;
    await custCtx.request.post(loginUrl, {
      form: {
        username: email("customer", w),
        password: PASSWORD,
        csrfmiddlewaretoken: csrf,
        next: "/en/",
      },
      headers: { "X-CSRFToken": csrf, Referer: loginUrl, Origin: BASE },
    });
    await page.goto(`${BASE}/en/orders/status/`, { waitUntil: "domcontentloaded" });
    const card = page
      .locator("div, article, section", { hasText: `#${order.id}` })
      .first();
    await expect(card).toContainText("Delivered", { timeout: 30000 });
  } finally {
    await custCtx.close();
  }
});
