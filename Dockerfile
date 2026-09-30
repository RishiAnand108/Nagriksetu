# NagrikSetu — production image (Gunicorn + WhiteNoise).
# The same image runs the web process and the Celery worker (see docker-compose.yml).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# DejaVu provides the font used to watermark complaint photos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Static files are collected at build time with production settings; the
# throwaway key and host exist only for this step and are never used at runtime.
RUN SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')" \
    ALLOWED_HOSTS=build.invalid DJANGO_ENV=prod \
    python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/media \
    && chown -R app:app /app/media
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=4)" || exit 1

CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
