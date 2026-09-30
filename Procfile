web: gunicorn config.wsgi --log-file - --workers 3 --timeout 60
worker: celery -A config worker --loglevel=info
