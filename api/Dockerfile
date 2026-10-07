FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Swagger UI assets served by the API itself, so /docs works offline or behind a CDN-blocking
# firewall (FastAPI's default loads them from cdn.jsdelivr.net at view time).
ARG SWAGGER_UI_VERSION=5.17.14
RUN mkdir -p /opt/swagger-ui && python -c "import urllib.request as u; [u.urlretrieve( \
      f'https://cdn.jsdelivr.net/npm/swagger-ui-dist@${SWAGGER_UI_VERSION}/{f}', f'/opt/swagger-ui/{f}') \
      for f in ('swagger-ui-bundle.js', 'swagger-ui.css')]"

COPY . .

# Non-root user: the API never needs to write to its own filesystem.
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
# Migrations run from empty on every start; Alembic makes this a no-op when up to date.
# --no-access-log: uvicorn's access log prints query strings, which can contain a patient name (q=...).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
