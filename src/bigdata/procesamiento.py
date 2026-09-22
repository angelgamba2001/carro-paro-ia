"""
Procesamiento Big Data: RAW -> BRONZE -> SILVER -> GOLD (arquitectura medallón).

  BRONZE  datos tal como llegaron + metadatos de linaje (_fuente, _archivo, _fecha_ingesta)
  SILVER  datos limpios: tipos correctos, fechas unificadas, nombres de medicamento
          normalizados contra el catálogo, sin duplicados, nulos ni cantidades inválidas;
          fuentes integradas (histórico legado + base operativa + CUM)
  GOLD    agregados listos para analítica y dashboard

Motor principal: PySpark. Motor alterno: pandas (mismas reglas), útil para
depurar o si en Windows no está configurado Java. Se elige con MOTOR_BIGDATA.

Nota Windows: Spark necesita winutils.exe para ESCRIBIR en disco local. Para evitar
ese requisito, Spark hace todo el procesamiento y la escritura final a Parquet se
hace con pyarrow (función _guardar). En Linux/Docker no hay diferencia.
"""
import glob
import json
import os
import sys
import time
import unicodedata
from datetime import datetime

import pandas as pd

from src import config

SILVER = ("consumos", "revisiones", "bajas", "catalogo_enriquecido")
GOLD = ("consumo_diario", "consumo_semanal", "consumo_mensual_servicio", "eventos_mensuales",
        "revisiones_mensual", "bajas_mensual", "catalogo_enriquecido", "calidad_datos")


# ---------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------
def clave_medicamento(texto) -> str:
    """'  ADRENALINA 1 mg/ml ' -> 'adrenalina1mg/ml' (sin espacios, minúsculas, sin tildes)."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return "".join(t.lower().split())


def _guardar(df: pd.DataFrame, zona, nombre: str):
    zona.mkdir(parents=True, exist_ok=True)
    df.to_parquet(zona / f"{nombre}.parquet", index=False)


def _ultimo_corte_operativo():
    cortes = sorted((config.RAW_DIR / "operativo").glob("corte=*"))
    if not cortes:
        raise FileNotFoundError("No hay exportación operativa en RAW. Ejecute primero la ingesta.")
    return cortes[-1]


def _ultimo_cum():
    archivos = sorted((config.RAW_DIR / "cum").glob("cum_*.json"))
    if not archivos:
        raise FileNotFoundError("No hay datos CUM en RAW. Ejecute primero la ingesta.")
    return archivos[-1]


def _cum_normalizado(ruta) -> pd.DataFrame:
    """El JSON de datos abiertos puede cambiar de nombres de columna: se busca la primera coincidente."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    df = pd.DataFrame(datos)
    df.columns = [c.lower() for c in df.columns]

    def col(*candidatas):
        for c in candidatas:
            if c in df.columns:
                return df[c].astype(str)
        return pd.Series([""] * len(df))

    out = pd.DataFrame({
        "principio_activo": col("principioactivo", "principio_activo"),
        "titular": col("titular"),
        "registro_sanitario": col("registrosanitario", "registro_sanitario"),
        "estado_registro": col("estadoregistro", "estado_registro"),
    })
    out["clave_pa"] = out["principio_activo"].map(lambda x: clave_medicamento(x).split("(")[0])
    return out


def _enriquecer_catalogo(catalogo: pd.DataFrame, cum: pd.DataFrame) -> pd.DataFrame:
    catalogo = catalogo.copy()
    catalogo["clave_pa"] = catalogo["principio_activo"].map(clave_medicamento)
    filas = []
    for _, m in catalogo.iterrows():
        coincide = cum[cum["clave_pa"].str.contains(m["clave_pa"][:8], regex=False)] if m["clave_pa"] else cum.iloc[0:0]
        vigentes = coincide[coincide["estado_registro"].str.lower().str.startswith("vigente")]
        filas.append({
            "medicamento": m["nombre"], "principio_activo": m["principio_activo"],
            "criticidad": m["criticidad"], "costo_unitario": float(m["costo_unitario"]),
            "registros_cum": len(coincide), "registros_vigentes": len(vigentes),
            "titulares_distintos": vigentes["titular"].nunique(),
            "riesgo_proveedor": "ALTO" if vigentes["titular"].nunique() <= 1 else
                                ("MEDIO" if vigentes["titular"].nunique() == 2 else "BAJO"),
        })
    return pd.DataFrame(filas)


def _gold_desde_silver(consumos: pd.DataFrame, revisiones: pd.DataFrame, bajas: pd.DataFrame,
                       carros: pd.DataFrame, catalogo: pd.DataFrame) -> dict:
    """Agregaciones GOLD. Se hacen sobre SILVER ya reducido; comunes a ambos motores."""
    c = consumos.copy()
    c["fecha"] = pd.to_datetime(c["fecha_hora"]).dt.normalize()
    diario = (c.groupby(["fecha", "carro", "servicio", "medicamento"], as_index=False)
                .agg(unidades=("cantidad", "sum"), eventos=("id_evento", "nunique")))
    diario["semana"] = diario["fecha"].dt.to_period("W-SUN").dt.start_time
    semanal = (diario.groupby(["semana", "carro", "servicio", "medicamento"], as_index=False)
                     .agg(unidades=("unidades", "sum"), eventos=("eventos", "sum")))
    diario["mes"] = diario["fecha"].dt.to_period("M").dt.start_time
    mensual = (diario.groupby(["mes", "servicio", "medicamento"], as_index=False)
                     .agg(unidades=("unidades", "sum")))
    ev = c.drop_duplicates("id_evento").assign(mes=lambda x: x["fecha"].dt.to_period("M").dt.start_time)
    eventos = ev.groupby(["mes", "servicio"], as_index=False).agg(eventos_codigo_azul=("id_evento", "count"))

    r = revisiones.copy()
    r["mes"] = pd.to_datetime(r["fecha"]).dt.to_period("M").dt.start_time
    por_dia = (r.groupby(["mes", "carro", "fecha"], as_index=False)
                .agg(revisado=("revisado", "max"),
                     discrepancias=("discrepancia", "sum")))
    rev_mes = (por_dia.groupby(["mes", "carro"], as_index=False)
                      .agg(dias=("fecha", "count"), dias_revisados=("revisado", "sum"),
                           discrepancias=("discrepancias", "sum")))
    rev_mes["cumplimiento_pct"] = (100 * rev_mes["dias_revisados"] / rev_mes["dias"]).round(1)

    b = bajas.merge(catalogo[["nombre", "costo_unitario"]], left_on="medicamento", right_on="nombre", how="left")
    b["mes"] = pd.to_datetime(b["fecha"]).dt.to_period("M").dt.start_time
    b["costo"] = b["cantidad"] * b["costo_unitario"].astype(float)
    bajas_mes = (b.groupby(["mes", "carro", "medicamento"], as_index=False)
                  .agg(unidades=("cantidad", "sum"), costo=("costo", "sum")))
    bajas_mes = bajas_mes.merge(carros[["codigo", "servicio"]], left_on="carro", right_on="codigo",
                                how="left").drop(columns="codigo")
    return {"consumo_diario": diario, "consumo_semanal": semanal, "consumo_mensual_servicio": mensual,
            "eventos_mensuales": eventos, "revisiones_mensual": rev_mes, "bajas_mensual": bajas_mes}


# ---------------------------------------------------------------------------
# Motor PySpark
# ---------------------------------------------------------------------------
def _spark():
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    from pyspark.sql import SparkSession
    # Java 17/21: Arrow (toPandas) necesita acceso a java.nio
    opciones_java = ("-Dio.netty.tryReflectionSetAccessible=true "
                     "--add-opens=java.base/java.nio=ALL-UNNAMED "
                     "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED")
    return (SparkSession.builder.appName("SMARTDATA360-CarroParo")
            .config("spark.driver.extraJavaOptions", opciones_java)
            .config("spark.executor.extraJavaOptions", opciones_java)
            .master(os.getenv("SPARK_MASTER", "local[*]"))
            .config("spark.sql.shuffle.partitions", "8")
            .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "2g"))
            .config("spark.sql.legacy.timeParserPolicy", "CORRECTED")
            .config("spark.sql.execution.arrow.pyspark.enabled", os.getenv("SPARK_ARROW", "false"))
            .config("spark.ui.showConsoleProgress", "false")
            .getOrCreate())


def _procesar_spark(corte, cum_ruta, calidad: list) -> dict:
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    spark = _spark()
    spark.sparkContext.setLogLevel("ERROR")
    ahora = F.current_timestamp()

    def leer(patron, fuente):
        df = spark.read.option("header", True).option("inferSchema", False).csv(patron)
        return (df.withColumn("_fuente", F.lit(fuente))
                  .withColumn("_archivo", F.input_file_name())
                  .withColumn("_fecha_ingesta", ahora))

    def clave(col):
        limpio = F.lower(F.regexp_replace(F.col(col), r"\s+", ""))
        return F.translate(limpio, "áéíóúñÁÉÍÓÚÑ", "aeiounAEIOUN")

    def fecha(col):
        return F.coalesce(F.to_timestamp(F.col(col), "yyyy-MM-dd HH:mm:ss"),
                          F.to_timestamp(F.col(col), "yyyy-MM-dd"),
                          F.to_timestamp(F.col(col), "dd/MM/yyyy HH:mm"),
                          F.to_timestamp(F.col(col), "dd/MM/yyyy"))

    def medir(nombre, antes, despues, regla):
        calidad.append({"tabla": nombre, "regla": regla, "filas_antes": antes, "filas_despues": despues,
                        "descartadas": antes - despues})

    # ---------- BRONZE ----------
    raw = config.RAW_DIR
    b_consumo_hist = leer(str(raw / "consumos" / "anio=*" / "*.csv"), "historico_legado")
    b_revisiones = leer(str(raw / "revisiones" / "anio=*" / "*.csv"), "historico_legado")
    b_bajas_hist = leer(str(raw / "bajas" / "anio=*" / "*.csv"), "historico_legado")
    b_mov = leer(str(corte / "movimientos.csv"), "mysql_operativo")
    catalogo_pd = pd.read_csv(corte / "catalogo.csv")
    carros_pd = pd.read_csv(corte / "carros.csv")
    for nombre, df in (("consumos", b_consumo_hist), ("revisiones", b_revisiones),
                       ("bajas", b_bajas_hist), ("movimientos_operativo", b_mov)):
        _guardar(df.toPandas(), config.BRONZE_DIR, nombre)

    catalogo_sp = spark.createDataFrame(catalogo_pd[["nombre"]]).withColumn("k", clave("nombre"))
    carros_sp = spark.createDataFrame(carros_pd.rename(columns={"codigo": "carro", "servicio": "servicio_cat"})[
        ["carro", "servicio_cat"]])

    def normalizar_med(df):
        return (df.withColumn("k", clave("medicamento")).drop("medicamento")
                  .join(F.broadcast(catalogo_sp), "k", "left")
                  .withColumnRenamed("nombre", "medicamento").drop("k"))

    # ---------- SILVER: consumos (histórico + operativo integrados) ----------
    hist = b_consumo_hist.select(
        fecha("fecha_hora").alias("fecha_hora"), F.trim("carro").alias("carro"), "medicamento",
        F.col("cantidad").cast("int").alias("cantidad"), "id_evento", "_fuente")
    oper = (b_mov.filter(F.col("tipo") == "CONSUMO")
                 .select(fecha("fecha").alias("fecha_hora"), "carro", "medicamento",
                         F.col("cantidad").cast("int").alias("cantidad"),
                         F.concat(F.lit("OP-"), F.col("motivo")).alias("id_evento"), "_fuente"))
    consumos = hist.unionByName(oper)
    n0 = consumos.count()
    consumos = consumos.dropDuplicates(["fecha_hora", "carro", "medicamento", "cantidad", "id_evento"])
    n1 = consumos.count(); medir("consumos", n0, n1, "duplicados exactos")
    consumos = consumos.filter(F.col("fecha_hora").isNotNull() & (F.col("fecha_hora") <= ahora))
    n2 = consumos.count(); medir("consumos", n1, n2, "fecha nula, inválida o futura")
    consumos = consumos.filter(F.col("cantidad").isNotNull() & (F.col("cantidad") > 0))
    n3 = consumos.count(); medir("consumos", n2, n3, "cantidad nula o no positiva")
    consumos = normalizar_med(consumos).filter(F.col("medicamento").isNotNull())
    n4 = consumos.count(); medir("consumos", n3, n4, "medicamento no reconocido en catálogo")
    consumos = consumos.join(F.broadcast(carros_sp), "carro", "inner").withColumnRenamed("servicio_cat", "servicio")
    n5 = consumos.count(); medir("consumos", n4, n5, "carro no reconocido")

    # ---------- SILVER: revisiones ----------
    rev = b_revisiones.select(
        F.to_date(fecha("fecha")).alias("fecha"), F.trim("carro").alias("carro"), "medicamento",
        F.col("cantidad_esperada").cast("int").alias("cantidad_esperada"),
        F.col("cantidad_contada").cast("int").alias("cantidad_contada"),
        F.col("revisado").cast("int").alias("revisado"), "responsable")
    m0 = rev.count()
    rev = rev.dropDuplicates(["fecha", "carro", "medicamento"]).filter(F.col("fecha").isNotNull())
    m1 = rev.count(); medir("revisiones", m0, m1, "duplicados / fecha inválida")
    rev = normalizar_med(rev).filter(F.col("medicamento").isNotNull())
    rev = rev.withColumn("discrepancia", F.when(
        (F.col("revisado") == 1) & (F.col("cantidad_contada") < F.col("cantidad_esperada")), 1).otherwise(0))
    m2 = rev.count(); medir("revisiones", m1, m2, "medicamento no reconocido")

    # ---------- SILVER: bajas ----------
    bajas = (b_bajas_hist.select(F.to_date(fecha("fecha")).alias("fecha"), "carro", "medicamento",
                                 F.col("cantidad").cast("int").alias("cantidad"))
             .unionByName(b_mov.filter(F.col("tipo") == "BAJA_VENCIMIENTO")
                               .select(F.to_date(fecha("fecha")).alias("fecha"), "carro", "medicamento",
                                       F.col("cantidad").cast("int").alias("cantidad"))))
    bajas = normalizar_med(bajas).filter(F.col("cantidad") > 0)

    # Ejemplo de ventana Spark: consumo acumulado por carro-medicamento (usado en validaciones)
    w = Window.partitionBy("carro", "medicamento").orderBy("fecha_hora")
    consumos = consumos.withColumn("acumulado_carro_med", F.sum("cantidad").over(w))

    silver = {
        "consumos": consumos.toPandas(),
        "revisiones": rev.toPandas(),
        "bajas": bajas.toPandas(),
    }
    spark.stop()
    return silver, catalogo_pd, carros_pd


# ---------------------------------------------------------------------------
# Motor pandas (mismas reglas; útil para depurar o sin Java)
# ---------------------------------------------------------------------------
def _fecha_pd(serie: pd.Series) -> pd.Series:
    iso = pd.to_datetime(serie, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    iso2 = pd.to_datetime(serie, format="%Y-%m-%d", errors="coerce")
    lat = pd.to_datetime(serie, format="%d/%m/%Y %H:%M", errors="coerce")
    lat2 = pd.to_datetime(serie, format="%d/%m/%Y", errors="coerce")
    return iso.fillna(iso2).fillna(lat).fillna(lat2)


def _procesar_pandas(corte, cum_ruta, calidad: list) -> dict:
    raw = config.RAW_DIR

    def leer(patron, fuente):
        partes = []
        for archivo in sorted(glob.glob(patron)):
            d = pd.read_csv(archivo, dtype=str)
            d["_fuente"], d["_archivo"] = fuente, archivo
            partes.append(d)
        df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
        df["_fecha_ingesta"] = pd.Timestamp.now()
        return df

    def medir(nombre, antes, despues, regla):
        calidad.append({"tabla": nombre, "regla": regla, "filas_antes": antes, "filas_despues": despues,
                        "descartadas": antes - despues})

    b_cons = leer(str(raw / "consumos" / "anio=*" / "*.csv"), "historico_legado")
    b_rev = leer(str(raw / "revisiones" / "anio=*" / "*.csv"), "historico_legado")
    b_baj = leer(str(raw / "bajas" / "anio=*" / "*.csv"), "historico_legado")
    b_mov = leer(str(corte / "movimientos.csv"), "mysql_operativo")
    for nombre, df in (("consumos", b_cons), ("revisiones", b_rev), ("bajas", b_baj),
                       ("movimientos_operativo", b_mov)):
        _guardar(df, config.BRONZE_DIR, nombre)

    catalogo = pd.read_csv(corte / "catalogo.csv")
    carros = pd.read_csv(corte / "carros.csv")
    mapa = {clave_medicamento(n): n for n in catalogo["nombre"]}

    def normalizar_med(df):
        df = df.copy()
        df["medicamento"] = df["medicamento"].map(clave_medicamento).map(mapa)
        return df

    hist = pd.DataFrame({"fecha_hora": _fecha_pd(b_cons["fecha_hora"]), "carro": b_cons["carro"].str.strip(),
                         "medicamento": b_cons["medicamento"],
                         "cantidad": pd.to_numeric(b_cons["cantidad"], errors="coerce"),
                         "id_evento": b_cons["id_evento"], "_fuente": b_cons["_fuente"]})
    op = b_mov[b_mov["tipo"] == "CONSUMO"]
    oper = pd.DataFrame({"fecha_hora": _fecha_pd(op["fecha"]), "carro": op["carro"], "medicamento": op["medicamento"],
                         "cantidad": pd.to_numeric(op["cantidad"], errors="coerce"),
                         "id_evento": "OP-" + op["motivo"].astype(str), "_fuente": op["_fuente"]})
    c = pd.concat([hist, oper], ignore_index=True)
    n0 = len(c)
    c = c.drop_duplicates(["fecha_hora", "carro", "medicamento", "cantidad", "id_evento"])
    n1 = len(c); medir("consumos", n0, n1, "duplicados exactos")
    c = c[c["fecha_hora"].notna() & (c["fecha_hora"] <= pd.Timestamp.now())]
    n2 = len(c); medir("consumos", n1, n2, "fecha nula, inválida o futura")
    c = c[c["cantidad"].notna() & (c["cantidad"] > 0)]
    n3 = len(c); medir("consumos", n2, n3, "cantidad nula o no positiva")
    c = normalizar_med(c).dropna(subset=["medicamento"])
    n4 = len(c); medir("consumos", n3, n4, "medicamento no reconocido en catálogo")
    c = c.merge(carros.rename(columns={"codigo": "carro"})[["carro", "servicio"]], on="carro", how="inner")
    n5 = len(c); medir("consumos", n4, n5, "carro no reconocido")
    c["cantidad"] = c["cantidad"].astype(int)
    c = c.sort_values("fecha_hora")
    c["acumulado_carro_med"] = c.groupby(["carro", "medicamento"])["cantidad"].cumsum()

    r = pd.DataFrame({"fecha": _fecha_pd(b_rev["fecha"]).dt.date, "carro": b_rev["carro"].str.strip(),
                      "medicamento": b_rev["medicamento"],
                      "cantidad_esperada": pd.to_numeric(b_rev["cantidad_esperada"], errors="coerce"),
                      "cantidad_contada": pd.to_numeric(b_rev["cantidad_contada"], errors="coerce"),
                      "revisado": pd.to_numeric(b_rev["revisado"], errors="coerce").fillna(0).astype(int),
                      "responsable": b_rev["responsable"]})
    m0 = len(r)
    r = r.drop_duplicates(["fecha", "carro", "medicamento"]).dropna(subset=["fecha"])
    m1 = len(r); medir("revisiones", m0, m1, "duplicados / fecha inválida")
    r = normalizar_med(r).dropna(subset=["medicamento"])
    r["discrepancia"] = ((r["revisado"] == 1) & (r["cantidad_contada"] < r["cantidad_esperada"])).astype(int)
    m2 = len(r); medir("revisiones", m1, m2, "medicamento no reconocido")

    bo = b_mov[b_mov["tipo"] == "BAJA_VENCIMIENTO"]
    b = pd.concat([
        pd.DataFrame({"fecha": _fecha_pd(b_baj["fecha"]).dt.date, "carro": b_baj["carro"],
                      "medicamento": b_baj["medicamento"], "cantidad": pd.to_numeric(b_baj["cantidad"], errors="coerce")}),
        pd.DataFrame({"fecha": _fecha_pd(bo["fecha"]).dt.date, "carro": bo["carro"],
                      "medicamento": bo["medicamento"], "cantidad": pd.to_numeric(bo["cantidad"], errors="coerce")}),
    ], ignore_index=True)
    b = normalizar_med(b)
    b = b[b["cantidad"] > 0].dropna(subset=["medicamento"])

    return {"consumos": c, "revisiones": r, "bajas": b}, catalogo, carros


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------
def ejecutar_procesamiento(motor: str | None = None) -> dict:
    motor = (motor or config.MOTOR_BIGDATA).lower()
    inicio = time.time()
    corte, cum_ruta = _ultimo_corte_operativo(), _ultimo_cum()
    calidad: list = []

    if motor == "spark":
        try:
            silver, catalogo, carros = _procesar_spark(corte, cum_ruta, calidad)
        except Exception as e:  # p. ej. Java no instalado
            print(f"[AVISO] Spark no disponible ({type(e).__name__}: {e}). Se usa el motor pandas.")
            motor, calidad = "pandas (respaldo)", []
            silver, catalogo, carros = _procesar_pandas(corte, cum_ruta, calidad)
    else:
        silver, catalogo, carros = _procesar_pandas(corte, cum_ruta, calidad)

    # Integración con la fuente de datos abiertos (CUM)
    silver["catalogo_enriquecido"] = _enriquecer_catalogo(catalogo, _cum_normalizado(cum_ruta))
    for nombre, df in silver.items():
        _guardar(df, config.SILVER_DIR, nombre)

    gold = _gold_desde_silver(silver["consumos"], silver["revisiones"], silver["bajas"], carros, catalogo)
    gold["catalogo_enriquecido"] = silver["catalogo_enriquecido"]
    gold["calidad_datos"] = pd.DataFrame(calidad)
    for nombre, df in gold.items():
        _guardar(df, config.GOLD_DIR, nombre)

    resumen = {
        "motor": motor,
        "segundos": round(time.time() - inicio, 1),
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "silver_filas": {k: len(v) for k, v in silver.items()},
        "gold_filas": {k: len(v) for k, v in gold.items()},
        "descartadas_limpieza": int(sum(x["descartadas"] for x in calidad)),
    }
    (config.GOLD_DIR / "_ultima_ejecucion.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2),
                                                           encoding="utf-8")
    return resumen


def leer_gold(nombre: str) -> pd.DataFrame:
    ruta = config.GOLD_DIR / f"{nombre}.parquet"
    return pd.read_parquet(ruta) if ruta.exists() else pd.DataFrame()


def ultima_ejecucion() -> dict | None:
    ruta = config.GOLD_DIR / "_ultima_ejecucion.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
