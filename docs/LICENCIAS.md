# Licencias y derechos de autor

Este documento registra el origen y la licencia de todo lo que el proyecto incorpora sin haber
sido escrito por sus autores. Sirve para tres cosas: cumplir las condiciones de cada licencia,
poder responder en la sustentación de dónde salió cada componente, y dejar constancia de que no
se usó material con derechos ajenos sin autorización.

Las versiones y licencias que aparecen abajo fueron **verificadas leyendo los metadatos de los
paquetes instalados**, no copiadas de la documentación. Se recomienda repetir la verificación
después de cada actualización de dependencias con el comando del último apartado.

---

## 1. Obra propia

El código fuente del módulo Carro de Paro, el esquema de base de datos, la redacción de la
interfaz y los documentos del proyecto son obra de sus autores, en el marco del semillero
SEGURINF. Conforme a la Ley 23 de 1982 y la Decisión Andina 351 de 1993, los derechos morales
son inalienables y corresponden a los autores; los derechos patrimoniales se rigen por lo que
acuerden los autores con la institución.

**Falta definir la licencia del repositorio.** Mientras no se declare una licencia, por defecto
la obra queda bajo «todos los derechos reservados», lo que impide legalmente que terceros la
reutilicen. Si la intención es que el trabajo pueda ser aprovechado por otros, conviene añadir un
archivo `LICENSE` en la raíz. Dos opciones habituales en proyectos académicos:

| Licencia | Qué permite | Cuándo conviene |
|---|---|---|
| MIT | Uso, copia y modificación, incluso comercial, conservando el aviso de autoría | Máxima difusión del trabajo |
| GNU GPL v3 | Lo mismo, pero obliga a que las obras derivadas sigan siendo libres | Evitar que un tercero cierre el código |

Hay un motivo técnico para preferir la GPL en este caso concreto, explicado en el apartado 3.

---

## 2. Componentes de software de terceros

Todos son bibliotecas de código abierto instaladas mediante `pip`. Ninguna se redistribuye dentro
del repositorio: se declaran en `requirements.txt` y cada usuario las descarga de su fuente oficial.

| Componente | Versión verificada | Licencia | Uso en el proyecto |
|---|---|---|---|
| Streamlit | 1.64.0 | Apache 2.0 | Aplicación web e interfaz |
| Plotly | 7.1.0 | MIT | Gráficos del tablero |
| FastAPI | 0.141.1 | MIT | Interfaz de programación |
| Uvicorn | 0.46.0 | BSD 3-Clause | Servidor de la API |
| Pydantic | 2.13.3 | MIT | Validación de datos de la API |
| httpx | 0.28.1 | BSD 3-Clause | Cliente del modelo de lenguaje y pruebas |
| mysql-connector-python | 26.7.0 | **GPL v2 con excepción FOSS** | Conexión con MySQL |
| python-dotenv | 1.2.2 | BSD 3-Clause | Lectura de la configuración |
| bcrypt | 5.0.0 | Apache 2.0 | Protección de contraseñas |
| PyJWT | 2.12.1 | MIT | Tokens de la API |
| pyotp | 2.10.0 | MIT | Segundo factor de autenticación |
| qrcode | 8.2 | BSD | Código QR de activación |
| Pillow | 12.2.0 | MIT-CMU | Imagen del código QR |
| pandas | 3.0.2 | BSD 3-Clause | Procesamiento de datos |
| NumPy | 2.4.4 | BSD 3-Clause y otras | Cálculo numérico |
| PyArrow | 25.0.1 | Apache 2.0 | Archivos Parquet del data lake |
| PySpark | 3.5.3 | Apache 2.0 | Procesamiento Big Data |
| scikit-learn | 1.8.0 | BSD 3-Clause | Predicción y detección de anomalías |
| XlsxWriter | 3.2.9 | BSD 2-Clause | Exportación a Excel |
| pytest | 9.1.1 | MIT | Pruebas automatizadas |
| EasyOCR (opcional) | — | Apache 2.0 | Lectura de etiquetas |

Las licencias MIT, BSD y Apache 2.0 permiten el uso académico y comercial siempre que se conserve
el aviso de derechos de autor, cosa que se cumple al no modificar las bibliotecas y al declarar su
procedencia en este documento.

---

## 3. Punto que exige atención: MySQL

**MySQL Community Server** se distribuye bajo **GPL v2**, y el conector oficial de Python también,
con la llamada *FOSS License Exception*.

Qué significa en la práctica:

- **Para este proyecto académico no hay problema.** El uso interno, la investigación y la docencia
  están cubiertos.
- **Si el sistema se publicara como software privativo**, la GPL obligaría a liberar el código
  bajo una licencia compatible, o exigiría adquirir una licencia comercial de MySQL a Oracle.
- La excepción FOSS resuelve precisamente ese caso: permite usar el conector desde software libre
  aunque no sea GPL, siempre que esté bajo una de las licencias de la lista aprobada.

Por eso, si el repositorio va a declarar una licencia, **la GPL v3 es la opción más segura**:
elimina cualquier duda sobre la compatibilidad con el conector de MySQL. Otra salida es sustituir
MySQL por PostgreSQL, cuya licencia es de tipo BSD y no impone esta condición.

---

## 4. Tipografías

El sistema usa la familia **IBM Plex Sans** e **IBM Plex Mono**, diseñadas por IBM y publicadas
bajo la **SIL Open Font License 1.1**. Esa licencia permite usarlas, incrustarlas y redistribuirlas
libremente, incluso con fines comerciales, con dos condiciones: no venderlas por separado y no
usar los nombres reservados en versiones modificadas. El proyecto no modifica las fuentes.

Actualmente se cargan desde el servicio público de Google Fonts. Esto tiene una implicación de
privacidad que ya se declara en la política de cookies: la dirección de red del navegador queda
visible para ese servicio.

**Para un despliegue institucional conviene alojarlas localmente**, cosa que la licencia permite:

1. Descargar la familia desde `https://github.com/IBM/plex` (o desde Google Fonts).
2. Copiar los archivos `.woff2` a `app/static/fuentes/`.
3. En `app/estilos.py`, reemplazar el `@import` por reglas `@font-face` que apunten a esa carpeta.
4. Incluir el archivo de licencia `OFL.txt` junto a las fuentes, como exige la OFL.

---

## 5. Modelo de lenguaje del agente

El agente funciona con un motor de reglas propio y, opcionalmente, con un modelo de lenguaje
ejecutado localmente mediante **Ollama** (licencia MIT).

El modelo de la configuración recomendada es **Qwen2.5 7B Instruct**, de Alibaba Cloud, publicado
bajo **licencia Apache 2.0**, que permite el uso comercial. Conviene tener presente que otros
tamaños de la misma familia, y otros modelos abiertos, tienen licencias distintas y algunas
restringen el uso comercial. **Si se cambia de modelo hay que verificar su licencia**, que suele
estar en la ficha del modelo en Hugging Face o en el catálogo de Ollama.

Los pesos del modelo no se incluyen en el repositorio: se descargan por separado.

---

## 6. Datos

| Fuente | Naturaleza | Condiciones |
|---|---|---|
| Inventario, consumos e histórico de la demostración | **Sintéticos**, generados por `src/bigdata/simulador.py` | Obra propia del proyecto |
| Nombres y concentraciones de los medicamentos | Denominaciones genéricas de uso común en reanimación | No son objeto de derechos de autor |
| Costos unitarios del catálogo | Valores de referencia inventados para la simulación | No corresponden a precios reales |
| Código Único de Medicamentos (CUM) | Datos abiertos del Estado colombiano, publicados en datos.gov.co | Ley 1712 de 2014 de transparencia; uso libre citando la fuente |
| `data/referencia/cum_muestra.json` | **Muestra sintética** con la estructura del CUM, para cuando la interfaz pública no responde | Obra propia; cada registro está marcado como sintético |

No se utilizan fotografías, iconos ni ilustraciones de terceros. Los elementos gráficos de la
interfaz (el trazado del monitor, el semáforo de carros, los marcos) están dibujados con código
dentro del propio proyecto.

---

## 7. Marcas de terceros

Se mencionan de forma descriptiva, para indicar compatibilidad, y pertenecen a sus titulares:
Microsoft Authenticator y Google Authenticator (aplicaciones de segundo factor), MySQL y Oracle,
Windows, Docker, GitHub, Hugging Face. El proyecto no está afiliado, patrocinado ni avalado por
ninguna de estas organizaciones, y no reproduce sus logotipos.

---

## 7 bis. Herramientas de desarrollo que no se distribuyen con el sistema

En `.claude/skills/impeccable` está instalado **Impeccable** (pbakaus/impeccable), un conjunto de
reglas de diseño de interfaz que se usó para auditar y corregir el frontend. Su licencia es
**Apache 2.0**, que permite uso, modificación y distribución conservando el aviso de copyright y
el archivo LICENSE (ambos vienen dentro de la carpeta del paquete).

Es una herramienta de autoría, no una dependencia: no se importa desde ningún módulo, no viaja en
`requirements.txt` y el sistema funciona igual si se borra la carpeta. Se deja en el repositorio
para que cualquier cambio posterior en la interfaz pueda revisarse con el mismo criterio.

---

## 8. Cómo volver a verificar las licencias

Tras actualizar dependencias, dentro del entorno virtual:

```powershell
pip install pip-licenses
pip-licenses --format=markdown --with-urls --order=license
```

Ese listado debe compararse con la tabla del apartado 2. Cualquier dependencia nueva con licencia
copyleft (GPL, AGPL, LGPL) debe revisarse antes de incorporarla, porque afecta las condiciones
bajo las cuales puede distribuirse el proyecto completo.

---

## 9. Advertencia

Este documento es un inventario técnico preparado por el equipo del proyecto, no un concepto
jurídico. Para una publicación del sistema fuera del ámbito académico, la elección de licencia y
el cumplimiento de las condiciones de terceros deben ser revisados por el área jurídica de la
institución.
