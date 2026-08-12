cd tamini
python manage.py migrate
python manage.py ensure_superuser
python manage.py seed_data
# uvicorn worker handles HTTP + WebSockets, so one server is enough.
# Scale with GUNICORN_WORKERS (default 2). Keep Redis running so the
# channel layer + cache work across workers (see tamini/settings/base.py).
exec gunicorn tamini.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  -w ${GUNICORN_WORKERS:-2} \
  --timeout 60 \
  --graceful-timeout 30 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  -b 0.0.0.0:${PORT:-8000}
