# SMARTDATA 360 · Carro de Paro

Módulo del sistema hospitalario SMARTDATA 360 (SGHCU) para el control inteligente de los
medicamentos de reanimación en los carros de paro. Integra aplicación web, base de datos,
procesamiento Big Data, analítica predictiva, API REST y un agente de IA que consume los
servicios del propio sistema.

Proyecto integrador Big Data — Corte II. Semillero SEGURINF.

```
Fuentes de datos            Big Data (medallón)              Analítica                 Uso
─────────────────           ───────────────────              ─────────                 ───
MySQL operativo   ─┐                                          Predicción de demanda     Aplicación web (Streamlit)
Histórico legado  ─┼─▶ RAW ─▶ BRONZE ─▶ SILVER ─▶ GOLD ─▶     Detección de anomalías ─▶ Dashboard (KPI, filtros)
API datos.gov.co  ─┘         PySpark (respaldo pandas)        Matriz de riesgo          API REST (FastAPI + JWT)
(CUM)                                                         Alertas a la operación    Agente IA ─▶ recomendaciones
```

---

## 1. Requisitos

| Componente | Versión | Nota |
|---|---|---|
| Python | 3.10 – 3.12 | PySpark 3.5 aún no soporta 3.13 |
| MySQL | 8.0 | MySQL Workbench o XAMPP sirven |
| Java (JDK) | 17 | Solo para el motor Spark. Sin Java el pipeline usa pandas automáticamente |
| Git | cualquiera | |

## 2. Instalación en Windows (PowerShell)

```powershell
# 1. Clonar y entrar
git clone <url-del-repositorio> carro-paro-ia
cd carro-paro-ia

# 2. Entorno virtual
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
# Si PowerShell bloquea el script:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 3. Dependencias
pip install -r requirements.txt

# 4. Configuración
copy .env.example .env
notepad .env        # poner DB_USER, DB_PASSWORD y un JWT_SECRETO propio

# 5. Verificar
python verificar_entorno.py
```

### Java para Spark (opcional pero recomendado)
1. Instalar **Eclipse Temurin JDK 17** (adoptium.net), marcando la opción *Set JAVA_HOME*.
2. Cerrar y abrir PowerShell, y comprobar con `java -version`.
3. Spark en Windows muestra una advertencia sobre `winutils.exe`: se puede ignorar. El proyecto
   no usa Spark para escribir en disco (la escritura final a Parquet la hace pyarrow), que es lo
   que normalmente exige winutils.

## 3. Puesta en marcha

```powershell
# a) Crear la base de datos v2 y cargar datos de demostración (usuarios, carros, catálogo, inventario)
python scripts/inicializar_bd.py              # los usuarios deberán cambiar la clave al entrar
# python scripts/inicializar_bd.py --sin-cambio   # para demostraciones

# Si ya tenía la base creada, aplique las migraciones sin perder datos:
python scripts/migrar_mfa.py                  # segundo factor
python scripts/migrar_consentimientos.py      # registro de aceptación de políticas
python scripts/migrar_correo.py               # código por correo e identidad de Microsoft
python scripts/migrar_registro.py             # registro de usuarios por cuenta propia

# b) Generar el histórico legado (5 años, ~420 mil registros) en data/raw
python scripts/generar_historico.py --anios 5

# c) Ejecutar el flujo Big Data completo: ingesta -> Spark -> analítica -> alertas
python scripts/ejecutar_pipeline.py             # o:  --motor pandas

# d) Aplicación web
streamlit run app/main.py                       # http://localhost:8501

# e) API REST (otra terminal, con el venv activo)
uvicorn api.main:app --reload --port 8000       # documentación: http://localhost:8000/docs
```

Con Docker (sin instalar nada más): `copy .env.example .env` y luego `docker compose up --build`.

### Usuarios de demostración
Contraseña inicial de todos: **`Carro#Paro2026`**

| Correo | Rol | Qué puede hacer |
|---|---|---|
| admin@hospital.com | Administrador | Todo |
| medico@hospital.com | Médico | Consultar y registrar consumo |
| enfermero@hospital.com | Enfermero(a) | Registrar lotes, OCR, consumo, atender alertas |
| regente@hospital.com | Regente de farmacia | Además: bajas, catálogo, tablero analítico, acciones del agente |
| auditor@hospital.com | Auditor | Solo lectura + log de auditoría |
| direccion@hospital.com | Dirección médica | Tablero analítico y recomendaciones del agente |
| analista@hospital.com | Analista de datos | Ejecutar pipeline Big Data |
| seguridad@hospital.com | Oficial de seguridad | Auditoría y eventos de seguridad |
| ti@hospital.com | Soporte TI | Desbloquear cuentas, ejecutar pipeline |

La matriz completa está en `src/seguridad/permisos.py` (única fuente de verdad; la carga en la BD
la hace `inicializar_bd.py`).

## 4. Pruebas

```powershell
python -m pytest -q          # 26 pruebas: unitarias + integración (se omiten si no hay MySQL)
python prueba_entrega.py     # demostración por consola de todos los componentes
```

## 5. Estructura

```
app/                  Aplicación web Streamlit
  main.py             Portada, control de acceso y menú por permisos
  estilos.py          Sistema de diseño: paleta, tipografías y CSS común
  legal.py            Política de privacidad, cookies y términos de uso
  sesion.py           Expiración por inactividad y revalidación contra la BD
  vistas/landing.py   Página de inicio pública, con el acceso y los documentos legales
  vistas/             tablero, inventario, ocr, alertas, agente, bigdata, catalogo, usuarios, auditoria, perfil
api/main.py           API REST FastAPI con JWT
src/
  config.py           Configuración (todo desde .env)
  seguridad/          RBAC, bcrypt, bloqueo por intentos, JWT
  servicios/          Reglas de negocio (las usan web, API y agente por igual)
  bigdata/            Simulador, ingesta de 3 fuentes, procesamiento Spark/pandas, orquestador
  analitica/          KPI, predicción de demanda, anomalías, matriz de riesgo
  agente/             Herramientas, proveedores (reglas / espacios para LLM), agente
  ocr/                Extracción de fecha y lote; lectura de imagen con EasyOCR
  deteccion/          Espacio para el modelo YOLO
base de datos/        Esquema v2 (y el v1 anterior como referencia)
scripts/              inicializar_bd, generar_historico, ejecutar_pipeline
tests/                Pruebas automatizadas
docs/                 Mapeo contra la guía, registro de cambios e inventario de licencias
data/                 Data lake (raw/bronze/silver/gold). Solo data/referencia va a Git
```

## 6. Integrar un LLM en el agente

El agente ya funciona con un motor de reglas (sin costo ni conexión). Para conectarlo a un modelo
de lenguaje:

1. Implementar `siguiente_paso()` en `ProveedorHuggingFace` o `ProveedorAnthropic`
   (`src/agente/proveedores.py`); los pasos están descritos en el docstring de cada clase.
2. Poner `AGENTE_PROVEEDOR=huggingface` (o `anthropic`) y las credenciales en `.env`.

No hay que tocar nada más: las herramientas, los permisos por rol y la auditoría ya están
resueltos. Los esquemas de herramientas se exportan con `esquemas_llm()` y la API los expone en
`GET /api/agente/herramientas`. Si el proveedor falla o no está implementado, el agente vuelve
automáticamente al motor de reglas.

## 7. Sobre los datos

- **MySQL operativo**: datos de demostración generados por `inicializar_bd.py`.
- **Histórico legado**: sintético (`src/bigdata/simulador.py`), con estacionalidad, diferencias por
  servicio y errores de calidad intencionales (duplicados, nulos, formatos de fecha mixtos,
  nombres inconsistentes) para que la limpieza sea medible.
- **CUM (datos.gov.co)**: se consulta por API. Si no hay red o el recurso cambió, se usa
  `data/referencia/cum_muestra.json`, que es una **muestra sintética** con la misma estructura
  (no contiene registros sanitarios reales). Verifique el identificador del recurso en
  `CUM_API_URL` antes de la sustentación.
- Los costos unitarios del catálogo son valores de referencia para la simulación.


## 8. Portada, documentos legales y licencias

Al abrir la aplicación sin sesión aparece una **página de inicio pública** que explica el sistema y
contiene el acceso. Desde allí se consultan la política de privacidad, la política de cookies y los
términos y condiciones, redactados según la Ley 1581 de 2012 y normas concordantes.

Dos advertencias importantes:

- Esos documentos son una **plantilla académica** y no han sido revisados por un abogado. Antes de
  usar el sistema fuera del aula hay que completar los datos del responsable en `app/legal.py` y
  someterlos a revisión jurídica.
- Al iniciar sesión, el usuario debe **aceptar las políticas**; la aceptación queda registrada en la
  tabla `consentimientos` con su versión y fecha, como exige el artículo 9 de la Ley 1581. Si se
  cambia el texto legal, hay que subir `VERSION_POLITICAS` en `src/servicios/consentimiento.py`
  para que se vuelva a solicitar.

El inventario de licencias de todo lo que el proyecto usa de terceros está en
[`docs/LICENCIAS.md`](docs/LICENCIAS.md), verificado contra los metadatos de los paquetes
instalados. Ahí queda anotado el punto que exige más atención: el conector de MySQL es GPL v2, lo
que condiciona la licencia que puede declarar el repositorio.

Las tipografías IBM Plex se cargan desde Google Fonts. Para un despliegue institucional conviene
alojarlas localmente; el procedimiento está en el mismo documento de licencias.


## 9. Rendimiento

La interfaz se ejecuta sobre Streamlit, que vuelve a correr el script completo ante cada
interacción. Tres decisiones sostienen la velocidad:

| Medida | Dónde | Efecto |
|---|---|---|
| Importación diferida de las vistas | `app/main.py` | La portada ya no espera a scikit-learn, Plotly ni PySpark: bajó de 2.282 ms a 283 ms |
| Memoria intermedia de lectura | `app/datos.py` | Navegar entre pantallas no repite las consultas; una escritura la vacía y el dato vuelve a ser el real |
| Tema nativo en vez de CSS sobreescrito | `.streamlit/config.toml` | Menos hoja de estilo que aplicar y una tipografía menos que descargar |

Medido en el navegador: primera pintura con contenido de 1.480 ms en la primera visita y
528 ms en las siguientes, cuando los archivos ya están en la caché del navegador.

Si la aplicación se siente lenta en un equipo concreto, conviene revisar primero si el
procesamiento Big Data se está ejecutando con Spark en segundo plano y si MySQL está en la misma
máquina; ambos compiten por memoria con la interfaz.


## 10. Novedades de la interfaz

**Portada con acceso separado.** La página pública tiene navegación propia y un botón *Acceder* que
lleva a la pantalla de ingreso. El movimiento es CSS puro —Streamlit no ejecuta JavaScript dentro de
sus bloques—: entrada escalonada del hero, trazado del monitor que se dibuja una vez, y una columna
roja que acompaña la lectura de las secciones usando animaciones ligadas al scroll. Donde el
navegador no las soporta, el contenido se ve igual, sin animación.

**Contraseña olvidada.** Quien tenga la verificación en dos pasos activa puede restablecer su
contraseña sin pasar por soporte: el código de la aplicación de autenticación —o uno de respaldo—
autoriza el cambio. Los intentos fallidos cuentan para el mismo bloqueo que el ingreso normal y todo
queda en `eventos_seguridad`. Las cuentas sin segundo factor no pueden usar esta vía y deben acudir
a soporte; el mensaje es idéntico exista o no la cuenta, para no revelar qué correos están
registrados.

**Asistente a mano.** Una burbuja en la esquina inferior derecha abre el asistente desde cualquier
pantalla, con cuatro atajos y un campo de escritura. Solo aparece para los roles con el permiso
`agente.usar`.

**Herramientas del asistente.** De 10 a 16, con seis nuevas: detalle de un carro, comparación entre
servicios, búsqueda de un medicamento, pedido consolidado para farmacia, historial de consumo y la
acción de atender una alerta. El motor de reglas ahora reconoce el carro, el medicamento o el
servicio mencionados en la pregunta, y pide el dato cuando falta en lugar de fallar.


## 11. Revisión de la interfaz

La portada y el sistema de diseño se auditaron contra **Impeccable**, un conjunto de reglas de
diseño de interfaz instalado en `.claude/skills/impeccable` (Apache 2.0; ver `docs/LICENCIAS.md`).
No es una dependencia del sistema: es una herramienta de autoría que se puede borrar sin afectar
nada. Lo que cambió a raíz de esa revisión:

| Se quitó | Por qué | Qué hay en su lugar |
|---|---|---|
| Rótulos sobre cada titular («el problema», «cómo funciona») | El titular ya dice de qué trata la sección; el rótulo solo la repite en pequeño | Solo el titular, con más aire encima |
| Numeración 01–05 de las secciones | No son pasos: nadie necesita leerlas en ese orden | Nada; las cuatro etapas del procesamiento sí conservan su número, porque ahí el orden es la información |
| Banda de tres cifras bajo el titular | Cifras sueltas sin la frase que las explica | Las mismas cifras dentro del párrafo de entrada |
| Franjas de color de 2 px al costado de bloques | Recurso decorativo | Regla superior de 1 px o superficie propia |
| Misma disolvencia de entrada en cada sección | Repetida cinco veces deja de ser un efecto | Un único movimiento de autor: la entrada del hero y la línea roja que se dibuja al leer |
| Cuadrícula de cuatro bloques iguales (seguridad) | Cuatro cajas idénticas no jerarquizan nada | Lista de definición con reglas, en el mismo lenguaje que la tabla de roles |
| Monoespaciada en rótulos («opcional», pies de figura) | La monoespaciada es para alinear dígitos, no para dar aire técnico | Sans; la monoespaciada queda para cifras, códigos y lotes, con cifras tabulares y cero barrado |

Se añadió además lo que el navegador dibuja por su cuenta y no pertenecía a ninguna paleta:
selección de texto, cursor de escritura, barras de desplazamiento y anillo de foco (`app/estilos.py`).
Y dos defectos reales que aparecieron al medir en el navegador: el texto de entrada se quedaba en
15 px porque Streamlit ganaba en especificidad, y la tabla de roles era ilegible a 390 px, donde
ahora se reordena en fichas con cada campo rotulado.

Para volver a revisar la interfaz tras un cambio:

```powershell
sh .claude/skills/impeccable/scripts/impeccable detect <archivos .html o .css>
```

El detector no lee Python, así que analiza el CSS y el marcado ya extraídos. Reporta dos avisos de
`cramped-padding` sobre `.cajon` que son falsos positivos: no resuelve `clamp()`, y el navegador
mide 43,5 px de relleno donde el detector supone cero.


## 12. Correos institucionales e inicio de sesión con Microsoft

Los usuarios pueden usar direcciones reales (`@suuniversidad.edu.co`, `@outlook.com`)
en lugar de las de demostración, recibir avisos de seguridad en su buzón, obtener el
código del segundo factor por correo y entrar con su cuenta de Microsoft.

El procedimiento completo está en [`docs/CORREO_Y_SSO.md`](docs/CORREO_Y_SSO.md).
Resumen de lo que hay que hacer y saber:

```powershell
python scripts/migrar_correo.py                      # una vez
python scripts/probar_correo.py su@correo.com        # diagnóstico y prueba
```

| Pieza | Qué activa | Qué necesita |
|---|---|---|
| `DOMINIOS_CORREO` | Restringe los dominios al crear usuarios. Vacío = cualquiera | Nada |
| `CORREO_MODO=archivo` | Guarda cada correo en `data/correo_saliente` sin enviarlo | Nada. **Es el modo por defecto** |
| `CORREO_MODO=smtp` | Envío real de avisos y códigos | Un buzón con SMTP habilitado |
| Segundo factor por correo | Cada usuario lo activa en *Mi cuenta* | Que el correo funcione |
| `MS_CLIENT_ID` y compañía | Botón *Continuar con Microsoft* | Que TI registre la aplicación en Entra ID |

Tres cosas que conviene tener claras antes de la sustentación:

**El modo archivo no es un sucedáneo.** Genera exactamente el mismo mensaje que se
enviaría, y se abre con doble clic. Para demostrar en una sala es más fiable que
depender de la red y del servidor de correo de la universidad.

**Microsoft 365 trae el SMTP deshabilitado.** Desde 2022 la autenticación SMTP básica
viene desactivada por defecto en los inquilinos. Habilitarla es una petición acotada
a TI —se hace buzón por buzón—, pero es el obstáculo con el que se va a topar.
`probar_correo.py` reconoce ese error y dice qué pedir.

**El código por correo es un factor más débil que el TOTP.** Viaja por la red y queda
en un buzón. Por eso los roles con permisos críticos siguen obligados a usar la
aplicación de autenticación, y el correo solo se les ofrece como canal adicional.
Esa distinción es la parte defendible del diseño.

El inicio de sesión con Microsoft usa OpenID Connect con *authorization code* y
**PKCE**, aunque haya secreto de cliente: Streamlit devuelve el código en la barra de
direcciones, y con PKCE un código robado de ahí no sirve sin el verificador, que
nunca sale del servidor. La persona se identifica por el `oid` de Entra ID y no por
el correo, porque el correo cambia y el `oid` no. Una cuenta de Microsoft válida que
no esté dada de alta **no entra**, salvo que se configure `MS_ROL_POR_DEFECTO`.


## 13. Registro de usuarios por cuenta propia

Cualquiera puede crear su cuenta desde la pantalla de acceso con su correo real.
El recorrido es: **crear cuenta → código de seis dígitos al correo → autorización →
acceso**.

El formulario no deja elegir el perfil, y esa es la decisión de diseño que sostiene
todo lo demás. Aquí el perfil determina quién puede dar de baja medicamentos o
gestionar cuentas: si el registro lo dejara elegir, registrarse equivaldría a
autoasignarse permisos sobre los carros de paro de un hospital. Verificar el correo
demuestra que el buzón es suyo; que además deba operar carros lo decide la
institución, desde **Usuarios → Solicitudes de acceso**.

Hasta que alguien autorice, la cuenta tiene el perfil `SIN_ASIGNAR` —sin ningún
permiso— y `activo = 0`, así que ni siquiera puede iniciar sesión.

| Ajuste | Efecto |
|---|---|
| `REGISTRO_ABIERTO=false` | Desaparece el botón *Crear una cuenta* |
| `REGISTRO_ROL_INICIAL=` (vacío) | La cuenta espera autorización. **Por defecto** |
| `REGISTRO_ROL_INICIAL=MEDICO` | Se activa sola al verificar el correo, con ese perfil |

Si alguien se registra con un correo que ya existe, el mensaje es idéntico al de un
correo nuevo: decir «esa cuenta ya existe» permitiría averiguar quién está
registrado probando direcciones. En su lugar, al dueño del buzón le llega un aviso
de que alguien lo intentó.

**Para que los correos lleguen de verdad a Gmail**, el camino que funciona sin
depender de TI es una cuenta de Gmail con contraseña de aplicación como remitente
(Microsoft 365 trae el SMTP deshabilitado). Los pasos están en el apartado 6 de
[`docs/CORREO_Y_SSO.md`](docs/CORREO_Y_SSO.md), junto con el límite de esa
solución —500 correos al día y un remitente que no es del dominio del hospital— que
conviene mencionar en el documento antes de que lo pregunten.


## 14. Crear cuentas sin pasar por el registro

El registro por cuenta propia es para las personas. Usted, como administrador, tiene
dos atajos.

**Varias cuentas de una vez**, desde un CSV con columnas `nombre,correo,rol`:

```powershell
python scripts/crear_usuarios.py --archivo equipo.csv
python scripts/crear_usuarios.py --archivo equipo.csv --password "Carro#Paro2026"
python scripts/crear_usuarios.py "Ana Ruiz" ana.ruiz@gmail.com MEDICO
python scripts/crear_usuarios.py --roles        # ver los códigos de rol
```

Quedan activas y verificadas de inmediato —las crea un administrador, no hay nada
que confirmar— y cada persona recibe el correo de bienvenida con su perfil. La
contraseña **no** viaja en ese correo: se imprime en la terminal para que usted la
entregue por el canal que corresponda. Sin `--password`, a cada cuenta se le genera
una distinta y segura.

**Ver el último código generado** mientras desarrolla, sin abrir archivos a mano:

```powershell
python scripts/ultimo_codigo.py                  # los más recientes
python scripts/ultimo_codigo.py ana@gmail.com    # los de esa dirección
```

Solo funciona con `CORREO_MODO=archivo`. Con el envío real configurado el código
llega al buzón y este atajo deja de hacer falta.


## 15. Aplicación móvil

En [`movil/`](movil/README.md) está la app Android/iOS, construida con Apache
Cordova sobre la misma API REST y los mismos permisos por rol que la web.

Para verla sin compilar nada:

```powershell
uvicorn api.main:app --port 8000 --host 0.0.0.0        # terminal 1
python -m http.server 8700 --directory movil/www       # terminal 2
```

Abra `http://localhost:8700`, active la vista de móvil del navegador y, antes de
entrar, pulse *Configurar servidor*.

Cinco pantallas —tablero, inventario, alertas, asistente y cuenta— con la barra
inferior mostrando solo los destinos que el rol permite. Para compilar el APK y
para el problema de que el teléfono no alcanza el `localhost` del computador, el
procedimiento está en [`movil/README.md`](movil/README.md).

**Dos cambios que esto exigió en el backend**, ambos necesarios y ya aplicados:

- **CORS** en `api/main.py`, con lista explícita de orígenes (`CORS_ORIGENES` en el
  `.env`). Nunca `*`: eso dejaría que cualquier web llamara a la API en nombre de
  un usuario autenticado.
- **Un error 500 corregido** en el serializador de la API. Los huecos de pandas
  (`NaN`, `NaT`) no son JSON válido, y `GET /api/alertas` fallaba siempre que una
  alerta no tuviera fecha de atención —es decir, siempre que estuviera pendiente—.
  Ahora se convierten a `null`.
