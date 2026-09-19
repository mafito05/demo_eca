#!/usr/bin/env bash
#
# Configura el stack para servirse desde la IP publica de este servidor.
#
# Equivalente en Linux de `setup-lan-access.ps1`, que fue escrito para desarrollo en Windows
# contra una IP de LAN. El problema que resuelve es el mismo y no se arregla solo cambiando la
# URL del API: las URLs prefirmadas de MinIO **se firman contra un host concreto**, porque la
# firma SigV4 cubre la cabecera Host. Firmadas con `localhost:9000`, el movil intentaria
# conectarse a si mismo y el video no se reproduciria. De ahi que haya que tocar
# MINIO_PUBLIC_ENDPOINT y RECREAR los contenedores: `docker compose restart` NO recarga env_file.
#
# Uso:
#   ./tools/setup-server-access.sh              # detecta la IP publica de la ruta por defecto
#   ./tools/setup-server-access.sh 72.60.112.93 # o se le pasa explicita
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="$repo/.env"

[[ -f "$env_file" ]] || { echo "No existe $env_file. Copia .env.example primero." >&2; exit 1; }

# --- 1. Determinar la IP -----------------------------------------------------
host_ip="${1:-}"
if [[ -z "$host_ip" ]]; then
    # La IP de la interfaz con la ruta por defecto: la que ve el mundo exterior.
    host_ip="$(ip -4 -o route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || true)"
fi
[[ "$host_ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || {
    echo "IP no valida: '$host_ip'. Pasala como argumento." >&2; exit 1; }

echo "IP del servidor: $host_ip"

# --- 2. Parchear el .env -----------------------------------------------------
set_env_line() {
    local key="$1" value="$2"
    if grep -q "^${key}=" "$env_file"; then
        # El valor puede llevar barras y dos puntos: se usa | como delimitador de sed.
        sed -i "s|^${key}=.*|${key}=${value}|" "$env_file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$env_file"
    fi
}

minio_public="${host_ip}:9000"
# El panel servido por Nginx comparte origen con /api (no dispara CORS); las entradas con
# puerto siguen ahi para poder levantar `ng serve` contra este backend.
cors="http://localhost:4200,http://127.0.0.1:4200,http://${host_ip},http://${host_ip}:4200"

cambios=0
for pair in "MINIO_PUBLIC_ENDPOINT=$minio_public" "CORS_ORIGINS=$cors"; do
    key="${pair%%=*}"; value="${pair#*=}"
    actual="$(grep "^${key}=" "$env_file" | head -1 | cut -d= -f2-)" || true
    if [[ "$actual" != "$value" ]]; then
        set_env_line "$key" "$value"
        echo "  $key -> $value"
        cambios=1
    fi
done
[[ $cambios -eq 0 ]] && echo ".env ya estaba configurado para esta IP."

# --- 3. Recrear los contenedores --------------------------------------------
cd "$repo"
echo
echo "Recreando backend y worker (restart NO recarga env_file)..."
docker compose up -d --force-recreate backend worker >/dev/null
sleep 10
echo "backend: $(docker compose ps backend --format '{{.Status}}')"

# --- 4. Comprobar accesibilidad ---------------------------------------------
echo
echo "Comprobando acceso por la IP publica..."
for check in "API|http://${host_ip}:8000/health/ready" \
             "MinIO|http://${host_ip}:9000/minio/health/live" \
             "Panel|http://${host_ip}/"; do
    nombre="${check%%|*}"; url="${check#*|}"
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "$url" || echo 000)"
    if [[ "$code" =~ ^[23] ]]; then
        echo "  OK    $nombre en $url -> HTTP $code"
    else
        echo "  FALLO $nombre en $url -> HTTP $code"
    fi
done

cat <<EOF

=========================================================================
 Listo.

   Panel:   http://${host_ip}
   API:     http://${host_ip}:8000/docs

 Para la app movil:

   ./tools/build-apk.sh ${host_ip}

 IMPORTANTE: la IP queda embebida en el APK. Si cambia la IP del
 servidor, hay que volver a ejecutar este script y recompilar el APK.
=========================================================================
EOF
