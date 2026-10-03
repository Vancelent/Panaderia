# Despliegue en producción

Guía para publicar el sistema en un **VPS chico** (1 vCPU, 1 GB de RAM) con **dominio propio** y
**Cloudflare Tunnel**, tal como define la [RFC-001 §7](rfc-001-reparto-produccion-movil.md#7-infraestructura-de-producción-low-cost).
Los archivos que intervienen:

| Archivo | Para qué |
|---|---|
| `docker-compose.prod.yml` | Los 4 contenedores: `db`, `api`, `web` (Caddy) y `cloudflared` (opcional) |
| `deploy/web.Dockerfile` | Compila el frontend y lo sirve con Caddy (no queda Node corriendo) |
| `deploy/Caddyfile` | Sirve el build, reenvía `/api` y pone los encabezados de seguridad |
| `deploy/backup.sh` | Respaldo diario de la base (verificado, rotado, con copia externa) |
| `deploy/restore.sh` | Prueba de restauración sobre una base vacía |
| `deploy/crontab.ejemplo` | Tareas programadas: respaldo, retención GPS, verificaciones |

```
Internet ─▶ Cloudflare ─▶ túnel (saliente) ─▶ cloudflared ─┐
                                                           ▼
                              red "borde"          web (Caddy :80) ─▶ api (uvicorn :8000)
                                                                          │
                                                       red "interna" ◀────┘
                                                       db (PostgreSQL, sin salida a Internet)
```

El VPS **no tiene puertos 80/443 abiertos**: toda la entrada pública es la conexión saliente del túnel.

## 1. Preparar el servidor

Debian 12 o Ubuntu 24.04, 1 vCPU, 1–2 GB de RAM y 20 GB de disco.

```bash
# Docker Engine + plugin Compose (https://docs.docker.com/engine/install/)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER        # cerrar y abrir sesión para que tome efecto

# Swap comprimido (zram): absorbe picos sin matar procesos
sudo apt-get install -y zram-tools && echo -e "ALGO=zstd\nPERCENT=50" | sudo tee /etc/default/zramswap && sudo systemctl restart zramswap

# Firewall del proveedor: SIN puertos entrantes salvo SSH (restringido a tu IP o solo por clave)
```

> **Compilar en un VPS de 1 GB:** `vite build` necesita ~700 MB. Con el zram anterior suele alcanzar;
> si se queda sin memoria, compilá la imagen en otra máquina (`docker build -f deploy/web.Dockerfile -t panaderia-web .`)
> y subila a un registro, o agregá un swapfile temporal de 1 GB.

## 2. Dominio y Cloudflare

1. Registrá el dominio y delegá los DNS a Cloudflare (plan gratuito).
2. En **Zero Trust → Networks → Tunnels** creá un túnel (tipo *Cloudflared*) y copiá su **token**.
3. En el túnel, agregá un **Public hostname**: `app.tudominio.com` → servicio **HTTP** `web:80`
   (el contenedor `cloudflared` comparte red con Caddy, por eso se usa el nombre `web`). Cloudflare crea
   solo el CNAME proxied.
4. Configuración recomendada:

| Área | Configuración |
|---|---|
| SSL/TLS | Modo **Full (strict)**, *Always Use HTTPS*, TLS mínimo 1.2. Activá **HSTS** recién cuando verifiques todo |
| WAF | Reglas administradas gratuitas activadas y una regla propia que bloquee `/api/docs` y `/api/openapi.json` |
| Rate limit en el borde | `/api/v1/auth/*`: 20 solicitudes/min por IP → bloqueo de 10 min |
| Bot Fight Mode | Activado para la web; **excluir** `/api/v1/*` (lo usará la app móvil) |
| Caché | *Bypass* para `/api/*`. `/assets/*` se cachea respetando los encabezados de Caddy (`immutable`) |

## 2 bis. Ingreso con Google

Google exige una URL de retorno **HTTPS pública**, por eso el dominio de la sección 2 es requisito.

1. En [Google Cloud Console](https://console.cloud.google.com/apis/credentials) creá un proyecto y una
   *pantalla de consentimiento* (tipo **Externo** o **Interno** si usás Google Workspace; con ámbitos
   `openid`, `email` y `profile`).
2. Creá unas credenciales **ID de cliente de OAuth → Aplicación web** y registrá como *URI de redireccionamiento
   autorizado*: `https://app.tudominio.com/api/v1/auth/google/callback` (exactamente esa).
3. Copiá el ID y el secreto a `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) y poné
   `OAUTH_REDIRECT_URL=https://app.tudominio.com/api/v1/auth/google/callback`.
4. En **Usuarios**, un administrador carga el **correo** de cada persona. No hay alta automática: solo entran
   las cuentas vinculadas. El primer ingreso con Google cuyo correo (verificado) coincida crea la vinculación.
5. Dejá siempre **al menos un administrador con contraseña**: si Google o Internet fallan, el mostrador sigue
   operando con PIN y la gestión con contraseña.

La app móvil usa sus propios ID de cliente (Android e iOS): van en `GOOGLE_CLIENT_IDS_MOVIL`.

### PIN en la caja

El PIN solo funciona en un **equipo registrado**: un administrador o la encargada abre la caja en la PC del
mostrador y elige **«Registrar este equipo como caja»** (el equipo queda identificado por una cookie que el
servidor reconoce por su hash). Después, en el login de ese equipo aparecen las personas con PIN. Para dejar
de aceptar un equipo, se lo desactiva en **Usuarios → Equipos**: sus sesiones se cierran en el acto.

## 3. Primer despliegue

```bash
sudo mkdir -p /opt/panaderia && sudo chown $USER /opt/panaderia
git clone https://github.com/Vancelent/Panaderia.git /opt/panaderia && cd /opt/panaderia
git checkout modernizacion          # o la rama/etiqueta que corresponda

cp .env.example .env
nano .env                           # ver la tabla de abajo
chmod 600 .env
```

Variables que hay que completar en `.env`:

| Variable | Valor |
|---|---|
| `POSTGRES_PASSWORD` | Una clave larga y aleatoria: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `JWT_SECRET` | Otra distinta, ≥ 32 caracteres: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CLOUDFLARE_TUNNEL_TOKEN` | El token del túnel (paso 2) |
| `PIN_PEPPER` | **Obligatoria** (≥ 32 caracteres): `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. Sin ella la API no arranca. No la cambies después de cargar PIN (habría que cargarlos de nuevo) y guardala junto con los respaldos de la base |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `OAUTH_REDIRECT_URL` | Ingreso con Google (sección 2 bis). Sin ellas el botón de Google no aparece y el sistema funciona con contraseña y PIN |
| `ZONA_HORARIA` | `America/Argentina/Buenos_Aires` (o la del local) |
| `PANADERIA_LATITUD` / `PANADERIA_LONGITUD` | Ubicación del local: es el punto de partida de la ruta sugerida |

El compose de producción ya fija `ENV=production`, `COOKIE_SECURE=true`, `COOKIE_PREFIX=__Host-`,
`DB_POOL_SIZE=4` y `DB_MAX_OVERFLOW=2`. Dejá `CORS_ORIGINS` **vacío**: la web y la API comparten origen.

```bash
docker compose -f docker-compose.prod.yml --profile tunnel up -d --build
docker compose -f docker-compose.prod.yml ps                 # db, api y web en "healthy"
docker compose -f docker-compose.prod.yml logs -f api        # las migraciones se aplican solas

# Primer usuario administrador (pide la contraseña por consola)
docker compose -f docker-compose.prod.yml exec api python -m app.cli crear-admin <usuario>
```

Abrí `https://app.tudominio.com` e ingresá. Para comprobar desde el servidor:

```bash
curl -s http://127.0.0.1:8080/api/health        # {"status":"ok"}  (puerto solo local, no público)
```

Sin el perfil `tunnel` el sistema corre igual, accesible solo en `127.0.0.1:8080` del servidor
(sirve para diagnosticar o para probar la imagen de producción en una máquina cualquiera).

### Probar la imagen de producción en tu PC

Con un archivo de variables aparte, sin tocar tu `.env` de desarrollo:

```bash
cp .env.example .env.prueba         # completá POSTGRES_PASSWORD, JWT_SECRET y PIN_PEPPER
ENV_FILE=.env.prueba docker compose --env-file .env.prueba -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prueba -f docker-compose.prod.yml exec api python -m app.cli crear-admin <usuario>
# → http://localhost:8080
```

Usa el proyecto `panaderia-prod`: no pisa los contenedores ni el volumen del `docker-compose.yml` de
desarrollo. Las cookies no distinguen puertos: no uses a la vez el sistema de desarrollo (`localhost:5173`) y esta
prueba (`localhost:8080`) en el mismo navegador, o se mezclan las cookies de sesión de ambos. Para borrar la prueba (incluida su base): `docker compose -f docker-compose.prod.yml -p panaderia-prod down -v`.

## 4. Actualizar a una versión nueva

```bash
cd /opt/panaderia
deploy/backup.sh                                  # siempre un respaldo antes de actualizar
git pull
VERSION=$(git rev-parse --short HEAD) docker compose -f docker-compose.prod.yml --profile tunnel up -d --build
```

Las migraciones se aplican solas al arrancar `api`. Etiquetar la imagen con `VERSION` permite volver
atrás (`VERSION=<anterior> docker compose … up -d`), siempre que la migración nueva sea compatible
con el código anterior; si no lo es, restaurá el respaldo (sección 6).

## 5. Respaldos

`deploy/backup.sh` hace un `pg_dump -Fc` dentro del contenedor `db`, verifica que el archivo se pueda
leer, rota las últimas 14 copias y, si hay `RCLONE_REMOTE`, lo copia fuera del servidor (un disco que
falla se lleva también los respaldos que tiene al lado).

```bash
# Copia externa con rclone (Backblaze B2, Google Drive, S3, etc.)
curl https://rclone.org/install.sh | sudo bash
rclone config                                    # crear un remoto, p. ej. "b2"

# Programación: copiar y ajustar los valores del ejemplo
sudo mkdir -p /var/log/panaderia /var/backups/panaderia && sudo chown $USER /var/log/panaderia /var/backups/panaderia
crontab -e                                       # pegar deploy/crontab.ejemplo (ajustar REPO, RCLONE_REMOTE…)
```

El ejemplo programa todos los días: respaldo (03:15), retención de la traza GPS (03:30) y las
verificaciones de saldos y de reservas (04:00). El día 1 de cada mes corre la prueba de restauración.
`BACKUP_PING_URL` (por ejemplo un *check* de healthchecks.io) avisa por mail si **no** corrió.

Rotación de los logs del cron (`/etc/logrotate.d/panaderia`):

```
/var/log/panaderia/*.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
}
```

En Proxmox, además, programá un respaldo semanal de la VM o del LXC con `vzdump`.

## 6. Restaurar

### Prueba mensual (no toca producción)

```bash
deploy/restore.sh                      # el último respaldo, en la base temporal "restore_test"
deploy/restore.sh /ruta/archivo.dump   # uno puntual
deploy/restore.sh --conservar          # deja la base de prueba para mirarla con psql
```

Compara los totales de las tablas principales con producción y sale con error si no son coherentes.
**Un respaldo que nunca se restauró no es un respaldo**: hacelo al menos una vez por mes.

### Recuperarse de un desastre (reemplaza producción)

```bash
cd /opt/panaderia
docker compose -f docker-compose.prod.yml stop api web           # nadie escribe mientras se restaura
docker compose -f docker-compose.prod.yml exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE \"$POSTGRES_DB\" WITH (FORCE)" \
   -c "CREATE DATABASE \"$POSTGRES_DB\""'
docker compose -f docker-compose.prod.yml exec -T db sh -c \
  'pg_restore --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < /var/backups/panaderia/panaderia-AAAAMMDD-HHMMSS.dump
docker compose -f docker-compose.prod.yml up -d                   # (agregar --profile tunnel en el VPS)
docker compose -f docker-compose.prod.yml exec api python -m app.cli verificar-saldos
docker compose -f docker-compose.prod.yml exec api python -m app.cli verificar-reservas
```

## 7. Pasar la base de desarrollo a producción

La imagen de producción usa `postgres:15-alpine`, que tiene otra biblioteca de *collation* que la
imagen Debian de desarrollo: **no reutilices el volumen**, pasá los datos con `pg_dump`/`pg_restore`.

```bash
# En la máquina de desarrollo
docker compose exec db sh -c 'pg_dump -Fc --no-owner -U "$POSTGRES_USER" "$POSTGRES_DB"' > panaderia-dev.dump

# En el servidor, con la base de producción recién creada (sin datos)
docker compose -f docker-compose.prod.yml stop api web
docker compose -f docker-compose.prod.yml exec -T db sh -c \
  'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < panaderia-dev.dump
docker compose -f docker-compose.prod.yml up -d
```

Si preferís no migrar, podés dejar `postgres:15` (Debian) en el compose: ocupa ~100 MB más de disco
y usa la misma RAM.

## 8. Alternativas

### Sin túnel (Caddy expuesto con certificado propio)

En un VPS con IP pública se puede prescindir de `cloudflared`: no uses el perfil `tunnel`, quitá
`auto_https off` del `Caddyfile`, cambiá `:80` por tu dominio (`app.tudominio.com { … }`), publicá
`443:443` en el servicio `web` y limitá el firewall a los rangos de IP de Cloudflare (o usá un
certificado *Origin CA*). Ajustá también `trusted_proxies` del `Caddyfile` a esos rangos.

### Proxmox en el local

Una **VM Debian 12** de 1 vCPU / 1,5 GB es lo más simple y estable para Docker. Más liviano: un
**LXC sin privilegios** con `nesting=1` y `keyctl=1` (sobre ZFS puede hacer falta ajustar el driver de
almacenamiento de Docker). Mismo túnel, mismo dominio y mismos pasos que en el VPS. Como el servidor
está en la red del local, la caja también puede entrar por la IP local del puerto `8080` si lo publicás
en la red (en el compose está limitado a `127.0.0.1`).

## 9. Cómo se protege

| Capa | Medida |
|---|---|
| Red | La base está en una red `internal` (sin salida a Internet). Solo `web` publica un puerto, y solo en `127.0.0.1` |
| Entrada | Cloudflare (WAF, límite de intentos, *bot fight*) → túnel saliente. El firewall del VPS no abre 80/443 |
| IP real | Caddy toma `CF-Connecting-IP` solo de conexiones de la red `borde`; uvicorn acepta `X-Forwarded-For` solo de esa red. El límite de login ve la IP verdadera |
| Cookies | `__Host-`, `Secure`, `HttpOnly` (sesión), `SameSite=Strict`, sin `Domain`. CSRF por doble envío |
| Encabezados | CSP estricta (scripts solo del propio origen), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` |
| Contenedores | `no-new-privileges`, sistema de archivos de solo lectura en `api` y `web`, Caddy sin capacidades salvo el puerto 80, usuario no root en la API |
| Documentación de la API | Apagada (`ENV=production`) y bloqueada también en Caddy |
| Datos | `fsync` y `synchronous_commit` activados; respaldo diario verificado y copia externa |

## 10. Verificación

- **Puertos:** desde otra máquina, `nmap -Pn <ip-del-vps> -p 80,443` debe mostrar los puertos cerrados o filtrados, y la app debe responder por `https://app.tudominio.com`.
- **Memoria:** durante un día de uso real (o simulado: varias cajas abiertas y un repartidor enviando posiciones), `docker stats --no-stream`. Presupuesto: `db` 320 MB, `api` 256 MB, `web` 64 MB y `cloudflared` 64 MB (límites duros; el uso típico es ~250–400 MB en total).
- **Restauración:** `deploy/restore.sh` sobre el último respaldo.
- **Consistencia:** `python -m app.cli verificar-saldos` y `verificar-reservas` no deben informar diferencias.
- **Cabeceras:** `curl -sI https://app.tudominio.com | grep -i -E "content-security|x-frame|nosniff"`.
