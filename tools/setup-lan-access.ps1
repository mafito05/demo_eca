<#
.SYNOPSIS
    Configura el backend para que sea accesible desde un emulador o un móvil de la red local.

.DESCRIPTION
    Por defecto el stack está pensado para acceder desde el propio host (`localhost`). Un
    emulador como BlueStacks, o un teléfono físico, son otra máquina desde el punto de vista de
    la red: `localhost` allí es el propio dispositivo.

    Hay un detalle que no se arregla solo cambiando la URL del API: las URLs prefirmadas de
    MinIO (segmentos de video, documentos) **se firman contra un host concreto**, porque la
    firma SigV4 cubre la cabecera `Host`. Si se firman con `localhost:9000`, el emulador
    intentará conectarse a sí mismo y el video no se reproducirá. De ahí que este script tenga
    que tocar `MINIO_PUBLIC_ENDPOINT` y recrear los contenedores.

    Recrear y no reiniciar: `docker compose restart` NO recarga `env_file`.

.PARAMETER HostIp
    IP a usar. Si se omite, se detecta la de la interfaz con puerta de enlace por defecto.

.EXAMPLE
    .\tools\setup-lan-access.ps1
    .\tools\setup-lan-access.ps1 -HostIp 192.168.18.33
#>
[CmdletBinding()]
param(
    [string]$HostIp
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repo '.env'

if (-not (Test-Path $envFile)) {
    Write-Error "No existe $envFile. Copia .env.example primero."
}

# --- 1. Determinar la IP -----------------------------------------------------
if (-not $HostIp) {
    # Se elige la interfaz que tiene la ruta por defecto: es la que ve la red local. Se excluye
    # Tailscale y similares, que tienen IP propia pero no son la LAN a la que llega el emulador.
    $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric |
        Where-Object { $_.InterfaceAlias -notmatch 'Tailscale|WSL|Hyper-V|vEthernet' } |
        Select-Object -First 1

    if (-not $route) {
        Write-Error 'No se pudo determinar la interfaz de red. Pasa la IP con -HostIp.'
    }

    $HostIp = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex |
        Where-Object { $_.IPAddress -notlike '169.254.*' } |
        Select-Object -First 1).IPAddress
}

if (-not ($HostIp -match '^\d{1,3}(\.\d{1,3}){3}$')) {
    Write-Error "IP no válida: '$HostIp'"
}

Write-Host "IP del host: $HostIp" -ForegroundColor Cyan

# --- 2. Parchear el .env ----------------------------------------------------
# Se lee y escribe con UTF8 sin BOM explícitamente: PowerShell 5.1 escribe BOM por defecto, y un
# BOM en un .env se cuela en la primera clave.
$lines = [System.IO.File]::ReadAllLines($envFile)
$cambios = @()

function Set-EnvLine {
    param([string[]]$Lines, [string]$Key, [string]$Value)
    $pattern = "^$([regex]::Escape($Key))="
    $found = $false
    $result = foreach ($line in $Lines) {
        if ($line -match $pattern) {
            $found = $true
            "$Key=$Value"
        } else {
            $line
        }
    }
    if (-not $found) { $result = @($result) + "$Key=$Value" }
    return $result
}

$objetivos = @{
    # Host con el que se FIRMAN las URLs para clientes externos.
    'MINIO_PUBLIC_ENDPOINT' = "${HostIp}:9000"
    # Se añade la IP a CORS para poder abrir el panel desde otro dispositivo de la red.
    'CORS_ORIGINS'          = "http://localhost:4200,http://127.0.0.1:4200,http://${HostIp}:4200"
}

foreach ($key in $objetivos.Keys) {
    $actual = ($lines | Where-Object { $_ -match "^$key=" }) -replace "^$key=", ''
    if ($actual -ne $objetivos[$key]) {
        $lines = Set-EnvLine -Lines $lines -Key $key -Value $objetivos[$key]
        $cambios += "$key -> $($objetivos[$key])"
    }
}

if ($cambios.Count -gt 0) {
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines($envFile, $lines, $utf8NoBom)
    Write-Host 'Cambios en .env:' -ForegroundColor Yellow
    $cambios | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host '.env ya estaba configurado para esta IP.' -ForegroundColor Green
}

# --- 3. Recrear los contenedores -------------------------------------------
Push-Location $repo
try {
    Write-Host "`nRecreando backend y worker (restart NO recarga env_file)..." -ForegroundColor Cyan
    docker compose up -d --force-recreate backend worker | Out-Null
    Start-Sleep -Seconds 10

    $estado = docker compose ps backend --format '{{.Status}}'
    Write-Host "backend: $estado"

    # --- 4. Comprobar accesibilidad ----------------------------------------
    Write-Host "`nComprobando acceso por la IP de la LAN..." -ForegroundColor Cyan
    foreach ($check in @(
            @{ Nombre = 'API'; Url = "http://${HostIp}:8000/health/ready" },
            @{ Nombre = 'MinIO'; Url = "http://${HostIp}:9000/minio/health/live" }
        )) {
        try {
            $response = Invoke-WebRequest -Uri $check.Url -TimeoutSec 6 -UseBasicParsing
            Write-Host "  OK    $($check.Nombre) en $($check.Url) -> HTTP $($response.StatusCode)" -ForegroundColor Green
        } catch {
            Write-Host "  FALLO $($check.Nombre) en $($check.Url): $($_.Exception.Message)" -ForegroundColor Red
        }
    }
} finally {
    Pop-Location
}

# --- 5. Instrucciones ------------------------------------------------------
Write-Host @"

=========================================================================
 Listo. Para la app móvil:

   flutter run --dart-define=API_BASE_URL=http://${HostIp}:8000

 Y si compilas un APK para instalarlo en el emulador:

   flutter build apk --debug --dart-define=API_BASE_URL=http://${HostIp}:8000

 IMPORTANTE: la IP queda embebida en el APK. Si el router cambia la IP del
 host (DHCP), hay que volver a ejecutar este script y recompilar.
=========================================================================
"@ -ForegroundColor Cyan
