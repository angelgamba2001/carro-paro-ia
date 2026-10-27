import re
import unicodedata
from collections import Counter
from datetime import date

import streamlit as st

from app import datos
from app.componentes import accion, cabecera
from app.vistas.inventario import _form_registro
from src.database.auditoria import registrar_log
from src.ocr.extractor_fechas import extraer_fecha_texto, extraer_lote
from src.ocr.lector_imagen import leer_texto, ocr_disponible
from src.seguridad.archivos import ArchivoInvalido, validar_imagen
from src.seguridad.permisos import tiene_permiso
from src.servicios import catalogo as srv_cat

# Palabras que aparecen en casi cualquier etiqueta y no identifican al medicamento
RUIDO = {
    "tabletas", "tableta", "capsulas", "capsula", "ampolla", "ampollas", "solucion",
    "inyectable", "institucional", "colombia", "oral", "frasco", "jarabe", "unidades",
    "registro", "sanitario", "invima", "laboratorio", "fabricado", "contenido",
    "vencimiento", "fabricacion", "advertencia", "medicamento", "venta", "formula",
}


def _normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y sin signos: así 'Adrenalina' casa con 'ADRENALlNA.'"""
    plano = unicodedata.normalize("NFKD", texto.lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", plano)


def _medicamento_en_texto(texto: str, meds: list[dict]) -> dict | None:
    """Primer medicamento del catálogo cuyo nombre o principio activo aparece en la etiqueta.

    Se compara contra la primera palabra de cada campo y se exige al menos cinco
    caracteres, para no casar por fragmentos como 'sodio' o '10 mg'. Gana la
    coincidencia más larga, que es la más específica.
    """
    plano = _normalizar(texto)
    mejor, largo = None, 0
    for m in meds:
        for campo in (m.get("principio_activo"), m.get("nombre")):
            if not campo:
                continue
            partes = _normalizar(str(campo)).split()
            if not partes:
                continue
            clave = partes[0]
            if len(clave) >= 5 and clave in plano and len(clave) > largo:
                mejor, largo = m, len(clave)
    return mejor


def _nombre_sugerido(texto: str) -> str:
    """Candidato a nombre del medicamento a partir de una etiqueta mal leída.

    Se puntúa cada palabra por repeticiones por longitud. La repetición descarta el
    ruido del OCR, que casi nunca produce dos veces el mismo error; la longitud evita
    quedarse con el nombre del laboratorio, que suele ser corto y aparecer tantas
    veces como el principio activo. Es una sugerencia editable, no una detección:
    sobre la etiqueta de prueba 'Genfar' aparece 5 veces y 'Amlodipino' 4, y sin
    ponderar por longitud ganaría el laboratorio.
    """
    palabras = [p.lower() for p in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{6,}", texto)]
    candidatos = [p for p in palabras if _normalizar(p).strip() not in RUIDO]
    if not candidatos:
        return ""
    cuenta = Counter(candidatos)
    return max(cuenta, key=lambda p: (cuenta[p] * len(p), cuenta[p])).capitalize()


def _alta_catalogo(usuario: dict, nombre_sugerido: str):
    """Alta de una referencia nueva sin salir de la pantalla de lectura."""
    with st.expander("Agregar este medicamento al catálogo", expanded=True):
        st.caption("El catálogo define el stock mínimo y máximo por carro, así que una "
                   "referencia nueva necesita esos valores antes de poder registrarse.")
        with st.form("alta_catalogo_ocr"):
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Nombre", value=nombre_sugerido, max_chars=150)
            principio = c2.text_input("Principio activo", value=nombre_sugerido, max_chars=150)
            c3, c4, c5 = st.columns(3)
            criticidad = c3.selectbox("Criticidad", ["ALTA", "MEDIA", "BAJA"], index=1)
            minimo = c4.number_input("Stock mínimo", 0, 500, 2)
            maximo = c5.number_input("Stock máximo", 0, 500, 10)
            c6, c7 = st.columns(2)
            costo = c6.number_input("Costo unitario", 0.0, 10_000_000.0, 0.0, step=100.0)
            cum = c7.text_input("Código CUM (opcional)", max_chars=30)
            if st.form_submit_button("Crear en el catálogo", type="primary"):
                r = accion(srv_cat.crear_medicamento, usuario, nombre, principio, criticidad,
                           int(minimo), int(maximo), float(costo), codigo_cum=cum,
                           exito=f"'{nombre}' agregado al catálogo. Ya puede registrar el lote.")
                if r:
                    st.rerun()


def mostrar(usuario: dict):
    cabecera("Lectura OCR", "Fecha de vencimiento y lote desde la etiqueta")
    texto, confianza = "", None
    modo = st.radio("Fuente", ["Foto de la etiqueta", "Texto manual (prueba)"], horizontal=True)
    if modo == "Foto de la etiqueta":
        if not ocr_disponible():
            st.warning("EasyOCR no está instalado en este equipo (pip install easyocr). Use el modo de texto.")
        foto = st.file_uploader("Imagen JPG o PNG (máx. 10 MB)", type=["jpg", "jpeg", "png"])
        if foto:
            # La extensión la elige quien sube el archivo: se revisa el contenido antes de usarlo
            try:
                validar_imagen(foto.getvalue(), foto.name, usuario)
            except ArchivoInvalido as e:
                st.error(str(e))
                return
        if foto and ocr_disponible():
            st.image(foto, width=320)
            with st.spinner("Leyendo etiqueta..."):
                texto, confianza = leer_texto(foto.getvalue())
            registrar_log(usuario["id"], "LECTURA_OCR", "inventario_carro", None, f"confianza={confianza}")
    else:
        texto = st.text_area("Texto de la etiqueta", "LOT: B8942 EXP: 11/2027 ADRENALINA 1MG/ML")

    if not texto:
        return

    meds = datos.medicamentos()
    fecha, lote = extraer_fecha_texto(texto), extraer_lote(texto)
    detectado = _medicamento_en_texto(texto, meds)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fecha detectada", fecha or "no encontrada")
    c2.metric("Lote detectado", lote or "no encontrado")
    c3.metric("Medicamento", detectado["nombre"] if detectado else "no reconocido")
    if confianza is not None:
        c4.metric("Confianza OCR", f"{confianza:.0%}")
        if confianza < 0.6:
            st.warning("Confianza baja: verifique los datos contra la etiqueta antes de guardar.")
    st.caption(f"Texto leído: {texto}")

    if not detectado:
        sugerido = _nombre_sugerido(texto)
        pista = f" Lo que más se repite en la etiqueta es «{sugerido}»." if sugerido else ""
        if tiene_permiso(usuario, "catalogo.gestionar"):
            st.info("Ningún medicamento del catálogo coincide con esta etiqueta." + pista +
                    " Puede darlo de alta aquí mismo y luego registrar el lote.")
            _alta_catalogo(usuario, sugerido)
        else:
            st.info("Ningún medicamento del catálogo coincide con esta etiqueta." + pista +
                    " Su rol no puede crear referencias nuevas: solicítelo al regente de farmacia "
                    "o a un administrador. Mientras tanto puede registrar el lote eligiendo "
                    "manualmente un medicamento del catálogo.")

    st.markdown("#### Confirmar y registrar")
    _form_registro(usuario, datos.carros(), meds, prefijo="ocr",
                   lote_ini=lote or "", fecha_ini=date.fromisoformat(fecha) if fecha and
                   date.fromisoformat(fecha) > date.today() else None,
                   origen="OCR", confianza=confianza,
                   med_ini=detectado["id"] if detectado else None)
