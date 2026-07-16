FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend /app/backend

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py ensure_default_admin && python manage.py seed_initial_artworks && python manage.py seed_initial_inspirations && python manage.py seed_commission_options && gunicorn configs.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-60} --max-requests ${GUNICORN_MAX_REQUESTS:-1000} --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER:-100}"]
