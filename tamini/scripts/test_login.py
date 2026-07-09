import requests, re

BASE = 'https://tamini-605z.onrender.com'
s = requests.Session()

r = s.get(f'{BASE}/en/accounts/login/')
match = re.search(r'csrfmiddlewaretoken" value="([^"]+)"', r.text)
if not match:
    print('NO CSRF TOKEN FOUND')
    exit(1)

csrf = match.group(1)
print(f'CSRF: {csrf[:30]}...')

r2 = s.post(f'{BASE}/en/accounts/login/', data={
    'csrfmiddlewaretoken': csrf,
    'username': 'customer@test.com',
    'password': 'Test@123',
    'next': '/en/'
}, headers={'Referer': f'{BASE}/en/accounts/login/'})

print(f'Status: {r2.status_code}')
print(f'URL: {r2.url}')

if '/login' in r2.url:
    # Try to find error messages in the response
    for pattern in [r'error[^>]*>([^<]+)', r'alert[^>]*>([^<]+)', r'class="[^"]*text-red[^"]*"[^>]*>([^<]+)']:
        m = re.search(pattern, r2.text)
        if m:
            print(f'ERROR FOUND: {m.group(1).strip()}')
            break
    else:
        print('No error pattern found - checking HTML...')
        # Look for the errorlist or non-field errors
        nl = re.search(r'<ul class="errorlist[^"]*"[^>]*>(.*?)</ul>', r2.text, re.DOTALL)
        if nl:
            print(f'Error list: {nl.group(1)}')
else:
    print('LOGIN SUCCESS!')
    print(f'Redirected to: {r2.url}')
