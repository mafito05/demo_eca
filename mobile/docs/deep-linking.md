# Deep linking: lo que falta y por qué no lo puedo cerrar yo

El QR impreso en la máquina codifica una URL **https**, no el esquema propio `demoeca://`. El
motivo es concreto: si la app no está instalada, un esquema propio no abre nada y el código
quedaría muerto pegado a un equipo de 200.000 €. Una URL https, en cambio, cae en una landing web
que ofrece descargar la app.

Para que esa misma URL abra la app **directamente** (sin el diálogo "¿con qué app abrir esto?")
hacen falta dos ficheros servidos por el dominio del cliente. **Son datos que no tengo**, y sin
ellos el enlace se abre en el navegador. No es un fallo de la app: falta el paso del lado del
servidor.

## 1. Android — App Links

Servir en `https://DOMINIO/.well-known/assetlinks.json` con `Content-Type: application/json`:

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.demoeca.demoeca_app",
      "sha256_cert_fingerprints": [
        "AA:BB:CC:...:FF"
      ]
    }
  }
]
```

**Huella del certificado de debug de este proyecto** (ya utilizable, porque el keystore vive en el
volumen `demoeca_android` y no cambia entre builds — ver D-037):

```
D3:DC:9F:EF:AD:2A:7F:49:84:FA:F1:FF:89:51:66:02:26:01:4B:7D:79:FB:84:11:A5:B8:72:6E:AA:1F:6C:E8
```

Con esa huella en `assetlinks.json` ya se puede probar el App Link **con el build de debug**, sin
esperar al certificado de release. Ojo: si se borra el volumen, el keystore se regenera y la huella
cambia.

La de release se obtiene del **certificado con el que se firma el APK que se distribuye**:

```bash
# Certificado de release
keytool -list -v -keystore release.jks -alias demoeca | grep SHA256

# Certificado de debug (para probar antes de tener el de release)
keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey \
  -storepass android -keypass android | grep SHA256
```

Se pueden incluir varias huellas en el array: conviene poner la de debug **y** la de release para
poder probar sin publicar. Si la app se distribuye por Google Play con *Play App Signing*, la
huella que cuenta es la que muestra Play Console, **no** la del keystore local — es el error más
frecuente en este paso.

Comprobar tras publicar el fichero:

```bash
adb shell pm verify-app-links --re-verify com.demoeca.demoeca_app
adb shell pm get-app-links com.demoeca.demoeca_app     # debe decir "verified"
```

## 2. iOS — Universal Links

Servir en `https://DOMINIO/.well-known/apple-app-site-association` (**sin extensión**, con
`Content-Type: application/json`):

```json
{
  "applinks": {
    "apps": [],
    "details": [
      {
        "appID": "TEAMID.com.demoeca.demoecaApp",
        "paths": ["/m/*"]
      }
    ]
  }
}
```

`TEAMID` es el Team ID de la cuenta de Apple Developer (10 caracteres, visible en
developer.apple.com → Membership).

Además, en Xcode: seleccionar el target *Runner* → **Signing & Capabilities** → `+ Capability` →
**Associated Domains**, y añadir:

```
applinks:DOMINIO
```

Ese paso toca el fichero `Runner.entitlements`, que se genera desde Xcode y no está en el
repositorio.

## 3. Landing web de respaldo

En `https://DOMINIO/m/:token` conviene servir una página que:

1. Detecte el sistema operativo y ofrezca el enlace a la store correspondiente.
2. Muestre el nombre del equipo (se puede resolver contra
   `GET /api/v1/machines/resolve/{token}`, aunque hoy ese endpoint exige autenticación, así que
   haría falta una variante pública con datos mínimos).

Sin esa página, un QR escaneado en un móvil sin la app instalada acaba en un 404.

## Datos que hacen falta del cliente

| Dato | Para qué | Estado |
|---|---|---|
| Dominio real | Sustituir `demoeca.example.com` en `DEEPLINK_DOMAIN`, el manifiesto de Android y el AASA | ❌ pendiente |
| SHA-256 del certificado de firma Android | `assetlinks.json` | ❌ pendiente |
| Team ID de Apple | `apple-app-site-association` | ❌ pendiente |
| Bundle ID definitivo | Hoy `com.demoeca.demoeca_app` en ambas plataformas | ⚠️ provisional |

## Mientras tanto

Se prueba con el esquema propio, que sí funciona sin ninguna configuración de servidor:

```bash
# Android
adb shell am start -a android.intent.action.VIEW -d "demoeca://machine/EL_TOKEN"

# iOS (simulador)
xcrun simctl openurl booted "demoeca://machine/EL_TOKEN"
```

Y dentro de la app, el botón **Introducir código** de la pantalla de escaneo acepta el token
directamente, sin cámara ni deep link.
