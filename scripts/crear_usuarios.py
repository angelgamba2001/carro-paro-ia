"""
Alta de varias cuentas de una sola vez, sin pasar por el registro ni por la pantalla.

Una cuenta suelta:

    python scripts/crear_usuarios.py "Ana Ruiz" ana.ruiz@gmail.com MEDICO

Varias, desde un archivo CSV con las columnas nombre,correo,rol:

    python scripts/crear_usuarios.py --archivo usuarios.csv

Opciones:
    --password CLAVE   Misma contraseña para todas (para demostraciones).
                       Sin esto, a cada una se le genera una distinta y segura.
    --sin-cambio       No obligar a cambiar la contraseña al primer ingreso.
    --roles            Muestra los códigos de rol disponibles y termina.

Las cuentas quedan activas y verificadas de inmediato: las crea un administrador,
así que no hay nada que confirmar. Cada persona recibe el correo de bienvenida con
su perfil; la contraseña NO viaja en ese correo —se imprime aquí, para que usted la
entregue por el canal que corresponda—.
"""
import argparse
import csv
import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import consultar, ejecutar      # noqa: E402
from src.seguridad.permisos import ROLES                     # noqa: E402
from src.servicios.errores import ErrorNegocio               # noqa: E402
from src.servicios.usuarios import crear_usuario             # noqa: E402

ALFABETO = string.ascii_letters + string.digits
SIMBOLOS = "!@#$%&*?"


def clave_segura() -> str:
    """Cumple la política: mayúscula, minúscula, número y símbolo."""
    cuerpo = "".join(secrets.choice(ALFABETO) for _ in range(11))
    return (secrets.choice(string.ascii_uppercase) + secrets.choice(string.ascii_lowercase)
            + secrets.choice(string.digits) + secrets.choice(SIMBOLOS) + cuerpo)


def administrador() -> dict:
    """Un ADMIN activo cualquiera: el alta queda registrada a su nombre."""
    u = consultar("SELECT id, nombre, correo, rol, activo FROM usuarios "
                  "WHERE rol = 'ADMIN' AND activo = 1 ORDER BY id LIMIT 1", uno=True)
    if not u:
        raise SystemExit("No hay ningún administrador activo. Ejecute scripts/inicializar_bd.py")
    return u


def filas(args) -> list[tuple[str, str, str]]:
    if args.archivo:
        ruta = Path(args.archivo)
        if not ruta.exists():
            raise SystemExit(f"No encuentro el archivo {ruta}")
        with ruta.open(encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            faltan = {"nombre", "correo", "rol"} - set(h.strip().lower() for h in lector.fieldnames or [])
            if faltan:
                raise SystemExit(f"Al CSV le faltan columnas: {', '.join(sorted(faltan))}")
            return [(r["nombre"].strip(), r["correo"].strip(), r["rol"].strip().upper())
                    for r in lector if r.get("correo", "").strip()]
    if len(args.datos) != 3:
        raise SystemExit('Use:  python scripts/crear_usuarios.py "Nombre Apellido" correo@dominio.com ROL\n'
                         "       o bien  --archivo usuarios.csv")
    return [(args.datos[0], args.datos[1], args.datos[2].upper())]


def main():
    p = argparse.ArgumentParser(add_help=True, description="Crea cuentas en lote.")
    p.add_argument("datos", nargs="*", help="nombre, correo y rol de una sola cuenta")
    p.add_argument("--archivo", help="CSV con columnas nombre,correo,rol")
    p.add_argument("--password", help="misma contraseña para todas")
    p.add_argument("--sin-cambio", action="store_true",
                   help="no exigir cambio de contraseña al primer ingreso")
    p.add_argument("--roles", action="store_true", help="lista los roles y termina")
    args = p.parse_args()

    if args.roles:
        print("Roles disponibles:\n")
        for codigo, valor in ROLES.items():
            print(f"  {codigo:20} {valor[0]}")
        return 0

    admin = administrador()
    pendientes = filas(args)
    print(f"Creando {len(pendientes)} cuenta(s) a nombre de {admin['nombre']}.\n")

    creadas, errores = [], []
    for nombre, correo, rol in pendientes:
        if rol not in ROLES:
            errores.append((correo, f"rol desconocido: {rol}. Use --roles para ver la lista"))
            continue
        clave = args.password or clave_segura()
        try:
            nuevo = crear_usuario(admin, nombre, correo, clave, rol)
        except ErrorNegocio as e:
            errores.append((correo, str(e)))
            continue
        if args.sin_cambio:
            ejecutar("UPDATE usuarios SET debe_cambiar_password = 0 WHERE id = %s", (nuevo,))
        # Creada por un administrador: no hay correo que verificar ni nada que aprobar
        ejecutar("UPDATE usuarios SET estado = 'ACTIVO', correo_verificado = 1, activo = 1 "
                 "WHERE id = %s", (nuevo,))
        creadas.append((nombre, correo, ROLES[rol][0], clave))

    if creadas:
        ancho = max(len(c[1]) for c in creadas)
        print(f"  {'CORREO'.ljust(ancho)}  {'PERFIL'.ljust(22)}  CONTRASEÑA")
        print(f"  {'-' * ancho}  {'-' * 22}  {'-' * 16}")
        for _, correo, perfil, clave in creadas:
            print(f"  {correo.ljust(ancho)}  {perfil.ljust(22)}  {clave}")
        print(f"\n{len(creadas)} cuenta(s) creada(s) y activa(s).")
        print("Cada persona recibió el correo de bienvenida con su perfil.")
        print("La contraseña NO va en ese correo: entréguesela usted por otro canal.")
        if not args.sin_cambio:
            print("Se les exigirá cambiarla en el primer ingreso.")

    if errores:
        print(f"\n{len(errores)} no se pudo(pudieron) crear:")
        for correo, motivo in errores:
            print(f"  {correo}: {motivo}")
    return 1 if errores and not creadas else 0


if __name__ == "__main__":
    raise SystemExit(main())
