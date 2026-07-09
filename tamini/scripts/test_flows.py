import sys, time
from playwright.sync_api import sync_playwright

BASE = 'https://tamini.onrender.com'
PW = 'Test@123'
PW_SU = 'admin123'
PW_DELIVERY1 = 'Ahmad0944043511'
PW_DELIVERY2 = 'Rand1234567890'

def log(msg):
    print(f'  {msg}')
    sys.stdout.flush()

def ok():
    print('    ✓')

def fail(msg='FAILED'):
    print(f'    ✗ {msg}')

def login(page, email, password=PW):
    page.goto(f'{BASE}/en/accounts/login/')
    page.wait_for_timeout(1000)
    page.fill('input[name="username"]', email)
    page.fill('input[name="password"]', password)
    log(f'Filled form: {email}')
    with page.expect_navigation(timeout=15000):
        page.get_by_role("button", name="Login").click()
    log(f'Post-login URL: {page.url}')
    # Check for Django error messages
    error_text = page.locator('.error, .alert, [role="alert"], .text-red-500, p.text-red, li.text-red').first
    if error_text.count():
        log(f'Page error: {error_text.text_content()[:150]}')
    if page.url.rstrip('/').endswith('/login'):
        fail(f'Login failed for {email}')
        return False
    ok()
    return True

def add_to_cart(page, menu_url):
    page.goto(menu_url)
    page.wait_for_timeout(3000)
    add_btn = page.get_by_role("button", name="Add").first
    if add_btn.count() > 0:
        add_btn.click()
        page.wait_for_timeout(2000)
        log('Added item to cart')
        ok()
        return True
    else:
        fail('No add-to-cart buttons found')
        return False

def test_homepage(page):
    print('\n=== 1. HOMEPAGE ===')
    page.goto(BASE)
    page.wait_for_timeout(2000)
    ok()

def test_customer_full_flow(page, user='customer@test.com', password=PW):
    print('\n=== 2. CUSTOMER FLOW ===')

    # Login
    if not login(page, user, password):
        return

    # Browse restaurants
    page.goto(f'{BASE}/en/restaurants/')
    page.wait_for_timeout(2000)
    log('Restaurants page loaded')
    ok()

    # Find and click first restaurant (link with ID like /restaurants/1/)
    restaurant_links = page.locator('a[href*="/restaurants/"]').filter(has_text=re.compile(r'\d+'))
    count = restaurant_links.count()
    if count == 0:
        # Fallback: find any non-nav restaurant link
        restaurant_links = page.locator('a[href*="/restaurants/"]').filter(has_not_text=re.compile(r'(dashboard|admin|add|search|menu|home)'))
        count = restaurant_links.count()
    if count > 0:
        href = restaurant_links.first.get_attribute('href')
        log(f'Found restaurant link: {href}')
        page.goto(f'{BASE}{href}' if href.startswith('/') else href)
        page.wait_for_timeout(2000)
        log('Restaurant menu page loaded')
        ok()

        # Add item to cart
        log('Looking for add-to-cart buttons...')
        add_to_cart(page, page.url)

        # View cart
        page.goto(f'{BASE}/en/orders/cart/')
        page.wait_for_timeout(3000)
        log(f'Cart page: {page.title()}')

        # Check if checkout form exists (cart has items)
        name_field = page.locator('input[name="customer_name"]')
        if name_field.count() == 0:
            log('Cart empty or checkout form not found - skipping checkout')
            # Try to add via direct POST
            token = page.locator('input[name="csrfmiddlewaretoken"]').first
            if token.count():
                page.goto(f'{BASE}/en/orders/cart/')
                page.wait_for_timeout(2000)
                name_field = page.locator('input[name="customer_name"]')
                if name_field.count() == 0:
                    fail('Still no checkout form - order data may have been created via seed_data')
                    return

        name_field.fill('عميل تجربة')
        page.fill('input[name="customer_phone"]', '0933000001')
        page.fill('input[name="customer_email"]', 'customer@test.com')
        page.fill('input[name="delivery_address"]', 'دمشق, المزة, شارع 29 أيار')
        try:
            page.evaluate('document.getElementById("delivery-lat").value = "33.5100"')
            page.evaluate('document.getElementById("delivery-lng").value = "36.2700"')
        except:
            pass
        log('Checkout form filled')
        ok()

        # Submit checkout via JS form submit (bypasses any JS interceptors)
        page.evaluate('document.getElementById("checkout-btn").form.submit()')
        page.wait_for_timeout(5000)
        log(f'After checkout URL: {page.url}')

        # Handle payment page
        current = page.url
        if 'process' in current or 'payments' in current:
            cash = page.locator('input[name="payment_method"][value="Cash"]')
            if cash.count():
                cash.click()
                confirm_btn = page.get_by_role("button", name="تأكيد").first
                if confirm_btn.count():
                    confirm_btn.click()
                    page.wait_for_timeout(3000)
                    log(f'After payment: {page.url}')
                ok()
            else:
                log('No Cash option found')
        else:
            log(f'No payment page (redirected to {current})')
            ok()

        # Check order status
        page.goto(f'{BASE}/en/orders/status/')
        page.wait_for_timeout(2000)
        log(f'Order status page: {page.title()}')
        ok()
    else:
        fail('No restaurants found. Run seed_data on Render first!')

def test_restaurant_flow(page):
    print('\n=== 3. RESTAURANT FLOW ===')

    if not login(page, 'ahmad19.8722.2@gmail.com', PW_SU):
        return

    page.goto(f'{BASE}/en/restaurants/dashboard/')
    page.wait_for_timeout(3000)
    log(f'Dashboard loaded: {page.title()}')

    has_dash = 'dashboard' in page.url.lower()
    if has_dash:
        ok()
    else:
        fail('Dashboard not accessible')

    # Check for order tabs
    orders_tab = page.locator('#orders-list-view, .tab-btn:has-text("طلبات"), .tab-btn:has-text("Orders")')
    if orders_tab.count():
        orders_tab.first.click()
        page.wait_for_timeout(1000)
        log('Orders tab clicked')
        ok()
    else:
        log('No orders tab found (may not have orders)')

    # Check menu tab
    menu_tab = page.locator('#menu-view, .tab-btn:has-text("قائمة"), .tab-btn:has-text("Menu")')
    if menu_tab.count():
        menu_tab.first.click()
        page.wait_for_timeout(1000)
        log('Menu tab exists')
        ok()
    else:
        log('Menu items tab not found')

def test_delivery_flow(page):
    print('\n=== 4. DELIVERY FLOW ===')

    if not login(page, 'taminyfood@gmail.com', PW_DELIVERY1):
        if not login(page, 'taminyfood@gmail.com', PW_DELIVERY2):
            return

    page.goto(f'{BASE}/en/delivery/available/')
    page.wait_for_timeout(3000)
    log(f'Available orders page: {page.title()}')

    if 'available' in page.url.lower():
        ok()
    else:
        fail('Available orders page not accessible')

    order_cards = page.locator('[id^="order-card-"], form button[type="submit"]:has-text("قبول")')
    if order_cards.count():
        order_cards.first.click()
        page.wait_for_timeout(2000)
        log('Accepted an order')
        ok()
    else:
        log('No available orders to accept (need an active order)')

    page.goto(f'{BASE}/en/delivery/finance/')
    page.wait_for_timeout(2000)
    log(f'Finance page: {page.title()}')
    ok()

def test_admin_flow(page):
    print('\n=== 5. ADMIN FLOW ===')

    if not login(page, 'ahmad19.8722.2@gmail.com', PW_SU):
        return

    page.goto(f'{BASE}/en/restaurants/admin-dashboard/')
    page.wait_for_timeout(3000)
    log(f'Admin dashboard: {page.title()}')

    if 'admin' in page.url.lower() or 'dashboard' in page.url.lower():
        ok()
    else:
        fail('Admin dashboard not accessible')

    page.goto(f'{BASE}/admin/')
    page.wait_for_timeout(2000)
    log(f'Django admin: {page.title()}')
    if 'admin' in page.url.lower():
        ok()
    else:
        fail('Django admin not accessible')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    import re

    print('=' * 60)
    print('TAMINI — Full Site Test')
    print(f'URL: {BASE}')
    print('Prerequisite: Run `cd tamini && python manage.py seed_data` on Render Shell')
    print('=' * 60)

    ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()

    try:
        test_homepage(page)
        test_customer_full_flow(page, user='ahmad19.8722.2@gmail.com', password=PW_SU)
        test_restaurant_flow(page)
        test_delivery_flow(page)
        test_admin_flow(page)
    except Exception as e:
        print(f'\n  ERROR: {e}')
        import traceback
        traceback.print_exc()

    browser.close()
    print('\n=== ALL TESTS COMPLETE ===')
