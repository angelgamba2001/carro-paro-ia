"""
Crea el esquema v2 y carga datos maestros y de demostración.

    python scripts/inicializar_bd.py                 # esquema + datos demo
    python scripts/inicializar_bd.py --sin-cambio    # demo sin exigir cambio de clave al primer ingreso

Contraseña inicial de todos los usuarios demo: la de --password (por defecto Carro#Paro2026).
"""
import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mysql.connector  # noqa: E402

from src import config  # noqa: E402
from src.bigdata.simulador import eventos_codigo_azul  # noqa: E402
from src.datos_referencia import CARROS, MEDICAMENTOS, SERVICIOS, USUARIOS_DEMO  # noqa: E402
from src.seguridad.contrasenas import hash_password, validar_politica  # noqa: E402
from src.seguridad.permisos import MATRIZ, PERMISOS, ROLES  # noqa: E402

DIAS_OPERACION = 60   # movimientos recientes en la base operativa


def crear_esquema():
    sql = (config.RAIZ / "base de datos" / "carro_paro_db.sql").read_text(encoding="utf-8")
    conn = mysql.connector.connect(host=config.DB_HOST, port=config.DB_PORT,
                                   user=config.DB_USER, password=config.DB_PASSWORD)
    cur = conn.cursor()
    for sentencia in sql.split(";\n"):
        lineas = [l for l in sentencia.splitlines() if not l.strip().startswith("--")]
        s = "\n".join(lineas).strip()
        if s:
            cur.execute(s)
    conn.commit()
    cur.close()
    conn.close()
    print("✔ Esquema v2 creado")


def cargar_datos(password: str, exigir_cambio: bool, semilla: int = 2026):
    rng = random.Random(semilla)
    conn = mysql.connector.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
                                   password=config.DB_PASSWORD, database=config.DB_NAME)
    cur = conn.cursor()

    cur.executemany("INSERT INTO roles (codigo, nombre, descripcion) VALUES (%s,%s,%s)",
                    [(k, v[0], v[1]) for k, v in ROLES.items()])
    cur.executemany("INSERT INTO permisos (codigo, descripcion) VALUES (%s,%s)", list(PERMISOS.items()))
    cur.executemany("INSERT INTO rol_permiso (rol, permiso) VALUES (%s,%s)",
                    [(r, p) for r, ps in MATRIZ.items() for p in sorted(ps)])
    print(f"✔ {len(ROLES)} roles, {len(PERMISOS)} permisos")

    h = hash_password(password)
    cur.executemany("INSERT INTO usuarios (nombre, correo, password_hash, rol, debe_cambiar_password) "
                    "VALUES (%s,%s,%s,%s,%s)", [(n, c, h, r, int(exigir_cambio)) for n, c, r in USUARIOS_DEMO])
    print(f"✔ {len(USUARIOS_DEMO)} usuarios demo (uno por rol)")

    cur.executemany("INSERT INTO servicios (nombre) VALUES (%s)", [(s,) for s in SERVICIOS])
    cur.execute("SELECT id, nombre FROM servicios")
    serv_id = {n: i for i, n in cur.fetchall()}
    cur.executemany("INSERT INTO carros (codigo, servicio_id, ubicacion) VALUES (%s,%s,%s)",
                    [(c, serv_id[s], u) for c, s, u in CARROS])
    cur.execute("SELECT id, codigo FROM carros")
    carro_id = {c: i for i, c in cur.fetchall()}

    cur.executemany("INSERT INTO cat_medicamentos (nombre, principio_activo, criticidad, stock_minimo, "
                    "stock_maximo, costo_unitario, descripcion) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    [(n, pa, c, mn, mx, costo, "Dotación de carro de paro")
                     for n, pa, c, mn, mx, costo, _ in MEDICAMENTOS])
    cur.execute("SELECT id, nombre FROM cat_medicamentos")
    med_id = {n: i for i, n in cur.fetchall()}
    print(f"✔ {len(CARROS)} carros en {len(SERVICIOS)} servicios, {len(MEDICAMENTOS)} medicamentos")

    cur.execute("SELECT id, rol FROM usuarios")
    usuarios = dict(cur.fetchall())
    operativos = [i for i, r in usuarios.items() if r in ("ENFERMERO", "MEDICO")]
    regente = next(i for i, r in usuarios.items() if r == "REGENTE_FARMACIA")

    # --- Inventario actual: lotes con vencimientos variados y algunos faltantes ---
    hoy = date.today()
    lotes = 0
    for codigo, _s, _u in CARROS:
        for nombre, _pa, _c, mn, mx, _costo, _t in MEDICAMENTOS:
            r = rng.random()
            objetivo = mx if r > 0.04 else rng.randint(0, max(0, mn - 1))  # ~4% bajo el mínimo
            restante = objetivo
            while restante > 0:
                cant = restante if rng.random() < 0.6 else rng.randint(1, restante)
                x = rng.random()
                if x < 0.015:
                    venc = hoy - timedelta(days=rng.randint(1, 40))
                elif x < 0.07:
                    venc = hoy + timedelta(days=rng.randint(1, 30))
                else:
                    venc = hoy + timedelta(days=rng.randint(45, 720))
                dias = (venc - hoy).days
                estado = "vencido" if dias < 0 else ("proximo_a_vencer" if dias <= 30 else "vigente")
                lote = f"L{rng.randint(10000, 99999)}"
                cur.execute("INSERT INTO inventario_carro (carro_id, medicamento_id, usuario_id, lote, cantidad, "
                            "fecha_registro, fecha_vencimiento, estado, origen_registro) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'MIGRACION')",
                            (carro_id[codigo], med_id[nombre], regente, lote, cant,
                             hoy - timedelta(days=rng.randint(DIAS_OPERACION, 200)), venc, estado))
                lotes += 1
                restante -= cant
    print(f"✔ {lotes} lotes en inventario")

    # --- Movimientos recientes de la base operativa (continúan el histórico) ---
    desde = hoy - timedelta(days=DIAS_OPERACION)
    filas = []
    for ts, carro, _serv, id_evento, usados in eventos_codigo_azul(desde, hoy - timedelta(days=1), semilla=semilla):
        u = rng.choice(operativos)
        for med, unidades in usados:
            filas.append((carro_id[carro], med_id[med], u, "CONSUMO", unidades, f"Evento {id_evento}", 1, ts))
    cur.executemany("INSERT INTO movimientos (carro_id, medicamento_id, usuario_id, tipo, cantidad, motivo, "
                    "evento_codigo_azul, fecha) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", filas)
    print(f"✔ {len(filas)} movimientos de consumo en los últimos {DIAS_OPERACION} días")

    conn.commit()
    cur.close()
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", default="Carro#Paro2026")
    ap.add_argument("--sin-cambio", action="store_true", help="No exigir cambio de contraseña al primer ingreso")
    ap.add_argument("--sin-esquema", action="store_true", help="No recrear el esquema (ya existe y está vacío)")
    a = ap.parse_args()
    errores = validar_politica(a.password)
    if errores:
        sys.exit("La contraseña demo no cumple la política: " + " ".join(errores))
    if not a.sin_esquema:
        crear_esquema()
    cargar_datos(a.password, exigir_cambio=not a.sin_cambio)

    from src.servicios.inventario import recalcular_estados
    print("✔ Alertas iniciales:", recalcular_estados())
    print(f"\nListo. Usuarios: admin@hospital.com, enfermero@hospital.com, ... | Contraseña: {a.password}")


if __name__ == "__main__":
    main()
