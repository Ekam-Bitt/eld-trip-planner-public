FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl ca-certificates \
    libcairo2 libpangocairo-1.0-0 libpango-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend /app

EXPOSE 8000

# Default to gunicorn in production, fall back to dev server if DEBUG=1
ENV WEB_CONCURRENCY=2
CMD ["/bin/sh", "-c", "if [ \"$DEBUG\" = \"1\" ]; then python manage.py runserver 0.0.0.0:8000; else gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY}; fi"]


