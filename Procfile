web: python manage.py migrate --noinput && gunicorn --bind 0.0.0.0:$PORT --workers 1 --max-requests 100 --max-requests-jitter 10 --timeout 120 --preload greenwatts.wsgi:application
