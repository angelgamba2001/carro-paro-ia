"""
Simulador de datos operativos del carro de paro.

Se usa para: (1) el histórico "legado" que alimenta el data lake (varios años de
revisiones diarias y consumos por código azul) y (2) los movimientos recientes de
la base operativa. Los datos son sintéticos pero con patrones realistas:
estacionalidad (temporadas de lluvia/respiratorias en Colombia), diferencias por
servicio, y ruido de calidad (duplicados, nombres inconsistentes, fechas en varios
formatos, nulos) para que la etapa de limpieza del pipeline tenga sentido.
"""
import math
import random
from datetime import date, datetime, timedelta

from src.datos_referencia import CARROS, MEDICAMENTOS, TASA_CODIGO_AZUL

# Picos respiratorios/lluvias (abr-may, oct-nov) -> más eventos
_ESTACIONAL = {1: 0.9, 2: 0.9, 3: 1.0, 4: 1.25, 5: 1.3, 6: 1.05, 7: 0.95, 8: 0.95,
               9: 1.0, 10: 1.2, 11: 1.25, 12: 1.1}


def _factor_dia(d: date, tendencia_anual: float, inicio: date) -> float:
    anios = (d - inicio).days / 365.0
    fin_semana = 1.15 if d.weekday() >= 5 else 1.0
    return _ESTACIONAL[d.month] * fin_semana * (1 + tendencia_anual) ** anios


def _nombre_sucio(nombre: str, rng: random.Random) -> str:
    """Variantes reales de digitación que la limpieza debe normalizar."""
    r = rng.random()
    if r < 0.06:
        return nombre.upper()
    if r < 0.10:
        return f"  {nombre} "
    if r < 0.13:
        return nombre.replace("mg/ml", " mg/ml").replace("mg/", " mg/")
    return nombre


def _fecha_sucia(ts: datetime, rng: random.Random) -> str:
    r = rng.random()
    if r < 0.08:
        return ts.strftime("%d/%m/%Y %H:%M")
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def eventos_codigo_azul(desde: date, hasta: date, semilla: int = 42, tendencia_anual: float = 0.06):
    """Genera (fecha_hora, carro, servicio, id_evento, [(medicamento, unidades)])."""
    rng = random.Random(semilla)
    d = desde
    n = 0
    while d <= hasta:
        for codigo, servicio, _ in CARROS:
            p = TASA_CODIGO_AZUL[servicio] * _factor_dia(d, tendencia_anual, desde)
            eventos = 1 if rng.random() < p else 0
            if eventos and rng.random() < 0.12:
                eventos += 1
            for _ in range(eventos):
                n += 1
                ts = datetime.combine(d, datetime.min.time()) + timedelta(minutes=rng.randint(0, 1439))
                usados = []
                for nombre, _pa, _c, _mn, mx, _costo, tasa in MEDICAMENTOS:
                    lam = tasa * (0.6 if "Pediátrica" in servicio or servicio == "Pediatría" else 1.0)
                    # Poisson simple (Knuth), acotado a la dotación máxima
                    L, k, pr = math.exp(-lam), 0, 1.0
                    while True:
                        pr *= rng.random()
                        if pr <= L:
                            break
                        k += 1
                    if k:
                        usados.append((nombre, min(k, mx)))
                if usados:
                    yield ts, codigo, servicio, f"CA-{d:%Y%m%d}-{n:06d}", usados
        d += timedelta(days=1)


def filas_consumo_historico(desde: date, hasta: date, semilla: int = 42):
    """Consumos en formato de exportación del sistema anterior (con ruido)."""
    rng = random.Random(semilla + 1)
    for ts, carro, servicio, id_evento, usados in eventos_codigo_azul(desde, hasta, semilla):
        for med, unidades in usados:
            fila = {
                "fecha_hora": _fecha_sucia(ts, rng),
                "carro": carro,
                "servicio": servicio,
                "medicamento": _nombre_sucio(med, rng),
                "cantidad": unidades,
                "tipo": "CONSUMO",
                "id_evento": id_evento,
            }
            r = rng.random()
            if r < 0.004:
                fila["cantidad"] = None          # nulo
            elif r < 0.006:
                fila["cantidad"] = -unidades     # signo erróneo
            yield fila
            if rng.random() < 0.015:
                yield dict(fila)                 # duplicado exacto


def filas_revision_diaria(desde: date, hasta: date, semilla: int = 7):
    """Lista de chequeo diaria (verificación del carro por turno), un registro por medicamento."""
    rng = random.Random(semilla)
    responsables = [f"ENF-{i:03d}" for i in range(1, 41)]
    d = desde
    while d <= hasta:
        for codigo, servicio, _ in CARROS:
            # el cumplimiento de la revisión mejora con el tiempo y es peor fines de semana
            anios = (d - desde).days / 365.0
            p_revision = min(0.98, 0.80 + 0.04 * anios) - (0.07 if d.weekday() >= 5 else 0)
            revisado = rng.random() < p_revision
            responsable = rng.choice(responsables) if revisado else ""
            for nombre, _pa, _c, _mn, mx, _costo, _t in MEDICAMENTOS:
                contada = mx
                if revisado and rng.random() < 0.02:
                    contada = max(0, mx - rng.randint(1, 2))   # discrepancia
                yield {
                    "fecha": d.isoformat() if rng.random() > 0.05 else d.strftime("%d/%m/%Y"),
                    "carro": codigo,
                    "medicamento": _nombre_sucio(nombre, rng),
                    "cantidad_esperada": mx,
                    "cantidad_contada": contada if revisado else None,
                    "revisado": int(revisado),
                    "responsable": responsable,
                }
        d += timedelta(days=1)


def filas_bajas_historicas(desde: date, hasta: date, semilla: int = 11):
    """Bajas por vencimiento: principalmente en carros de bajo uso y medicamentos de baja rotación."""
    rng = random.Random(semilla)
    d = desde
    while d <= hasta:
        if d.day == 1:  # cierre mensual de farmacia
            for codigo, servicio, _ in CARROS:
                bajo_uso = TASA_CODIGO_AZUL[servicio] < 0.08
                for nombre, _pa, _c, _mn, mx, _costo, tasa in MEDICAMENTOS:
                    p = (0.10 if bajo_uso else 0.04) * (1.5 if tasa < 0.5 else 0.7)
                    if rng.random() < p:
                        yield {"fecha": d.isoformat(), "carro": codigo, "medicamento": nombre,
                               "cantidad": rng.randint(1, mx), "tipo": "BAJA_VENCIMIENTO"}
        d += timedelta(days=1)
