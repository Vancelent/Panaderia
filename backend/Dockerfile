FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# No correr como root dentro del contenedor
RUN useradd --create-home --uid 1000 panaderia && chown -R panaderia /app
USER panaderia

EXPOSE 8000

# Migra y levanta la API. En desarrollo el compose agrega --reload.
CMD ["sh", "-c", "python -m app.db.migrate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
