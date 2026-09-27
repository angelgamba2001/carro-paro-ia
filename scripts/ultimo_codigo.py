"""
Muestra el último código que el sistema generó, sin abrir archivos a mano.

    python scripts/ultimo_codigo.py                      # el más reciente
    python scripts/ultimo_codigo.py ana@gmail.com        # el de esa dirección

Solo sirve con CORREO_MODO=archivo, que es el modo de desarrollo. Con el envío
real configurado, el código llega al buzón y este script no tiene nada que leer.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                                   # noqa: E402
from src.servicios.correo import SALIENTE                # noqa: E402

CODIGO = re.compile(r'text-align:center;">\s*([\d\s]{6,20}?)\s*</div>')
CABECERA = re.compile(r"<!-- Para: (.*?) \| Asunto: (.*?) \|")


def main():
    if (config.CORREO_MODO or "").lower() != "archivo":
        print(f"CORREO_MODO está en '{config.CORREO_MODO}', no en 'archivo'.")
        print("Con el envío real activo, el código llega al buzón del usuario.")
        return 1
    if not SALIENTE.exists():
        print(f"Todavía no se ha generado ningún correo.\nCarpeta: {SALIENTE}")
        return 1

    filtro = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    archivos = sorted(SALIENTE.glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)
    if filtro:
        archivos = [f for f in archivos if filtro in f.name.lower()]
    if not archivos:
        print(f"No hay correos para «{filtro}»." if filtro else "No hay correos generados.")
        return 1

    for archivo in archivos[:6]:
        texto = archivo.read_text(encoding="utf-8")
        cabecera = CABECERA.search(texto)
        destino = cabecera.group(1) if cabecera else "?"
        asunto = cabecera.group(2) if cabecera else "?"
        encontrado = CODIGO.search(texto)
        marca = f"{archivo.stat().st_mtime:.0f}"
        from datetime import datetime
        cuando = datetime.fromtimestamp(float(marca)).strftime("%H:%M:%S")
        if encontrado:
            codigo = "".join(encontrado.group(1).split())
            print(f"\n  {codigo}        <- {destino}  ({cuando})")
            print(f"  {'':{len(codigo)}}           {asunto}")
        else:
            print(f"\n  (sin código)  <- {destino}  ({cuando})")
            print(f"                 {asunto}")
    print(f"\nCarpeta: {SALIENTE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
