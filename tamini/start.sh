#!/usr/bin/env sh
set -e
cd tamini

python manage.py collectstatic --noinput
python manage.py migrate
python manage.py ensure_superuser
python manage.py seed_data

# Wait (briefly) for Redis so the cache + Channels layer connect across
# workers. If Redis never comes up we still boot: settings/base.py falls
# back to in-memory cache/channel layers (single-process only).
if [ -n "${REDIS_URL:-}" ]; then
  echo "[start.sh] Waiting for Redis at ${REDIS_URL} ..."
  python - "${REDIS_URL}" <<'PY' || echo "[start.sh] Redis unavailable — continuing with in-memory fallback (see tamini/settings/base.py)."
import os
import sys
import time

import redis

url = sys.argv[1]
client = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
attempts = int(os.environ.get('REDIS_WAIT_ATTEMPTS', '10'))
ok = False
for _ in range(attempts):
    try:
        client.ping()
        ok = True
        break
    except Exception:
        time.sleep(1)
print('[start.sh] Redis is reachable.' if ok else '[start.sh] Redis unavailable.', flush=True)
sys.exit(0 if ok else 1)
PY
fi

# uvicorn worker handles HTTP + WebSockets, so one server is enough.
# Scale with GUNICORN_WORKERS (default 2). Keep Redis running so the
# channel layer + cache work across workers (see tamini/settings/base.py).
exec gunicorn tamini.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  -w ${GUNICORN_WORKERS:-4} \
  --timeout 60 \
  --graceful-timeout 30 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  -b 0.0.0.0:${PORT:-8000}
