"""Quick load test — simulates concurrent users hitting key endpoints."""
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.error

BASE = "https://tamini.onrender.com"
ENDPOINTS = [
    "/",
    "/en/restaurants/",
    "/en/restaurants/menu/1/",
    "/en/orders/cart/",
    "/en/accounts/login/",
]

def fetch(url):
    start = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LoadTest/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            elapsed = time.time() - start
            return (url, resp.status, elapsed, None)
    except Exception as e:
        elapsed = time.time() - start
        return (url, 0, elapsed, str(e))

def run(concurrency=20, requests=100):
    total = requests
    done = 0
    times = []
    errors = []
    start = time.time()

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = []
        for _ in range(requests):
            ep = ENDPOINTS[_ % len(ENDPOINTS)]
            futs.append(ex.submit(fetch, BASE + ep))
        for f in as_completed(futs):
            url, status, elapsed, err = f.result()
            done += 1
            times.append(elapsed)
            if err:
                errors.append((url, err))
            sys.stdout.write(f"\r{done}/{total}  avg={sum(times)/len(times):.2f}s  errors={len(errors)}")
            sys.stdout.flush()

    wall = time.time() - start
    print()
    print(f"\n=== Results ===")
    print(f"Requests:     {total}")
    print(f"Concurrency:  {concurrency}")
    print(f"Wall time:    {wall:.1f}s")
    print(f"Throughput:   {total/wall:.1f} req/s")
    print(f"Avg latency:  {sum(times)/len(times)*1000:.0f}ms")
    print(f"Min latency:  {min(times)*1000:.0f}ms")
    print(f"Max latency:  {max(times)*1000:.0f}ms")
    print(f"p50 latency:  {sorted(times)[len(times)//2]*1000:.0f}ms")
    print(f"p95 latency:  {sorted(times)[int(len(times)*0.95)]*1000:.0f}ms")
    print(f"p99 latency:  {sorted(times)[int(len(times)*0.99)]*1000:.0f}ms")
    print(f"Errors:       {len(errors)}")
    for url, err in errors[:5]:
        print(f"  {url}: {err}")

if __name__ == "__main__":
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    requests = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    run(concurrency, requests)
