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
  main.py             Login, cambio obligatorio de clave, menú por permisos
  sesion.py           Expiración por inactividad y revalidación contra la BD
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
docs/                 Mapeo contra la guía y registro de cambios
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
