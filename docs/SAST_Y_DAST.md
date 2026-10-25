# Análisis de seguridad: SAST y DAST

Procedimiento y resultados del análisis estático (SAST) y dinámico (DAST) del
módulo Carro de Paro.

**Criterio de aceptación adoptado:** cero hallazgos de severidad media o superior
sobre código propio, con los residuales de severidad baja justificados uno por uno
en el propio código.

Conviene decirlo así y no «cero vulnerabilidades» a secas. Las herramientas siempre
reportan algo, y la diferencia entre un informe serio y uno maquillado es si los
hallazgos se corrigieron o se silenciaron. Cada supresión de este proyecto lleva el
motivo escrito junto a la línea y se puede auditar con un `grep`.

---

## 1. Análisis estático (SAST)

### 1.1 Herramientas

| Herramienta | Qué busca | Por qué esta |
|---|---|---|
| **Bandit 1.9** | Patrones inseguros en Python, clasificados por CWE | Es el analizador de referencia para Python; equivale a lo que SonarLint hacía sobre Java en el SGHCU |
| **Semgrep 1.178** | Configuración insegura, secretos, CORS permisivo, XSS | Analiza Python y JavaScript con reglas propias del proyecto, versionadas en el repositorio |
| **pip-audit 2.10** | Vulnerabilidades conocidas (CVE) en las dependencias | El código propio puede ser correcto y la aplicación ser vulnerable por una biblioteca desactualizada |

Las tres cubren superficies distintas. Bandit mira cómo está escrito el código;
Semgrep, cómo está configurado; pip-audit, de qué depende.

### 1.2 Ejecución

```powershell
pip install bandit semgrep pip-audit
python scripts/auditar_seguridad.py
python scripts/auditar_seguridad.py --detalle   # lista cada hallazgo
```

El script ejecuta las tres, consolida el resultado y deja los informes en JSON en
`docs/seguridad/`. Devuelve código de salida 1 si hay algo de severidad media o
superior, de modo que puede usarse como puerta de calidad en una integración
continua.

### 1.3 Resultado

```
BANDIT      0 altos · 0 medios · 0 bajos     sobre 7.125 líneas
SEMGREP     0 errores · 0 advertencias · 0 informativos
PIP-AUDIT   0 vulnerabilidades en 62 dependencias
```

### 1.4 Hallazgos corregidos

Estado inicial: **22 hallazgos en Bandit** (1 alto, 6 medios, 15 bajos), **2 en
Semgrep** y **1 CVE** en dependencias.

| # | Hallazgo | Sev. | CWE | Corrección |
|---|---|---|---|---|
| 1 | MD5 para la huella del audio del asistente | Alta | CWE-327 | Sustituido por SHA-256. No era uso criptográfico, pero MD5 obliga a justificarse en cada auditoría |
| 2 | `urlopen` sin validar el esquema de la URL | Media | CWE-918 | Se valida que sea `http`/`https` antes de abrir. La dirección viene del `.env`; sin la validación, `file://` habría convertido la ingesta en un lector de archivos locales |
| 3–7 | Cinco consultas SQL armadas con f-strings o concatenación | Media | CWE-89 | Reescritas como consultas literales y parametrizadas. Ninguna recibía entrada del usuario, pero una consulta armada en tiempo de ejecución obliga a comprobar de dónde sale cada valor |
| 8 | CVE en `pyspark` 3.5.3 | Media | PYSEC-2026-3966 | Actualizado a 3.5.8 |
| 9–15 | Siete bloques `except: pass` | Baja | CWE-390 | Reemplazados por registro en el log. El de `permisos.py` era el más serio: silenciaba fallos al registrar un evento de seguridad, dejando ciega la auditoría |
| 16 | IP fija en el cliente de la app móvil | Info | CWE-1051 | La dirección se deduce del origen desde el que se sirve la app; el usuario puede cambiarla sin recompilar |
| 17 | `subprocess` sin ruta absoluta en el script de auditoría | Baja | CWE-426 | Se resuelve el ejecutable con `shutil.which` antes de invocarlo |

### 1.5 Supresiones y su justificación

Nueve líneas llevan `# nosec` con el motivo al lado. Se pueden auditar con:

```powershell
findstr /S /N "nosec" src\*.py api\*.py app\*.py scripts\*.py
```

| Regla | Dónde | Por qué no es un defecto |
|---|---|---|
| B311 (`random` no criptográfico) | `simulador.py`, `inicializar_bd.py` | Genera **datos de demostración reproducibles a partir de una semilla fija**. `secrets` es seguro precisamente porque no permite reproducir una secuencia. Las credenciales del sistema sí usan `secrets` |
| B105 (contraseña en el código) | `api/main.py`, `migrar_mfa.py` | `"bearer"` es el tipo de token que define OAuth 2.0 (RFC 6750) y `"VARCHAR(64) NULL"` es una definición de columna. Ninguno es una credencial |
| B310 (`urlopen`) | `ingesta.py` | El esquema de la URL se valida en la línea anterior |
| B404/B603 (`subprocess`) | `auditar_seguridad.py` | Órdenes fijas, sin `shell`, con ruta absoluta y sin entrada del usuario |

### 1.6 Reglas propias de Semgrep

En `docs/seguridad/reglas-semgrep.yml` hay catorce reglas escritas para este
proyecto, con su CWE y su categoría OWASP. Cubren secretos en el código, secreto
JWT por defecto, CORS permisivo, modo de depuración, verificación TLS desactivada,
SQL por interpolación, ejecución dinámica, comandos con `shell`, hash débil,
aleatoriedad insegura en credenciales, excepciones silenciadas, secretos en el
registro, HTML sin escapar y direcciones fijas en el código.

Se versionan en el repositorio por dos razones: la auditoría se puede repetir sin
conexión a los catálogos en línea de Semgrep, y las reglas documentan explícitamente
qué se considera un defecto en este proyecto.

---

## 2. Análisis dinámico (DAST)

El análisis dinámico se hace sobre la aplicación **en ejecución**, porque busca
fallos que no son visibles en el código: cabeceras que faltan, sesiones que no
caducan, mensajes de error que revelan información interna.

### 2.1 Herramienta

**OWASP ZAP** (Zed Attack Proxy), la misma que se usó sobre el SGHCU el semestre
anterior, lo que permite comparar contra aquella línea base.

Descárguela de `zaproxy.org`. Requiere **Java 17 o superior**.

### 2.2 Superficies a analizar

Este sistema expone **dos** superficies distintas, y hay que analizarlas por separado
porque su naturaleza no es la misma:

| Superficie | Dirección | Naturaleza |
|---|---|---|
| Aplicación web | `http://localhost:8501` | Streamlit; el servidor renderiza y mantiene el estado |
| API REST | `http://localhost:8000` | FastAPI; sin estado, autenticación por token |

La API es la superficie más sensible: la consume la app móvil y cualquier sistema
externo, y su exposición es mayor que la de la interfaz web.

### 2.3 Procedimiento

**Paso 1 — Levantar el sistema.**

```powershell
python scripts/inicializar_bd.py
streamlit run app/main.py                              # terminal 1
uvicorn api.main:app --port 8000 --host 127.0.0.1      # terminal 2
```

**Paso 2 — Exploración automática de la web.**

En ZAP: *Quick Start → Automated Scan*, URL `http://localhost:8501`, *Attack*.

Streamlit comunica por WebSocket, así que el rastreador tradicional encuentra poco.
Use además el **navegador de ZAP** (*Manual Explore*) y recorra a mano el ingreso, el
tablero, el inventario y las alertas, para que el tráfico quede registrado.

**Paso 3 — Análisis de la API a partir de su especificación.**

Esta parte es la que da resultados sólidos, y aprovecha que FastAPI publica su
propia especificación OpenAPI:

1. *Import → Import an OpenAPI Definition from URL*
2. URL: `http://localhost:8000/openapi.json`
3. ZAP genera las peticiones de todos los endpoints
4. *Active Scan* sobre el nodo de la API

**Paso 4 — Analizar con sesión autenticada.**

Sin token, ZAP solo verá respuestas 401 y no analizará nada de fondo. Obtenga un token:

```powershell
curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d "{\"correo\":\"medico@hospital.com\",\"password\":\"Carro#Paro2026\"}"
```

En ZAP: *Options → Replacer → Add*, tipo *Request Header*, nombre `Authorization`,
valor `Bearer <el token>`, y marque *Enable*. Repita la exploración activa.

**Paso 5 — Exportar el informe.**

*Report → Generate HTML Report*. Guárdelo en `docs/seguridad/` como evidencia.

### 2.4 Qué esperar y cómo interpretarlo

Estas alertas aparecerán y **no** son defectos del sistema:

| Alerta | Por qué aparece | Qué responder |
|---|---|---|
| *Strict-Transport-Security Header Not Set* | Se está probando en `http://localhost`, sin TLS | La cabecera se emite solo sobre HTTPS. En despliegue real, detrás del proxy inverso con certificado, se activa |
| *Cookie without Secure flag* | Igual: sin HTTPS no se marcan como seguras | Lo mismo |
| *Server Leaks Version Information* | Cabecera del servidor de desarrollo | La API ya elimina la cabecera `server`; el de Streamlit en modo desarrollo no |

Estas sí hay que corregirlas si aparecen: cualquier alerta de **inyección SQL**,
**XSS**, **path traversal**, **autenticación rota** o **exposición de datos
sensibles**; y cualquier endpoint que responda 200 sin token cuando debería exigirlo.

### 2.5 Controles ya implementados que el DAST debería confirmar

| Control | Dónde | Qué debería observar ZAP |
|---|---|---|
| Cabeceras de seguridad | `api/main.py` | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store` |
| CORS restringido | `api/main.py` | Un `Origin` ajeno recibe 400, sin `Access-Control-Allow-Origin` |
| Autenticación en todos los endpoints | `api/main.py` | Sin token: 401 en todo salvo `/api/salud` |
| Autorización por rol | `src/seguridad/permisos.py` | Con token de médico: 403 en operaciones de administrador |
| Bloqueo por intentos | `src/seguridad/autenticacion.py` | Al sexto intento fallido, la cuenta se bloquea 15 minutos |
| Mensajes genéricos | `src/seguridad/autenticacion.py` | «Correo o contraseña incorrectos» sin distinguir cuál falló |
| Consultas parametrizadas | `src/database/connection.py` | Las pruebas de inyección SQL no alteran el comportamiento |
| Expiración de sesión | `app/sesion.py` | Inactividad de 15 minutos cierra la sesión |

### 2.6 Comprobaciones manuales que ZAP no hace

Tres controles de este sistema requieren verificación manual, porque dependen de la
lógica de negocio:

**Escalada horizontal de privilegios.** Con un token de médico, intentar operaciones
de regente de farmacia. Debe responder 403 y registrarse en `eventos_seguridad`.

**Reutilización del código de segundo factor.** Usar el mismo código TOTP dos veces.
La segunda debe fallar: el sistema guarda el último intervalo usado.

**Token temporal de MFA.** El token que devuelve el login cuando falta el segundo
factor solo debe servir para `POST /api/auth/mfa`. Probarlo contra cualquier otro
endpoint debe dar 401. Existe una prueba automatizada que lo verifica
(`test_api_token_temporal_no_da_acceso`).

---

## 3. Para el documento de la tesis

Lo que sostiene un informe de seguridad no es el número final sino el recorrido:

**Declare el alcance.** «Cero hallazgos de severidad media o superior sobre código
propio, en 7.125 líneas analizadas» es verificable. «Cero vulnerabilidades» no dice
de qué ni con qué herramienta.

**Muestre el antes y el después.** 22 hallazgos iniciales en Bandit, 1 CVE en
dependencias, y qué se hizo con cada uno. Un informe que empieza en cero levanta más
sospecha que uno que documenta correcciones.

**Justifique cada supresión.** Las nueve de este proyecto están en la tabla 1.5, con
el motivo junto a la línea en el código.

**Distinga corregir de silenciar.** De los 22 hallazgos, 17 se corrigieron
modificando el código. Solo 9 líneas llevan supresión, y ninguna es un defecto real.

**Reconozca lo que falta.** El análisis dinámico se ejecuta sobre un despliegue local
sin TLS, lo que impide verificar los controles de transporte. Las pruebas de carga y
el análisis de la aplicación móvil compilada quedan fuera del alcance.
