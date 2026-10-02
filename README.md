# Panadería · Gestión y caja

Sistema de gestión para panadería: punto de venta con arqueo ciego, pedidos/comandas,
producción con recetas (escandallo), stock de mostrador e insumos, clientes, compras,
gastos y tablero financiero.

| Capa | Stack |
|---|---|
| Backend | FastAPI · SQLAlchemy 2 · PostgreSQL 15 · Alembic · PyJWT · bcrypt |
| Frontend | React 19 · Vite · Tailwind CSS · TanStack Query · React Router |
| Infra | Docker Compose · Caddy · Cloudflare Tunnel (producción) |

## Puesta en marcha

```bash
cp .env.example .env        # y completá POSTGRES_PASSWORD y JWT_SECRET
docker compose up -d --build
docker compose exec web python -m app.cli crear-admin <usuario>
```

- App: http://localhost:5173 (Vite reenvía `/api` al backend)
- Documentación de la API: http://localhost:8000/api/docs (deshabilitada con `ENV=production`)

Las migraciones se aplican solas al arrancar el contenedor `web`. Una base creada con la
versión anterior (sin Alembic) se detecta y se migra conservando los datos.

### Producción

Un VPS de 1 vCPU / 1 GB con dominio propio, publicado por Cloudflare Tunnel (sin puertos abiertos):

```bash
cp .env.example .env        # POSTGRES_PASSWORD, JWT_SECRET y CLOUDFLARE_TUNNEL_TOKEN
docker compose -f docker-compose.prod.yml --profile tunnel up -d --build
docker compose -f docker-compose.prod.yml exec api python -m app.cli crear-admin <usuario>
```

Cuatro contenedores con límites de memoria (PostgreSQL afinado, API con 1 worker, Caddy y `cloudflared`),
respaldos diarios verificados y tareas programadas. Guía completa (servidor, dominio, Cloudflare,
respaldos, restauración y cómo probarlo en tu PC): [`docs/despliegue.md`](docs/despliegue.md).

### Desarrollo sin Docker

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Windows
export DATABASE_URL=postgresql://user:pass@localhost:5433/erp_panaderia JWT_SECRET=...
python -m app.db.migrate && uvicorn app.main:app --reload

cd frontend && npm install && npm run dev
```

Datos de ejemplo (solo sobre una base **vacía**): `python -m scripts.seed_demo`
(usuarios `admin`, `pamela`, `palala`; contraseña `demo-1234`).

## Tests y calidad

```bash
cd backend
pytest                                   # SQLite temporal (los tests de PostgreSQL se omiten)
TEST_DATABASE_URL=postgresql://... pytest  # Postgres (incluye test de concurrencia)
ruff check app tests
alembic check                            # modelos == migraciones

cd frontend
npm run lint && npm run build
```

## Arquitectura

```
backend/app/
  core/       config (variables de entorno), seguridad, errores, rate limit
  db/         engine/sesión, tipos base, migrate (arranque)
  models/     tablas SQLAlchemy
  schemas/    validación de entrada/salida (Pydantic)
  services/   reglas de negocio (caja, stock, producción, pedidos, finanzas)
  api/v1/     routers HTTP delgados: autenticación, rol y delegación al servicio
frontend/src/
  lib/        cliente HTTP (CSRF), queries, formato, roles
  auth/       sesión y guardas de ruta
  components/ UI compartida y layout
  features/   una carpeta por pantalla (pos, pedidos, produccion, stock, clientes, admin)
```

Todas las respuestas de error tienen la forma `{"error": {"code", "message", "details"}}`.

## Roles

| Rol | Acceso |
|---|---|
| Admin | Todo, incluida la gestión de usuarios |
| Encargada | Todo excepto usuarios: tablero, arqueos, productos, compras, gastos |
| Vendedora | Caja, pedidos (crear, cobrar), clientes, stock (lectura), mermas |
| Panadero | Producción, pedidos (mover estados), stock (lectura), mermas |
| Repartidor | Solo su hoja de ruta (vista de lectura en la web; entregas y cobros desde la app móvil) |

La autorización se aplica en el backend; el frontend solo adapta la navegación.

## Seguridad

- Sesión en cookie `httpOnly` + `SameSite=Strict`, con token CSRF *double-submit* en cada escritura.
- JWT firmado con `JWT_SECRET` (obligatorio, ≥ 32 caracteres). Cambiar la contraseña,
  desactivar un usuario o cambiarle el rol invalida sus sesiones abiertas.
- Límite de intentos de login por IP y usuario.
- Arqueo ciego: el cajero declara el efectivo contado y nunca ve la diferencia.
- Montos en `NUMERIC`; el precio de cada venta lo calcula el servidor.
- Bloqueo de filas (`SELECT … FOR UPDATE`) al mover stock: dos cajas no pueden vender la misma unidad.
- En producción (`docker-compose.prod.yml`): `ENV=production`, cookies `__Host-` y `Secure`, Caddy sirviendo
  el build y `/api` en el mismo origen con CSP estricta, base de datos en una red sin salida a Internet y
  sin documentación de la API. Detalle en [`docs/despliegue.md`](docs/despliegue.md#9-cómo-se-protege).
