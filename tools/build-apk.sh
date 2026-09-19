#!/usr/bin/env bash
#
# Compila el APK con la IP del servidor embebida, usando Flutter en Docker.
#
# Equivalente en Linux de `build-apk.ps1`. Existe para que no se olvide ningun volumen. Los tres
# son necesarios y cada uno resuelve un problema distinto:
#
#   demoeca_pubcache -> /root/.pub-cache   Sin el, `flutter analyze` en la siguiente invocacion
#                                          reporta ~200 errores de "package no existe": el cache
#                                          de pub vive dentro del contenedor y se pierde al salir.
#
#   demoeca_gradle   -> /root/.gradle      Sin el, cada build vuelve a descargar la cadena de
#                                          Android entera (~10 minutos en lugar de 3).
#
#   demoeca_android  -> /root/.android     **El importante para poder instalar.** Contiene el
#                                          debug.keystore. La imagen de Flutter no trae uno, asi
#                                          que Gradle lo genera al vuelo y se descarta al
#                                          terminar: cada APK quedaba firmado con una clave
#                                          distinta y Android rechazaba instalarlo encima del
#                                          anterior con INSTALL_FAILED_UPDATE_INCOMPATIBLE.
#
# Uso:
#   ./tools/build-apk.sh                    # detecta la IP publica del servidor
#   ./tools/build-apk.sh 72.60.112.93       # o se le pasa explicita
#   ./tools/build-apk.sh 72.60.112.93 release
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mobile="$repo/mobile"
image='ghcr.io/cirruslabs/flutter:stable'

[[ -f "$mobile/pubspec.yaml" ]] || { echo "No se encontro el proyecto Flutter en $mobile" >&2; exit 1; }

# --- IP ----------------------------------------------------------------------
host_ip="${1:-}"
if [[ -z "$host_ip" ]]; then
    host_ip="$(ip -4 -o route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || true)"
fi
[[ "$host_ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || {
    echo "IP no valida: '$host_ip'. Pasala como argumento." >&2; exit 1; }

# `release` exige un keystore propio de firma; sin configurarlo Gradle firma con el de debug y
# el APK no es distribuible por una tienda, pero si instalable a mano.
mode="${2:-debug}"
[[ "$mode" == "debug" || "$mode" == "release" ]] || { echo "Modo no valido: '$mode'" >&2; exit 1; }

# --- Volumenes ---------------------------------------------------------------
for volume in demoeca_pubcache demoeca_gradle demoeca_android; do
    docker volume create "$volume" >/dev/null
done

# El keystore se genera una sola vez y sobrevive en el volumen. Sin esto la firma cambiaria en
# cada build y la app no se podria actualizar sobre la instalada.
docker run --rm -v demoeca_android:/root/.android "$image" bash -lc '
test -f /root/.android/debug.keystore && exit 0
keytool -genkeypair -v -keystore /root/.android/debug.keystore \
  -storepass android -keypass android -alias androiddebugkey \
  -keyalg RSA -keysize 2048 -validity 10950 \
  -dname "CN=Android Debug, O=Android, C=US" > /dev/null 2>&1
echo "debug.keystore creado"'

# --- Build -------------------------------------------------------------------
echo "Compilando APK ($mode) contra http://${host_ip}:8000 ..."

docker run --rm \
    -v "${mobile}:/app" \
    -v demoeca_pubcache:/root/.pub-cache \
    -v demoeca_gradle:/root/.gradle \
    -v demoeca_android:/root/.android \
    -w /app "$image" \
    bash -lc "git config --global --add safe.directory /app; \
              flutter pub get && \
              flutter build apk --$mode --dart-define=API_BASE_URL=http://${host_ip}:8000 2>&1 | tail -5"

apk="$mobile/build/app/outputs/flutter-apk/app-$mode.apk"
[[ -f "$apk" ]] || { echo 'El build no produjo el APK.' >&2; exit 1; }

# --- Verificacion ------------------------------------------------------------
echo
echo "Huella de firma del APK:"
docker run --rm -v "${mobile}:/app" -w /app "$image" \
    bash -lc "\$(ls -d /opt/android-sdk-linux/build-tools/*/ | tail -1)apksigner verify --print-certs \
              build/app/outputs/flutter-apk/app-$mode.apk 2>/dev/null | grep -i 'SHA-256 digest'" || true

# La IP embebida se comprueba sobre el binario, no se asume: es el fallo mas caro de descubrir
# tarde, porque solo se manifiesta al instalar en el dispositivo.
#
# Hay que mirar DENTRO del ZIP, no con `strings` sobre el .apk: las entradas van comprimidas
# (en debug la URL acaba en assets/flutter_assets/kernel_blob.bin, en release dentro del
# snapshot AOT), asi que un `strings` sobre el fichero suelto no encuentra nada y da un falso
# negativo justo en la comprobacion que mas importa.
echo
echo "URL embebida en el APK:"
python3 - "$apk" "http://${host_ip}:8000" <<'PY'
import sys, zipfile
apk, target = sys.argv[1], sys.argv[2].encode()
hits = []
with zipfile.ZipFile(apk) as z:
    for name in z.namelist():
        try:
            if target in z.read(name):
                hits.append(name)
        except Exception:
            continue
if hits:
    print(f"  OK  {target.decode()} presente en: {', '.join(hits[:3])}")
else:
    print(f"  FALLO: {target.decode()} NO aparece en el APK. Se compilo contra otra URL.")
    sys.exit(1)
PY

size="$(du -h "$apk" | cut -f1)"
cat <<EOF

=========================================================================
 APK listo: $apk
 Tamano:    $size
 Backend:   http://${host_ip}:8000

 Descargalo a tu maquina con:
   scp root@${host_ip}:${apk} .

 Si es la primera vez tras cambiar de servidor, DESINSTALA la version
 anterior antes de instalar: la anterior apuntaba a otra IP.
=========================================================================
EOF
