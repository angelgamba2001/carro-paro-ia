"""
API REST (FastAPI) — mecanismo de comunicación entre componentes.

Consumidores: la app móvil, el agente IA (cuando se integre un LLM externo) y
cualquier sistema del hospital. Reutiliza la misma capa de servicios que la web.

    uvicorn api.main:app --reload --port 8000
    Documentación interactiva: http://localhost:8000/docs
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jwt  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from src.agente.agente import AgenteCarroParo  # noqa: E402
from src.agente.herramientas import esquemas_llm  # noqa: E402
from src.analitica.kpis import kpis_analiticos, kpis_operativos  # noqa: E402
from src.analitica.prediccion import leer_metricas  # noqa: E402
from src.bigdata.procesamiento import leer_gold, ultima_ejecucion  # noqa: E402
from src.database.connection import base_disponible  # noqa: E402
from src.seguridad.autenticacion import autenticar, revalidar_usuario  # noqa: E402
from src.seguridad.permisos import PermisoDenegado, exigir_permiso  # noqa: E402
from src.seguridad.tokens import decodificar_token, emitir_token  # noqa: E402
from src.servicios import alertas as srv_alertas  # noqa: E402
from src.servicios import inventario as srv_inv  # noqa: E402
from src.servicios.errores import ErrorNegocio  # noqa: E402

app = FastAPI(title="SMARTDATA 360 · Carro de Paro API", version="2.0",
              description="API del módulo Carro de Paro: inventario, alertas, analítica y agente IA.")
esquema_bearer = HTTPBearer(auto_error=False)
agente = AgenteCarroParo()


# ------------------------- seguridad transversal -------------------------
@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    if "server" in resp.headers:
        del resp.headers["server"]
    return resp


@app.exception_handler(PermisoDenegado)
async def _403(_, exc):
    return JSONResponse(status_code=403, content={"error": "forbidden", "message": str(exc)})


@app.exception_handler(ErrorNegocio)
async def _422(_, exc):
    return JSONResponse(status_code=422, content={"error": "validation", "message": str(exc)})


@app.exception_handler(Exception)
async def _500(_, exc):
    import logging
    logging.getLogger("api").exception("Error no controlado")
    return JSONResponse(status_code=500, content={"error": "internal", "message": "Error interno."})


def usuario_actual(cred: HTTPAuthorizationCredentials = Depends(esquema_bearer)) -> dict:
    if not cred:
        raise HTTPException(401, "Token requerido", headers={"WWW-Authenticate": "Bearer"})
    try:
        datos = decodificar_token(cred.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido o expirado", headers={"WWW-Authenticate": "Bearer"})
    u = revalidar_usuario(int(datos["sub"]))       # rol y estado vigentes en la BD
    if not u:
        raise HTTPException(401, "Usuario inactivo")
    return u


# ------------------------- modelos -------------------------
class Login(BaseModel):
    correo: str = Field(max_length=150)
    password: str = Field(max_length=128)


class NuevoLote(BaseModel):
    carro_id: int
    medicamento_id: int
    lote: str = Field(max_length=60)
    cantidad: int = Field(ge=1, le=500)
    fecha_vencimiento: date


class Consumo(BaseModel):
    cantidad: int = Field(ge=1, le=500)
    motivo: str = Field(default="", max_length=255)
    codigo_azul: bool = False


class Pregunta(BaseModel):
    pregunta: str = Field(min_length=1, max_length=1000)


class Atencion(BaseModel):
    nota: str = Field(default="", max_length=255)


def _df(df):
    return df.to_dict(orient="records") if hasattr(df, "to_dict") else df


# ------------------------- endpoints -------------------------
@app.get("/api/salud", tags=["sistema"])
def salud():
    return {"api": "ok", "base_de_datos": "ok" if base_disponible() else "sin conexión",
            "ultima_ejecucion_pipeline": (ultima_ejecucion() or {}).get("fecha")}


@app.post("/api/auth/login", tags=["autenticación"])
def login(datos: Login):
    r = autenticar(datos.correo, datos.password, origen="API")
    if not r.ok:
        raise HTTPException(401, r.mensaje)
    return {"access_token": emitir_token(r.usuario), "token_type": "bearer",
            "usuario": {k: r.usuario[k] for k in ("id", "nombre", "rol")},
            "debe_cambiar_password": bool(r.usuario["debe_cambiar_password"])}


@app.get("/api/auth/yo", tags=["autenticación"])
def yo(u=Depends(usuario_actual)):
    from src.seguridad.permisos import permisos_de
    return {**u, "permisos": sorted(permisos_de(u["rol"]))}


@app.get("/api/carros", tags=["inventario"])
def carros(u=Depends(usuario_actual)):
    exigir_permiso(u, "inventario.ver", "API")
    return srv_inv.listar_carros()


@app.get("/api/inventario", tags=["inventario"])
def inventario(carro_id: int | None = None, estado: str | None = None, u=Depends(usuario_actual)):
    return _df(srv_inv.listar_inventario(u, carro_id=carro_id, estados=[estado] if estado else None))


@app.get("/api/inventario/stock", tags=["inventario"])
def stock(u=Depends(usuario_actual)):
    return _df(srv_inv.stock_por_carro(u))


@app.post("/api/inventario", status_code=201, tags=["inventario"])
def crear_lote(d: NuevoLote, u=Depends(usuario_actual)):
    nuevo = srv_inv.registrar_lote(u, d.carro_id, d.medicamento_id, d.lote, d.cantidad, d.fecha_vencimiento,
                                   origen_llamada="API")
    return {"id": nuevo}


@app.post("/api/inventario/{inv_id}/consumo", tags=["inventario"])
def consumo(inv_id: int, d: Consumo, u=Depends(usuario_actual)):
    srv_inv.registrar_consumo(u, inv_id, d.cantidad, d.motivo, d.codigo_azul, origen_llamada="API")
    return {"ok": True}


@app.get("/api/alertas", tags=["alertas"])
def alertas(pendientes: bool = True, u=Depends(usuario_actual)):
    return _df(srv_alertas.listar_alertas(u, solo_pendientes=pendientes))


@app.post("/api/alertas/{alerta_id}/atender", tags=["alertas"])
def atender(alerta_id: int, d: Atencion, u=Depends(usuario_actual)):
    srv_alertas.atender_alerta(u, alerta_id, d.nota, origen_llamada="API")
    return {"ok": True}


@app.get("/api/analitica/kpis", tags=["analítica"])
def kpis(u=Depends(usuario_actual)):
    exigir_permiso(u, "dashboard.operativo", "API")
    datos = {"operativos": kpis_operativos()}
    from src.seguridad.permisos import tiene_permiso
    if tiene_permiso(u, "dashboard.analitico"):
        datos["analiticos"] = kpis_analiticos()
    return datos


@app.get("/api/analitica/predicciones", tags=["analítica"])
def predicciones(solo_riesgo: bool = True, u=Depends(usuario_actual)):
    exigir_permiso(u, "dashboard.analitico", "API")
    df = leer_gold("predicciones")
    if solo_riesgo and not df.empty:
        df = df[df["riesgo_desabastecimiento"] == 1]
    return {"metricas_modelo": leer_metricas(), "predicciones": _df(df)}


@app.get("/api/analitica/anomalias", tags=["analítica"])
def anomalias(u=Depends(usuario_actual)):
    exigir_permiso(u, "dashboard.analitico", "API")
    return _df(leer_gold("anomalias").astype(str))


@app.get("/api/agente/herramientas", tags=["agente IA"])
def herramientas_agente(u=Depends(usuario_actual)):
    exigir_permiso(u, "agente.usar", "API")
    return esquemas_llm(u, formato="anthropic")


@app.post("/api/agente/consulta", tags=["agente IA"])
def consulta_agente(d: Pregunta, u=Depends(usuario_actual)):
    r = agente.responder(u, d.pregunta)
    return {"respuesta": r["respuesta"], "herramientas_usadas": r["herramientas_usadas"], "proveedor": r["proveedor"]}


@app.post("/api/agente/revision", tags=["agente IA"])
def revision_agente(u=Depends(usuario_actual)):
    return agente.revision_autonoma(u)
