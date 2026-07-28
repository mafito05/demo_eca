<#
.SYNOPSIS
    Compila el APK de depuración con la IP del host embebida, usando Flutter en Docker.

.DESCRIPTION
    Existe para que no se olvide ningún volumen. Los tres son necesarios y cada uno resuelve un
    problema distinto:

      demoeca_pubcache -> /root/.pub-cache   Sin él, `flutter analyze` en la siguiente invocación
                                             reporta ~200 errores de "package no existe": el caché
                                             de pub vive dentro del contenedor y se pierde al salir.

      demoeca_gradle   -> /root/.gradle      Sin él, cada build vuelve a descargar la cadena de
                                             Android entera (~10 minutos en lugar de 3).

      demoeca_android  -> /root/.android     **El importante para poder instalar.** Contiene el
                                             `debug.keystore`. La imagen de Flutter no trae uno, así
                                             que Gradle lo genera al vuelo dentro del contenedor y se
                                             descarta al terminar: cada APK quedaba firmado con una
                                             clave distinta y Android rechazaba instalarlo encima del
                                             anterior con INSTALL_FAILED_UPDATE_INCOMPATIBLE.

.PARAMETER HostIp
    IP del backend a embeber. Si se omite, se detecta la de la interfaz con ruta por defecto.

.PARAMETER Release
    Compila en modo release en lugar de debug. Nota: release exige un keystore propio de firma; sin
    configurarlo, Gradle firma con el de debug y el APK no es distribuible.

.EXAMPLE
    .\tools\build-apk.ps1
    .\tools\build-apk.ps1 -HostIp 192.168.18.31
#>
[CmdletBinding()]
param(
    [string]$HostIp,
    [switch]$Release
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$mobile = Join-Path $repo 'mobile'

if (-not (Test-Path (Join-Path $mobile 'pubspec.yaml'))) {
    Write-Error "No se encontró el proyecto Flutter en $mobile"
}

# --- IP ---------------------------------------------------------------------
if (-not $HostIp) {
    $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric |
        Where-Object { $_.InterfaceAlias -notmatch 'Tailscale|WSL|Hyper-V|vEthernet' } |
        Select-Object -First 1
    if (-not $route) {
        Write-Error 'No se pudo determinar la interfaz de red. Pasa la IP con -HostIp.'
    }
    $HostIp = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex |
        Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress
}
if (-not ($HostIp -match '^\d{1,3}(\.\d{1,3}){3}$')) {
    Write-Error "IP no válida: '$HostIp'"
}

# --- Volúmenes --------------------------------------------------------------
foreach ($volume in @('demoeca_pubcache', 'demoeca_gradle', 'demoeca_android')) {
    docker volume create $volume | Out-Null
}

# El keystore se genera una sola vez y sobrevive en el volumen. Sin esto la firma cambiaría en cada
# build y la app no se podría actualizar sobre la instalada.
$image = 'ghcr.io/cirruslabs/flutter:stable'
docker run --rm -v demoeca_android:/root/.android $image bash -lc @'
test -f /root/.android/debug.keystore && exit 0
keytool -genkeypair -v -keystore /root/.android/debug.keystore \
  -storepass android -keypass android -alias androiddebugkey \
  -keyalg RSA -keysize 2048 -validity 10950 \
  -dname "CN=Android Debug, O=Android, C=US" > /dev/null 2>&1
echo "debug.keystore creado"
'@

# --- Build ------------------------------------------------------------------
$mode = if ($Release) { 'release' } else { 'debug' }
Write-Host "Compilando APK ($mode) contra http://${HostIp}:8000 ..." -ForegroundColor Cyan

docker run --rm `
    -v "${mobile}:/app" `
    -v demoeca_pubcache:/root/.pub-cache `
    -v demoeca_gradle:/root/.gradle `
    -v demoeca_android:/root/.android `
    -w /app $image `
    bash -lc "flutter build apk --$mode --dart-define=API_BASE_URL=http://${HostIp}:8000 2>&1 | tail -4"

$apk = Join-Path $mobile "build\app\outputs\flutter-apk\app-$mode.apk"
if (-not (Test-Path $apk)) {
    Write-Error 'El build no produjo el APK.'
}

# --- Verificación -----------------------------------------------------------
Write-Host "`nHuella de firma del APK:" -ForegroundColor Cyan
docker run --rm -v "${mobile}:/app" -w /app $image `
    bash -lc "/opt/android-sdk-linux/build-tools/36.0.0/apksigner verify --print-certs build/app/outputs/flutter-apk/app-$mode.apk 2>/dev/null | grep -i 'SHA-256 digest'"

$info = Get-Item $apk
Write-Host @"

=========================================================================
 APK listo: $apk
 Tamaño:    $([math]::Round($info.Length / 1MB, 1)) MB
 Backend:   http://${HostIp}:8000

 Instálalo arrastrándolo a la ventana de BlueStacks.

 Si es la primera vez tras arreglar la firma, DESINSTALA la versión
 anterior: venía firmada con otra clave y Android rechaza la
 actualización. A partir de ahora la firma es estable.
=========================================================================
"@ -ForegroundColor Cyan
