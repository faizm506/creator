FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY . .
# Collect static files at build time (the key here is only a placeholder for the build step)
RUN SECRET_KEY=build-only-placeholder-that-is-long-enough-0123456789-abcdefghij DEBUG=False ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz/')"
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi -c gunicorn.conf.py"]
