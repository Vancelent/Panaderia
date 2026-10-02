# syntax=docker/dockerfile:1
#
# Imagen del contenedor `web`: compila el frontend y lo sirve con Caddy. En producción no queda
# Node corriendo (docs/rfc-001 §7.2). El contexto de build es la raíz del repositorio:
#
#     docker build -f deploy/web.Dockerfile -t panaderia-web .

# ---- Etapa 1: compilar el frontend -------------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# Primero solo las dependencias: mientras no cambien, esta capa queda en caché
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---- Etapa 2: Caddy con el build estático ------------------------------------------------------
FROM caddy:2-alpine

COPY --from=build /app/dist /srv
# Valor por defecto; el compose lo reemplaza montando deploy/Caddyfile (así se edita sin recompilar)
COPY deploy/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80
