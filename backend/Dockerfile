FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# No correr como root dentro del contenedor
RUN useradd --create-home --uid 1000 panaderia

# Primero solo las dependencias: mientras no cambien, esta capa queda en caché
COPY requirements.txt .
RUN pip install -r requirements.txt

# --chown evita una capa extra con todo el código duplicado (un `chown -R` la duplicaría)
COPY --chown=panaderia:panaderia . .
USER panaderia

EXPOSE 8000

# Migra y levanta la API. En desarrollo el compose agrega --reload; en producción
# docker-compose.prod.yml reemplaza este comando (1 worker, proxy de confianza, sin access log).
CMD ["sh", "-c", "python -m app.db.migrate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
