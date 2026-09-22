"""
Agente IA del carro de paro.

Ciclo: pregunta -> el proveedor decide qué herramientas usar -> se ejecutan con los
permisos del usuario -> el proveedor redacta la respuesta. Todo queda auditado en
consultas_agente y log_auditoria.

Además del modo consulta, `revision_autonoma` hace que el agente actúe por iniciativa
propia: revisa el estado de todos los carros, prioriza hallazgos y (si el rol lo permite)
registra recomendaciones como alertas. Esto es lo que lo diferencia de un chatbot.
"""
import logging

from src.agente.herramientas import ejecutar_herramienta, herramientas_permitidas
from src.agente.proveedores import ProveedorReglas, obtener_proveedor
from src.database.auditoria import registrar_log
from src.database.connection import ejecutar
from src.seguridad.permisos import PermisoDenegado, exigir_permiso, tiene_permiso
from src.servicios.errores import ErrorNegocio

log = logging.getLogger(__name__)
MAX_PASOS = 4
MAX_LONGITUD_PREGUNTA = 1000


class AgenteCarroParo:
    def __init__(self, proveedor=None):
        self.proveedor = proveedor or obtener_proveedor()

    def responder(self, usuario: dict, pregunta: str, permitir_acciones: bool = False) -> dict:
        """permitir_acciones=False: el agente solo consulta. Las herramientas que modifican datos
        (crear recomendaciones/alertas) solo se le ofrecen si el usuario lo autoriza explícitamente."""
        exigir_permiso(usuario, "agente.usar", origen="AGENTE")
        pregunta = (pregunta or "").strip()
        if not pregunta:
            raise ErrorNegocio("Escriba una pregunta.")
        if len(pregunta) > MAX_LONGITUD_PREGUNTA:
            raise ErrorNegocio(f"La pregunta supera {MAX_LONGITUD_PREGUNTA} caracteres.")

        herramientas = [h for h in herramientas_permitidas(usuario) if permitir_acciones or not h.es_accion]
        proveedor = self.proveedor
        resultados: list[dict] = []
        respuesta = None
        for _ in range(MAX_PASOS):
            try:
                paso = proveedor.siguiente_paso(pregunta, resultados, herramientas)
            except Exception as e:  # LLM apagado, sin red, respuesta inválida o no implementado
                log.warning("Proveedor %s falló (%s); se usa el motor de reglas.", proveedor.nombre, e)
                proveedor = ProveedorReglas()
                paso = proveedor.siguiente_paso(pregunta, resultados, herramientas)
            if paso.respuesta is not None:
                respuesta = paso.respuesta
                break
            for nombre, args in paso.llamadas:
                try:
                    res = ejecutar_herramienta(usuario, nombre, args)
                except PermisoDenegado as e:
                    res = {"error": str(e)}
                resultados.append({"herramienta": nombre, "argumentos": args, "resultado": res})
        if respuesta is None:
            respuesta = "No logré completar el análisis en el número de pasos permitido."

        usadas = ", ".join(dict.fromkeys(r["herramienta"] for r in resultados))
        try:
            ejecutar("INSERT INTO consultas_agente (usuario_id, pregunta, respuesta, herramientas_usadas, proveedor) "
                     "VALUES (%s,%s,%s,%s,%s)", (usuario["id"], pregunta, respuesta, usadas[:500], proveedor.nombre))
        except Exception as e:
            log.error("No se guardó la consulta del agente: %s", e)
        registrar_log(usuario["id"], "CONSULTA_AGENTE", "agente", None, f"Herramientas: {usadas}", "AGENTE")
        return {"respuesta": respuesta, "herramientas_usadas": usadas.split(", ") if usadas else [],
                "proveedor": proveedor.nombre, "datos": resultados}

    def revision_autonoma(self, usuario: dict) -> dict:
        """Revisión proactiva de todos los carros. Detecta situaciones, prioriza y actúa."""
        exigir_permiso(usuario, "agente.usar", origen="AGENTE")
        hallazgos = []

        def usar(nombre, **args):
            if any(h.nombre == nombre for h in herramientas_permitidas(usuario)):
                return ejecutar_herramienta(usuario, nombre, args)
            return None

        stock = usar("consultar_stock_bajo") or []
        criticos = [x for x in stock if x["criticidad"] == "ALTA"]
        if criticos:
            carros = sorted({x["carro"] for x in criticos})
            hallazgos.append(("ALTA", f"{len(criticos)} medicamentos de criticidad ALTA bajo el mínimo en "
                                      f"{len(carros)} carros ({', '.join(carros[:5])}{'...' if len(carros) > 5 else ''}). "
                                      "Reponer antes del próximo turno."))
        venc = usar("consultar_vencimientos", dias=0) or []
        if venc:
            hallazgos.append(("ALTA", f"{len(venc)} lotes vencidos siguen en los carros: retirar y dar de baja."))
        pred = usar("predecir_desabastecimiento", limite=50)
        if pred and pred.get("total_en_riesgo"):
            hallazgos.append(("MEDIA", f"El modelo prevé {pred['total_en_riesgo']} faltantes en "
                                       f"{pred['horizonte_dias']} días; programar reposición preventiva."))
        anom = usar("consultar_anomalias") or []
        if anom:
            hallazgos.append(("MEDIA", f"{len(anom)} consumos anómalos recientes: verificar registros con "
                                       "el servicio correspondiente."))
        hist = usar("indicadores_historicos") or {}
        if hist and hist.get("cumplimiento_revision_pct", 100) < 95:
            hallazgos.append(("BAJA", f"Cumplimiento de revisión diaria en {hist['cumplimiento_revision_pct']}% "
                                      "(meta 95%): reforzar la lista de chequeo por turno."))

        creadas = []
        if tiene_permiso(usuario, "agente.acciones"):
            for sev, texto in hallazgos:
                r = ejecutar_herramienta(usuario, "crear_recomendacion", {"mensaje": texto, "severidad": sev})
                if r.get("creada"):
                    creadas.append(r["alerta_id"])
        registrar_log(usuario["id"], "REVISION_AUTONOMA", "agente", None,
                      f"{len(hallazgos)} hallazgos, {len(creadas)} recomendaciones registradas", "AGENTE")
        return {"hallazgos": [{"prioridad": s, "detalle": t} for s, t in hallazgos],
                "recomendaciones_creadas": creadas,
                "puede_actuar": tiene_permiso(usuario, "agente.acciones")}
