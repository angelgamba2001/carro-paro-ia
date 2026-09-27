# Carro de Paro · aplicación móvil

App Android/iOS del módulo Carro de Paro. Consume la **misma API REST** que la
aplicación web (`api/main.py`), con los mismos permisos por rol: lo que un perfil
no puede hacer en la web, tampoco puede hacerlo aquí, porque la decisión la toma
el servidor y no la pantalla.

Construida con **Apache Cordova**: HTML, CSS y JavaScript dentro de un contenedor
nativo. Mismo enfoque que la app del SGHCU, esta vez con un backend REST que sí
existe.

```
Teléfono                        Su computador o servidor
────────                        ────────────────────────
app Cordova  ──HTTPS + JWT──▶   FastAPI (puerto 8000)  ──▶  MySQL
(WebView)                       misma capa de servicios
                                que la web Streamlit
```

## Pantallas

| Pantalla | Qué muestra | Permiso que exige |
|---|---|---|
| Acceso | Correo, contraseña y segundo factor | — |
| Tablero | Seis indicadores y el semáforo de los doce carros | `dashboard.operativo` |
| Inventario | Lotes filtrables por carro y estado; registro de consumo | `inventario.ver` |
| Alertas | Pendientes y atendidas; marcar como atendida | `alertas.ver` |
| Asistente | Preguntas en español, con cuatro atajos | `agente.usar` |
| Mi cuenta | Perfil, permisos y estado del servidor | — |

La barra inferior **solo muestra los destinos que el rol permite**: un auditor no
ve «Asistente» si no tiene `agente.usar`. Los permisos se leen de
`GET /api/auth/yo` al entrar.

---

## 1. Probarla sin compilar nada

Lo más rápido para verla funcionando, antes de instalar Android Studio:

```powershell
# Terminal 1 — la API
uvicorn api.main:app --port 8000 --host 0.0.0.0

# Terminal 2 — la app como sitio web
python -m http.server 8700 --directory movil/www
```

Abra `http://localhost:8700` en el navegador y active la vista de móvil (F12 →
icono de teléfono). Antes de entrar, pulse **Configurar servidor** y ponga
`http://localhost:8000`.

Para que el navegador no bloquee las llamadas, arranque la API con ese origen
autorizado:

```powershell
$env:CORS_ORIGENES="http://localhost:8700,https://localhost,http://localhost"
uvicorn api.main:app --port 8000 --host 0.0.0.0
```

---

## 2. Compilar el APK

```powershell
npm install -g cordova
cd movil
cordova platform add android
cordova run android          # con el teléfono conectado y depuración USB activa
cordova build android --release   # para generar el APK firmado
```

Requiere **Android Studio** con el SDK y **JDK 17**. Cordova no funciona con
Java 26, que es el que usted tiene instalado para Spark: instale el JDK 17 aparte
y apunte `JAVA_HOME` a él solo para compilar la app.

---

## 3. El problema que le va a pasar: el teléfono no alcanza su computador

`localhost` dentro del teléfono se refiere **al teléfono**, no a su PC. Hay dos
salidas:

**a) Por la red Wi-Fi** (ambos en la misma red). Cuando Streamlit arranca imprime:

```
Network URL: http://192.168.1.12:8501
```

Esa IP es la de su computador. En la app, **Configurar servidor** →
`http://192.168.1.12:8000` (misma IP, puerto de la API). La API debe arrancar con
`--host 0.0.0.0`, no con `127.0.0.1`, o solo se escuchará a sí misma.

**b) Por cable USB**, si la Wi-Fi da problemas:

```powershell
adb reverse tcp:8000 tcp:8000
```

Con eso, `http://localhost:8000` dentro del teléfono llega a su PC. Hay que
repetirlo cada vez que se reconecte el cable.

Si el firewall de Windows bloquea el puerto, permítalo para redes privadas o
ejecute como administrador:

```powershell
New-NetFirewallRule -DisplayName "API Carro de Paro" -Direction Inbound `
  -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
```

---

## 4. CORS

La app corre en un WebView con su propio origen, así que la API tiene que
autorizarlo. En el `.env`:

```
CORS_ORIGENES=https://localhost,http://localhost,capacitor://localhost
```

Esos son los orígenes que usa Cordova. **Nunca ponga `*`**: eso permitiría que
cualquier página web abierta en el navegador de un usuario autenticado llamara a
la API en su nombre.

---

## 5. Decisiones que conviene saber defender

**Cordova y no Flutter.** Flutter da mejor rendimiento y componentes nativos.
Cordova gana aquí por una razón concreta: el sistema visual ya está escrito en CSS
para la web, y trasladarlo es copiar variables en vez de reescribir todo en
widgets de Dart. Para un tablero que consulta una API, el WebView es suficiente.
Si la app creciera a captura de fotos con YOLO en el dispositivo o gráficos
animados, Flutter sería la elección correcta.

**El token en `localStorage`.** Es lo que Cordova permite sin plugins, y el token
caduca en 30 minutos. Para producción conviene `cordova-plugin-secure-storage`,
que lo guarda en el llavero del sistema operativo. Está anotado en `js/api.js`.

**Las tablas se convierten en fichas.** Una tabla de siete columnas en 390 px es
ilegible. Cada lote y cada alerta se presentan como una ficha con jerarquía
propia; es el mismo dato, reorganizado para el pulgar.

**No se puede registrar consumo de un lote vencido.** La app muestra el lote, lo
marca en rojo y en lugar del botón pone la instrucción de retirarlo. Ofrecer
«Registrar consumo» ahí sería invitar a administrar un medicamento vencido, que es
justamente lo que el sistema existe para evitar.

**El inventario se pinta por tandas de 40.** Son más de trescientos lotes; pintarlos
de una vez deja el teléfono pensando varios segundos.

---

## 6. Lo que no está

Estas pantallas se quedaron fuera a propósito, porque en un teléfono aportan poco
o exigen más que una consulta rápida:

- **Big Data y catálogo**: se operan desde un computador, no de pie junto al carro.
- **Usuarios y auditoría**: revisar un registro de auditoría en 390 px no es útil.
- **Cambio de contraseña y activación del segundo factor**: se hacen en la web.
  La app los respeta —si el segundo factor está activo, lo pide al entrar—, pero
  no los administra.
- **Lectura OCR con la cámara**: es el siguiente paso natural y el que más sentido
  tiene en móvil. Requiere `cordova-plugin-camera` y decidir si la imagen se
  procesa en el teléfono o se envía a la API.
