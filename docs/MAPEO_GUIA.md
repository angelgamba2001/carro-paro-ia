# Cumplimiento de la guía del proyecto integrador (Corte II)

Cada punto de la guía y dónde se evidencia en el código. Útil para la sustentación.

## 3.1 Aplicación web
| Exigencia | Evidencia |
|---|---|
| Gestionar la información del contexto | `app/vistas/inventario.py`, `catalogo.py`, `usuarios.py` |
| Registrar, consultar y actualizar | Registro de lotes (manual y OCR), consumo, corrección de lote, baja lógica, atención de alertas |
| Interacción con usuarios | Login, 9 roles con menú según permisos, cambio obligatorio de clave |
| Consultar resultados del análisis | `app/vistas/tablero.py` pestaña Analítico, `bigdata.py` |
| Integrar el agente | `app/vistas/agente.py` + botón de interpretación en el tablero |

## 3.2 Big Data
| Exigencia | Evidencia |
|---|---|
| Obtención de datos | `src/bigdata/ingesta.py` |
| Integración de fuentes | 3 fuentes: MySQL operativo, histórico legado (CSV por año), API CUM datos.gov.co (JSON) |
| Almacenamiento | Data lake por zonas `data/raw` → `bronze` → `silver` → `gold` (Parquet) |
| Limpieza y transformación | `src/bigdata/procesamiento.py`: fechas en 4 formatos, normalización de nombres contra el catálogo, duplicados, nulos, cantidades inválidas, carros desconocidos. Cada regla se mide en `gold/calidad_datos` |
| Procesamiento de grandes conjuntos | PySpark (`_procesar_spark`), ~420 mil registros en 5 años; volumen escalable con `--anios` |
| Información preparada para análisis | 8 tablas GOLD (consumo diario/semanal/mensual, eventos, revisiones, bajas, catálogo enriquecido, calidad) |

## 3.3 Analítica
| Exigencia | Evidencia |
|---|---|
| Indicadores | `src/analitica/kpis.py` (disponibilidad de carros, valor en riesgo, cumplimiento de revisión, pérdidas) |
| Estadísticas y tendencias | Consumo mensual por servicio, eventos de código azul, pérdidas por vencimiento |
| Comparaciones | Tabla comparativa por servicio; variación vs periodo anterior |
| Patrones y clasificaciones | Matriz de riesgo probabilidad × impacto (ALTO/MEDIO/BAJO) en `riesgo.py` |
| Predicciones | `prediccion.py`: HistGradientBoosting global, validado contra línea base (MAE) |
| Comportamientos relevantes | `anomalias.py`: Isolation Forest + z-score sobre consumo semanal |
| Relación con la problemática | Todo apunta a que ningún carro quede sin medicamentos críticos |

## 3.4 Agente de IA
| Exigencia | Evidencia |
|---|---|
| Responder preguntas sobre los datos | `AgenteCarroParo.responder()` |
| Interpretar indicadores | Herramientas `resumen_inventario`, `indicadores_historicos`; botón en el tablero |
| Generar recomendaciones | `recomendar_reposicion`, `crear_recomendacion` |
| Detectar situaciones relevantes | `revision_autonoma()` recorre todos los carros por iniciativa propia |
| Generar alertas / ejecutar acciones | `crear_recomendacion` registra alertas tipo RECOMENDACION_AGENTE (permiso `agente.acciones`) |
| No es un chatbot independiente | Solo actúa mediante herramientas que llaman la capa de servicios; respeta el rol del usuario; todo queda en `consultas_agente` y `log_auditoria` |
| Lenguaje natural con LLM | Espacio listo en `src/agente/proveedores.py` (Hugging Face / Anthropic); hoy opera con motor de reglas |

## 3.5 Dashboard
KPI (6 operativos + 5 analíticos), gráficos Plotly, tablas, filtros por servicio / carro /
medicamento / periodo, semáforo de carros, mapa de calor de cobertura, matriz de riesgo.

## 4. Integración
El flujo pedido por la guía se cumple de extremo a extremo:
fuentes (`ingesta.py`) → almacenamiento (data lake) → procesamiento (Spark) → analítica (`motor.py`)
→ **las alertas vuelven a MySQL** → API (`api/main.py`) y web → dashboard + agente → recomendaciones.
`scripts/ejecutar_pipeline.py` o el botón de la vista Big Data ejecutan todo el flujo.

## 5. Funcionalidad mínima
| Ítem | Estado |
|---|---|
| Aplicación web funcional | ✔ Streamlit |
| Base de datos | ✔ MySQL 8, esquema v2 con 15 tablas |
| Fuentes de datos | ✔ 3 fuentes |
| Procesamiento con tecnologías Big Data | ✔ PySpark |
| Módulo de analítica | ✔ |
| Dashboard | ✔ |
| Agente de IA integrado | ✔ (motor de reglas; LLM pendiente de conectar) |
| API | ✔ FastAPI + JWT, documentación en /docs |
| Integración funcional | ✔ |
| Repositorio | Subir esta versión a GitHub |
| Ejecutable y demostrable | ✔ `prueba_entrega.py`, Docker Compose |
