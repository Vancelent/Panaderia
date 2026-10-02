#!/usr/bin/env bash
# Respaldo diario de PostgreSQL (docs/rfc-001 §7.6). Pensado para el `cron` del HOST: no hace falta
# ningún contenedor extra.
#
#   - `pg_dump -Fc` (formato custom, comprimido) ejecutado dentro del contenedor `db`
#   - verifica que el archivo se pueda leer (`pg_restore --list`) antes de aceptarlo
#   - rota: conserva las últimas BACKUP_KEEP copias locales (14 por defecto)
#   - copia fuera del servidor con rclone si RCLONE_REMOTE está definido
#   - avisa a un monitor externo (dead-man switch) si BACKUP_PING_URL está definido
#
# Variables (todas opcionales):
#   BACKUP_DIR         destino local            (por defecto /var/backups/panaderia)
#   BACKUP_KEEP        copias locales a guardar (por defecto 14)
#   RCLONE_REMOTE      p. ej. "b2:panaderia-backups" (vacío = sin copia externa)
#   RCLONE_KEEP_DAYS   antigüedad máxima de las copias externas (por defecto 30)
#   BACKUP_PING_URL    URL a la que se hace GET cuando el respaldo terminó bien (healthchecks.io, etc.)
#   COMPOSE_FILE_PROD  archivo compose (por defecto docker-compose.prod.yml en la raíz del repo)
#
# Uso:  deploy/backup.sh
# Código de salida: 0 = respaldo correcto y verificado · distinto de 0 = falló (no se rota nada).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/panaderia}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
RCLONE_KEEP_DAYS="${RCLONE_KEEP_DAYS:-30}"
BACKUP_PING_URL="${BACKUP_PING_URL:-}"
COMPOSE_FILE_PROD="${COMPOSE_FILE_PROD:-$REPO/docker-compose.prod.yml}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
fallar() { log "ERROR: $*" >&2; exit 1; }

[[ "$BACKUP_KEEP" =~ ^[0-9]+$ && "$BACKUP_KEEP" -ge 1 ]] || fallar "BACKUP_KEEP debe ser un entero >= 1"
command -v docker >/dev/null || fallar "docker no está instalado o no está en el PATH"

# docker compose lee el .env de la raíz del repositorio
cd "$REPO"
compose() { docker compose -f "$COMPOSE_FILE_PROD" "$@"; }

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

sello="$(date +%Y%m%d-%H%M%S)"
parcial="$BACKUP_DIR/.panaderia-$sello.dump.partial"
final="$BACKUP_DIR/panaderia-$sello.dump"
carpeta_bloqueo=""
limpiar() { rm -f "$parcial"; [[ -z "$carpeta_bloqueo" ]] || rmdir "$carpeta_bloqueo" 2>/dev/null || true; }
trap limpiar EXIT

# Un solo respaldo a la vez. Con flock (Linux) el bloqueo se libera solo si el proceso muere; sin
# flock (p. ej. Git Bash en Windows) se usa un directorio, que se crea de forma atómica.
if command -v flock >/dev/null; then
  exec 9>"$BACKUP_DIR/.backup.lock"
  flock -n 9 || fallar "ya hay otro respaldo en curso"
else
  mkdir "$BACKUP_DIR/.backup.lock.d" 2>/dev/null     || fallar "ya hay otro respaldo en curso (si no es así, borrá $BACKUP_DIR/.backup.lock.d)"
  carpeta_bloqueo="$BACKUP_DIR/.backup.lock.d"
fi

activos="$(compose ps --status running --services 2>/dev/null || true)"
grep -qx db <<< "$activos" || fallar "el contenedor db no está en marcha"

log "Respaldando la base de datos…"
# POSTGRES_USER / POSTGRES_DB se toman del entorno del contenedor: no hay que leer el .env acá
compose exec -T db sh -c 'pg_dump -Fc --no-owner -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$parcial" \
  || fallar "pg_dump falló"

[[ -s "$parcial" ]] || fallar "el respaldo quedó vacío"
# Verifica que el archivo sea un dump válido y completo (lee su tabla de contenidos)
compose exec -T db pg_restore --list < "$parcial" > /dev/null || fallar "el respaldo no se puede leer (¿corrupto?)"

mv "$parcial" "$final"
chmod 600 "$final"
tamano="$(du -h "$final" | cut -f1)"
log "Respaldo listo: $final ($tamano)"

# Rotación local: se conservan las BACKUP_KEEP más nuevas (solo si el de hoy salió bien)
mapfile -t viejos < <(ls -1t "$BACKUP_DIR"/panaderia-*.dump 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))")
for f in "${viejos[@]}"; do
  rm -f -- "$f"
  log "Rotado: $(basename "$f")"
done

# Copia fuera del servidor: un disco que muere se lleva también los respaldos que tiene al lado
if [[ -n "$RCLONE_REMOTE" ]]; then
  command -v rclone >/dev/null || fallar "RCLONE_REMOTE está definido pero rclone no está instalado"
  log "Copiando a $RCLONE_REMOTE…"
  rclone copy "$final" "$RCLONE_REMOTE" --quiet || fallar "rclone no pudo copiar el respaldo"
  rclone delete "$RCLONE_REMOTE" --min-age "${RCLONE_KEEP_DAYS}d" --include 'panaderia-*.dump' --quiet \
    || log "AVISO: no se pudo rotar el almacenamiento externo"
  log "Copia externa lista."
else
  log "AVISO: sin RCLONE_REMOTE, el respaldo queda solo en este servidor."
fi

if [[ -n "$BACKUP_PING_URL" ]] && command -v curl >/dev/null; then
  curl -fsS -m 10 --retry 2 -o /dev/null "$BACKUP_PING_URL" || log "AVISO: no se pudo avisar al monitor"
fi
log "Terminado."
