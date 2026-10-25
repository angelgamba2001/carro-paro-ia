"""
RBAC por permisos — fuente única de verdad de roles y permisos.

Unifica los roles de SGHCU (MEDICO, ENFERMERO, ADMIN, TI + los tres nuevos del
Cap. 2.1: DIRECCION_MEDICA, ANALISTA_DATOS, OFICIAL_SEGURIDAD) con los de
Carro de Paro (ENFERMERO, ADMINISTRADOR->ADMIN, AUDITOR) y agrega REGENTE_FARMACIA.

La interfaz web, la API y el agente IA validan con la MISMA función
(`exigir_permiso`), así ninguno de los tres caminos puede saltarse una regla.
"""
import logging

ROLES = {
    "ADMIN": ("Administrador", "Gestión total: usuarios, roles, catálogo y configuración"),
    "MEDICO": ("Médico", "Consulta el carro y registra el uso de medicamentos en código azul"),
    "ENFERMERO": ("Enfermero(a)", "Revisión diaria, registro, reposición y OCR del carro"),
    "REGENTE_FARMACIA": ("Regente de farmacia", "Catálogo, lotes, bajas por vencimiento y reposición"),
    "AUDITOR": ("Auditor", "Solo lectura de inventario, alertas y trazabilidad"),
    "DIRECCION_MEDICA": ("Dirección médica", "Tablero ejecutivo y recomendaciones del agente"),
    "ANALISTA_DATOS": ("Analista de datos", "Pipeline Big Data, analítica y modelos"),
    "OFICIAL_SEGURIDAD": ("Oficial de seguridad", "Eventos de seguridad, bloqueos y cumplimiento"),
    "TI": ("Soporte TI", "Soporte técnico, desbloqueo de cuentas y ejecución de procesos"),
    "VISITANTE": ("Visitante", "Solo consulta, y únicamente los módulos que le asigne un administrador"),
}

PERMISOS = {
    "inventario.ver": "Consultar inventario de los carros",
    "inventario.registrar": "Registrar lotes en un carro",
    "inventario.editar": "Corregir datos de un lote (la fecha de vencimiento es inmutable)",
    "inventario.consumo": "Registrar consumo de unidades",
    "inventario.baja": "Dar de baja lotes vencidos o dañados",
    "ocr.usar": "Leer etiquetas con OCR",
    "alertas.ver": "Consultar alertas",
    "alertas.gestionar": "Atender alertas",
    "catalogo.gestionar": "Crear y editar medicamentos del catálogo",
    "dashboard.operativo": "Tablero operativo",
    "dashboard.analitico": "Tablero analítico (tendencias, predicción, anomalías)",
    "auditoria.ver": "Consultar log de auditoría",
    "seguridad.ver": "Consultar eventos de seguridad",
    "usuarios.gestionar": "Crear usuarios, cambiar rol y estado",
    "usuarios.desbloquear": "Desbloquear cuentas bloqueadas",
    "bigdata.ejecutar": "Ejecutar el pipeline Big Data y la analítica",
    "agente.usar": "Consultar al agente IA",
    "agente.acciones": "Permitir que el agente ejecute acciones (crear alertas/recomendaciones)",
}

_OPERATIVO = {"inventario.ver", "alertas.ver", "dashboard.operativo"}

MATRIZ = {
    "ADMIN": set(PERMISOS),
    "MEDICO": _OPERATIVO | {"inventario.consumo", "agente.usar"},
    "ENFERMERO": _OPERATIVO | {"inventario.registrar", "inventario.editar", "inventario.consumo",
                               "ocr.usar", "alertas.gestionar", "agente.usar"},
    "REGENTE_FARMACIA": _OPERATIVO | {"inventario.registrar", "inventario.editar", "inventario.consumo",
                                      "inventario.baja", "ocr.usar", "alertas.gestionar",
                                      "catalogo.gestionar", "dashboard.analitico", "agente.usar",
                                      "agente.acciones"},
    "AUDITOR": _OPERATIVO | {"dashboard.analitico", "auditoria.ver"},
    "DIRECCION_MEDICA": _OPERATIVO | {"dashboard.analitico", "agente.usar", "agente.acciones"},
    "ANALISTA_DATOS": _OPERATIVO | {"dashboard.analitico", "bigdata.ejecutar", "agente.usar"},
    "OFICIAL_SEGURIDAD": {"auditoria.ver", "seguridad.ver"},
    "TI": {"seguridad.ver", "usuarios.desbloquear", "bigdata.ejecutar"},
    # El visitante no tiene permisos propios: los recibe de los módulos que un
    # administrador le abre (MODULOS_VISITANTE). Sin módulos asignados no ve nada.
    "VISITANTE": set(),
}

# Módulos que un administrador puede abrir a una cuenta VISITANTE.
#   clave -> (etiqueta, descripción, permisos que concede, vistas del menú que habilita)
# Todos son de SOLO LECTURA: ninguno incluye registrar, editar, dar de baja ni gestionar.
# El tablero necesita leer inventario y alertas para dibujarse, por eso esos permisos
# viajan con él; lo que el visitante VE en el menú se limita a las vistas de su módulo.
MODULOS_VISITANTE = {
    "tablero": ("Tablero operativo", "Estado de los carros en tiempo real",
                _OPERATIVO, {"tablero"}),
    "analitico": ("Tablero analítico", "Tendencias, predicción y anomalías",
                  _OPERATIVO | {"dashboard.analitico"}, {"tablero"}),
    "inventario": ("Inventario", "Consulta de lotes y existencias",
                   {"inventario.ver"}, {"inventario"}),
    "alertas": ("Alertas", "Consulta de alertas, sin atenderlas",
                {"alertas.ver"}, {"alertas"}),
    "agente": ("Asistente IA", "Preguntas al asistente, solo con los datos de sus otros módulos",
               {"agente.usar"}, {"agente"}),
}


class PermisoDenegado(Exception):
    """El rol del usuario no tiene el permiso requerido (equivale a HTTP 403)."""


def permisos_de(rol: str) -> set:
    return MATRIZ.get(rol, set())


def modulos_de(usuario: dict | None) -> set:
    """Módulos asignados a una cuenta VISITANTE (la columna `modulos`, separada por comas).
    Ignora claves desconocidas: un valor alterado en la BD nunca concede un permiso nuevo."""
    crudo = (usuario or {}).get("modulos")
    if not isinstance(crudo, str):          # NULL de la BD o NaN de pandas
        crudo = ""
    return {m.strip() for m in crudo.split(",") if m.strip() in MODULOS_VISITANTE}


def permisos_de_usuario(usuario: dict | None) -> set:
    """Permisos efectivos de una persona: los de su rol o, si es VISITANTE, los de sus módulos."""
    if not usuario:
        return set()
    rol = usuario.get("rol", "")
    if rol == "VISITANTE":
        permisos: set = set()
        for m in modulos_de(usuario):
            permisos |= MODULOS_VISITANTE[m][2]
        return permisos
    return permisos_de(rol)


def vista_permitida(usuario: dict | None, vista: str) -> bool:
    """¿Puede abrir esta vista del menú? Solo restringe a los VISITANTE: para el resto
    manda el permiso de siempre. Es una capa de interfaz; los permisos siguen siendo la barrera."""
    if not usuario or usuario.get("rol") != "VISITANTE":
        return True
    return any(vista in MODULOS_VISITANTE[m][3] for m in modulos_de(usuario)) or vista == "perfil"


def tiene_permiso(usuario: dict | None, permiso: str) -> bool:
    if not usuario or not usuario.get("activo", 1):
        return False
    return permiso in permisos_de_usuario(usuario)


def exigir_permiso(usuario: dict | None, permiso: str, origen: str = "WEB"):
    """Lanza PermisoDenegado y deja evidencia en eventos_seguridad."""
    if tiene_permiso(usuario, permiso):
        return
    try:
        from src.database.auditoria import registrar_evento_seguridad
        registrar_evento_seguridad(
            "ACCESO_DENEGADO",
            correo=(usuario or {}).get("correo"),
            usuario_id=(usuario or {}).get("id"),
            detalle=f"Permiso requerido: {permiso}",
            origen=origen,
        )
    except Exception:
        # Bandit B110 / OWASP A09:2021: silenciar esto dejaba la auditoria ciega ante
        # una denegacion de acceso, que es justo el evento que hay que poder rastrear.
        logging.getLogger(__name__).error(
            "No se pudo registrar ACCESO_DENEGADO para el permiso %s", permiso, exc_info=True)
    rol = (usuario or {}).get("rol", "ANÓNIMO")
    raise PermisoDenegado(f"El rol {rol} no tiene el permiso '{permiso}'.")
