#!/usr/bin/env bash
# Prueba de restauración (docs/rfc-001 §7.6): restaura un respaldo en una base VACÍA y compara
# sus totales con la base en producción. Se corre al menos una vez por mes: un respaldo que nunca
# se restauró no es un respaldo.
#
# NUNCA toca la base de producción: se niega a restaurar sobre ella. Para recuperarse de un
# desastre de verdad, ver "Restaurar" en docs/despliegue.md.
#
# Uso:
#   deploy/restore.sh                         # el respaldo más nuevo, en la base "restore_test"
#   deploy/restore.sh ARCHIVO.dump            # un respaldo puntual
#   deploy/restore.sh ARCHIVO.dump otra_base  # con otro nombre de base de prueba
#   deploy/restore.sh --conservar             # no borra la base de prueba al terminar (para mirarla con psql)
#
# Variables: BACKUP_DIR (por defecto /var/backups/panaderia), COMPOSE_FILE_PROD.
# Código de salida: 0 = restauró y los totales coinciden · 1 = falló o hay diferencias.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/panaderia}"
COMPOSE_FILE_PROD="${COMPOSE_FILE_PROD:-$REPO/docker-compose.prod.yml}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
fallar() { log "ERROR: $*" >&2; exit 1; }

conservar=0
args=()
for a in "$@"; do
  if [[ "$a" == "--conservar" ]]; then conservar=1; else args+=("$a"); fi
done
archivo="${args[0]:-}"
destino="${args[1]:-restore_test}"

[[ "$destino" =~ ^[a-z_][a-z0-9_]{0,40}$ ]] || fallar "nombre de base inválido: '$destino' (minúsculas, números y _)"
if [[ -z "$archivo" ]]; then
  archivo="$(ls -1t "$BACKUP_DIR"/panaderia-*.dump 2>/dev/null | head -n 1 || true)"
  [[ -n "$archivo" ]] || fallar "no hay respaldos en $BACKUP_DIR"
fi
[[ -r "$archivo" && -s "$archivo" ]] || fallar "no puedo leer el respaldo: $archivo"

cd "$REPO"
compose() { docker compose -f "$COMPOSE_FILE_PROD" "$@"; }
activos="$(compose ps --status running --services 2>/dev/null || true)"
grep -qx db <<< "$activos" || fallar "el contenedor db no está en marcha"

# psql/pg_restore dentro del contenedor, con el usuario de la base (sin contraseña: socket local)
sql() { compose exec -T db sh -c 'PGOPTIONS="-c client_min_messages=warning" psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -At -c "$1"' _ "$1"; }
en_base() { compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -At -c "$2"' _ "$1" "$2"; }

produccion="$(compose exec -T db sh -c 'printf %s "$POSTGRES_DB"')"
[[ "$destino" != "$produccion" ]] || fallar "'$destino' es la base de producción: este script no la toca"

log "Restaurando $(basename "$archivo") en la base '$destino'…"
sql "DROP DATABASE IF EXISTS \"$destino\" WITH (FORCE)" > /dev/null
sql "CREATE DATABASE \"$destino\"" > /dev/null
limpiar() { [[ "$conservar" -eq 1 ]] || sql "DROP DATABASE IF EXISTS \"$destino\" WITH (FORCE)" > /dev/null 2>&1 || true; }
trap limpiar EXIT

compose exec -T db sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1" --exit-on-error' _ "$destino" < "$archivo" \
  || fallar "pg_restore falló"

# Totales de las tablas que importan: producción vs. restaurado. Si el respaldo es de ayer, las
# ventas de hoy no están: lo normal es que el restaurado tenga igual o menos que producción.
tablas=(usuarios productos clientes ventas ventas_pagos turnos arqueos movimientos_cuenta_corriente hojas_ruta entregas)
difiere=0
printf '\n%-32s %12s %12s\n' "tabla" "producción" "restaurado"
for t in "${tablas[@]}"; do
  existe="$(en_base "$destino" "SELECT to_regclass('public.$t') IS NOT NULL")"
  [[ "$existe" == "t" ]] || { printf '%-32s %12s %12s\n' "$t" "-" "(no existe)"; difiere=1; continue; }
  p="$(en_base "$produccion" "SELECT count(*) FROM $t")"
  r="$(en_base "$destino" "SELECT count(*) FROM $t")"
  marca=""
  (( r > p )) && { marca="  <-- más que producción"; difiere=1; }
  printf '%-32s %12s %12s%s\n' "$t" "$p" "$r" "$marca"
done
version="$(en_base "$destino" "SELECT version_num FROM alembic_version")"
printf '\nMigración restaurada: %s\n\n' "$version"

if [[ "$conservar" -eq 1 ]]; then
  log "Base '$destino' conservada. Para mirarla: docker compose -f docker-compose.prod.yml exec db psql -U <usuario> -d $destino"
else
  log "Base de prueba '$destino' eliminada."
fi
[[ "$difiere" -eq 0 ]] || fallar "los totales no son coherentes con producción (ver arriba)"
log "Restauración verificada."
