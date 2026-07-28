# Probar la app en BlueStacks

BlueStacks **no** es el emulador de Android Studio, y esa diferencia importa para la red. Esta
guía asume Windows y el stack corriendo en el mismo ordenador.

## Lo que cambia respecto al emulador de Android Studio

| | Emulador de Android Studio (AVD) | BlueStacks |
|---|---|---|
| Cómo alcanzar el host | `10.0.2.2` (alias especial de QEMU) | **La IP de LAN del host** (ej. `192.168.18.33`) |
| ADB | Detectado automáticamente | Hay que conectarlo a mano por TCP |
| Arquitectura | Suele ser x86_64 o arm64 | x86_64 (con traducción para ARM) |

**`10.0.2.2` no funciona en BlueStacks.** Es un alias que implementa el emulador de Google, no una
convención de Android. Si se compila con el valor por defecto, la app no conectará con nada y el
síntoma será idéntico a un backend caído.

## 1. Configurar el backend para la red local

```powershell
docker compose up -d
.\tools\setup-lan-access.ps1
```

El script detecta la IP del host, ajusta el `.env`, recrea los contenedores y comprueba que el API
y MinIO responden por esa IP. Al final imprime el comando de compilación exacto.

**Por qué hace falta un script y no basta con cambiar la URL del API:** las URLs prefirmadas de
MinIO (los segmentos de video) se firman contra un host concreto, porque la firma SigV4 cubre la
cabecera `Host`. Si se firman con `localhost:9000`, BlueStacks intentará conectarse a sí mismo y el
video no cargará nunca, aunque el resto de la app funcione. Por eso el script toca
`MINIO_PUBLIC_ENDPOINT` y **recrea** los contenedores (`docker compose restart` no recarga
`env_file`).

Comprobar desde el propio host que la IP responde:

```powershell
curl http://192.168.18.33:8000/health/ready
```

Si eso falla, el problema es el **firewall de Windows**, no la app. Se abre con PowerShell
**como administrador**:

```powershell
New-NetFirewallRule -DisplayName "demoeca API"   -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "demoeca MinIO" -Direction Inbound -LocalPort 9000 -Protocol TCP -Action Allow
```

## 2. Compilar e instalar el APK

```powershell
.\tools\build-apk.ps1
```

Detecta la IP, la embebe en el binario y compila con los tres volúmenes de Docker que hacen falta.
**Usa siempre este script y no `docker run` a mano**: uno de esos volúmenes guarda el
`debug.keystore`, y sin él cada build queda firmado con una clave distinta y Android rechaza
instalarlo encima del anterior (ver D-037).

El APK aparece en `mobile\build\app\outputs\flutter-apk\app-debug.apk` e incluye `x86_64`, así que
instala en BlueStacks tal cual. Dos formas:

- **Arrastrar** el fichero a la ventana de BlueStacks (lo más rápido).
- **Instalar APK** desde el menú lateral.

**La IP queda embebida en el binario.** Si el router cambia la del host por DHCP, hay que volver a
ejecutar `setup-lan-access.ps1` y recompilar.

### Requisitos del APK

| | |
|---|---|
| `minSdkVersion` | 24 (Android 7.0) |
| `targetSdkVersion` | 36 |
| ABIs | `arm64-v8a`, `armeabi-v7a`, `x86_64` |
| Firma | APK Signature Scheme v2 (requiere Android 7.0+) |

BlueStacks `Pie64` es Android 9 (API 28) y cumple los cuatro. Para ver qué instancia tienes:

```powershell
Select-String -Path 'C:\ProgramData\BlueStacks_nxt\bluestacks.conf' -Pattern 'abi_list'
```

Si tu instancia fuese Nougat (API 24) también funciona; una anterior a Android 7 **no**, ni por
`minSdk` ni por el esquema de firma.

## 3. Comprobar la conexión antes de nada

Al abrir la app, la pantalla de entrada muestra en la parte inferior (solo en compilaciones de
depuración):

- **Backend configurado**: la URL con la que se compiló. Si dice `10.0.2.2`, el APK es el
  equivocado.
- Un botón **Comprobar conexión** que hace un `GET /health/ready` y explica el fallo concreto:
  tiempo de espera agotado (firewall o nada escuchando) frente a error de conexión (IP mal).

Ese diagnóstico existe justamente para no tener que adivinar: sin él, IP equivocada, firewall y
backend caído se ven exactamente igual.

## 4. Recorrer el flujo

La app tiene **dos módulos** en la barra inferior: **Equipos** y **Escanear**. Escanear es un atajo,
no un paso obligatorio.

1. **Entrar** — usa el bypass de demo; no pide credenciales.

2. **Aterrizas en Equipos**, el catálogo agrupado por especialidad. Toca *Litotrictor Uro-Litho
   3000* y la capacitación se abre **sin usar la cámara**. Es la vía recomendada en un emulador.

   > La app no arranca en el escáner a propósito. En la primera versión sí, y cuando la cámara
   > fallaba en BlueStacks la app quedaba inservible: la sesión persiste, así que cada
   > relanzamiento volvía al escáner y volvía a fallar. Ver D-033.

3. **Ruta de capacitación** — deben aparecer 2 módulos, 5 lecciones, y el módulo 2 con candado.
   La flecha de volver regresa al catálogo, y la barra inferior sigue accesible.

4. **Abrir la lección de video** ("Purga del circuito") — debe reproducirse el patrón de barras de
   12 segundos. Si se queda cargando, el problema es MinIO: vuelve al paso 1.

5. **Volver atrás** — la lección debe quedar marcada como completada y el módulo 2 desbloquearse.

6. **Botón Asistente** — preguntar:

   ```
   ¿Qué debo hacer si el equipo muestra el error E-204?
   ```

   Debe responder token a token y mostrar las fuentes citadas con la sección del manual.

7. **Guardrail** — preguntar algo clínico y comprobar que lo rehúsa:

   ```
   ¿Qué potencia uso para un paciente de 70 kg con un cálculo de 8 mm?
   ```

8. **Módulo Escanear** — toca la pestaña. BlueStacks puede usar la webcam del ordenador (Ajustes →
   Preferencias → activar cámara). Si no hay webcam, la pantalla explica el motivo y ofrece salida
   en lugar de quedarse en negro. El icono de teclado permite teclear el código:

   ```
   0hIB_HktchCK
   ```

   (Token de la máquina del seed. Para confirmarlo:
   `docker compose exec postgres psql -U demoeca -d demoeca -t -c "SELECT qr_token FROM machine_models;"`)

9. **Comprobar que la cámara se apaga** — con la webcam activa, entra en Escanear (se enciende el
   indicador de la webcam), cambia a Equipos y comprueba que se apaga. Si sigue encendida, la cámara
   quedó tomada en segundo plano y es un fallo que hay que reportar.

10. **Volver a explorar** — desde el catálogo se puede entrar a cualquier otro equipo. Los filtros
    por especialidad solo aparecen si hay más de una en los datos; con un único equipo sembrado no
    se verán, es lo esperado.

## 5. ADB con BlueStacks (opcional, para deep links y logs)

BlueStacks expone ADB por TCP, pero hay que activarlo: **Ajustes → Avanzado → Depuración por
ADB**. Anota el puerto que muestra (suele ser 5555, pero cambia por instancia).

```powershell
adb connect 127.0.0.1:5555
adb devices

# Probar el deep link sin cámara ni dominio configurado
adb shell am start -a android.intent.action.VIEW -d "demoeca://machine/0hIB_HktchCK"

# Ver los errores de la app
adb logcat -s flutter
```

El App Link con la URL `https://` **no** abrirá la app todavía: falta que el dominio sirva
`assetlinks.json` con la huella SHA-256 del certificado de firma. Ver
[deep-linking.md](deep-linking.md).

## Fallos frecuentes y qué significan

| Síntoma | Causa probable |
|---|---|
| **No deja instalar el APK** | Firma distinta a la de la versión ya instalada. **Desinstala la app primero.** Si se repite, se compiló sin el volumen `demoeca_android`: usa `tools\build-apk.ps1`. |
| "App not installed" sin más explicación | Casi siempre es lo anterior. También puede ser falta de espacio en la instancia, o Play Protect: prueba con **Instalar APK** del menú en lugar de arrastrar. |
| "No se pudo conectar con el servidor" al pulsar Entrar | IP equivocada en el APK, o firewall. Usa **Comprobar conexión**. |
| Entra, pero el catálogo sale vacío | Falta el seed: `docker compose exec backend python -m scripts.seed_demo` |
| El video se queda cargando para siempre | `MINIO_PUBLIC_ENDPOINT` apunta a `localhost`. Ejecuta `setup-lan-access.ps1`. |
| El chat dice "No hay credencial activa para el proveedor" | Falta la API key: `docker compose exec backend python -m scripts.bootstrap_ai` |
| El agente responde pero sin citar fuentes | El corpus no está vectorizado: `... bootstrap_ai --force` |
| La cámara sale en negro | BlueStacks sin webcam asignada. Usa **Introducir código**. |
| La app se cierra al abrir el escáner | Permiso de cámara denegado. Ajustes de Android → Apps → DemoECA → Permisos. |

## Lo que no se puede probar en BlueStacks

- **Rendimiento real del video.** BlueStacks decodifica por software sobre un hipervisor; los
  cortes que se vean ahí no predicen el comportamiento en un teléfono.
- **App Links / Universal Links** con el dominio real (falta la configuración del servidor).
- **Cámara con un QR impreso de verdad.** Una webcam apuntando a un adhesivo sobre metal, con
  reflejos y a distancia de brazo, es un caso distinto al de un QR en pantalla. Es lo primero que
  conviene probar con un teléfono físico.
