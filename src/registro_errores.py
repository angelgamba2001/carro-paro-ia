"""
Registro de errores de la aplicación y de la API.

Cada error (nivel ERROR o superior) queda en dos sitios:
  * un archivo rotativo, data/logs/errores.log  (siempre; sirve aunque la base de datos esté caída);
  * la tabla errores_sistema, que se consulta desde «Auditoría y seguridad».

Nunca debe tumbar la operación ni entrar en bucle: si escribir en la base de datos falla,
solo queda el archivo. No se guardan contraseñas: los mensajes se recortan y los datos
de las peticiones no se incluyen.
"""
import logging
import threading
import traceback
from logging.handlers import RotatingFileHandler

from src import config

_listo = False
_dentro = threading.local()
FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class _TablaErrores(logging.Handler):
    """Guarda en errores_sistema los registros ERROR o superiores."""

    def emit(self, record: logging.LogRecord):
        if getattr(_dentro, "activo", False):             # un fallo al guardar no genera otro registro
            return
        _dentro.activo = True
        try:
            from src.database.connection import ejecutar
            traza = "".join(traceback.format_exception(*record.exc_info))[-3000:] if record.exc_info else None
            ejecutar("INSERT INTO errores_sistema (nivel, modulo, mensaje, traza) VALUES (%s,%s,%s,%s)",
                     (record.levelname, record.name[:80], record.getMessage()[:500], traza))
        except Exception:                                 # noqa: BLE001  (la tabla puede no existir aún)
            pass
        finally:
            _dentro.activo = False


def configurar():
    """Idempotente: se puede llamar desde cada punto de entrada."""
    global _listo
    if _listo:
        return
    _listo = True
    raiz = logging.getLogger()
    if raiz.level in (logging.NOTSET, logging.WARNING) or raiz.level > logging.WARNING:
        raiz.setLevel(logging.WARNING)
    try:
        carpeta = config.DATA_DIR / "logs"
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = RotatingFileHandler(carpeta / "errores.log", maxBytes=2_000_000, backupCount=5,
                                      encoding="utf-8")
        archivo.setLevel(logging.WARNING)
        archivo.setFormatter(logging.Formatter(FORMATO))
        raiz.addHandler(archivo)
    except OSError:                                       # carpeta de solo lectura: queda la consola
        logging.getLogger(__name__).warning("No se pudo abrir el archivo de errores", exc_info=True)
    tabla = _TablaErrores(level=logging.ERROR)
    raiz.addHandler(tabla)


def errores_recientes(dias: int = 7, limite: int = 500):
    from src.database.connection import consultar_df
    return consultar_df("SELECT fecha, nivel, modulo, mensaje, traza FROM errores_sistema "
                        "WHERE fecha >= DATE_SUB(NOW(), INTERVAL %s DAY) ORDER BY fecha DESC LIMIT %s",
                        (dias, limite))
