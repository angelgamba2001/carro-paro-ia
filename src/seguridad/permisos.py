"""
RBAC por permisos — fuente única de verdad de roles y permisos.

Unifica los roles de SGHCU (MEDICO, ENFERMERO, ADMIN, TI + los tres nuevos del
Cap. 2.1: DIRECCION_MEDICA, ANALISTA_DATOS, OFICIAL_SEGURIDAD) con los de
Carro de Paro (ENFERMERO, ADMINISTRADOR->ADMIN, AUDITOR) y agrega REGENTE_FARMACIA.

La interfaz web, la API y el agente IA validan con la MISMA función
(`exigir_permiso`), así ninguno de los tres caminos puede saltarse una regla.
"""

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
}


class PermisoDenegado(Exception):
    """El rol del usuario no tiene el permiso requerido (equivale a HTTP 403)."""


def permisos_de(rol: str) -> set:
    return MATRIZ.get(rol, set())


def tiene_permiso(usuario: dict | None, permiso: str) -> bool:
    if not usuario or not usuario.get("activo", 1):
        return False
    return permiso in permisos_de(usuario.get("rol", ""))


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
        pass
    rol = (usuario or {}).get("rol", "ANÓNIMO")
    raise PermisoDenegado(f"El rol {rol} no tiene el permiso '{permiso}'.")
