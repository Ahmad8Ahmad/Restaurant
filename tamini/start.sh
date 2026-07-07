cd tamini
python manage.py migrate
python manage.py ensure_superuser
python manage.py seed_data
daphne -b 0.0.0.0 -p $PORT tamini.asgi:application
