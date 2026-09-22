from datetime import date

import streamlit as st

from app.componentes import cabecera
from app.vistas.inventario import _form_registro
from src.database.auditoria import registrar_log
from src.ocr.extractor_fechas import extraer_fecha_texto, extraer_lote
from src.ocr.lector_imagen import leer_texto, ocr_disponible
from src.servicios import catalogo as srv_cat
from src.servicios import inventario as srv_inv


def mostrar(usuario: dict):
    cabecera("Lectura OCR", "Fecha de vencimiento y lote desde la etiqueta")
    texto, confianza = "", None
    modo = st.radio("Fuente", ["Foto de la etiqueta", "Texto manual (prueba)"], horizontal=True)
    if modo == "Foto de la etiqueta":
        if not ocr_disponible():
            st.warning("EasyOCR no está instalado en este equipo (pip install easyocr). Use el modo de texto.")
        foto = st.file_uploader("Imagen JPG o PNG (máx. 10 MB)", type=["jpg", "jpeg", "png"])
        if foto and ocr_disponible():
            st.image(foto, width=320)
            with st.spinner("Leyendo etiqueta..."):
                texto, confianza = leer_texto(foto.getvalue())
            registrar_log(usuario["id"], "LECTURA_OCR", "inventario_carro", None, f"confianza={confianza}")
    else:
        texto = st.text_area("Texto de la etiqueta", "LOT: B8942 EXP: 11/2027 ADRENALINA 1MG/ML")

    if not texto:
        return
    fecha, lote = extraer_fecha_texto(texto), extraer_lote(texto)
    c1, c2, c3 = st.columns(3)
    c1.metric("Fecha detectada", fecha or "no encontrada")
    c2.metric("Lote detectado", lote or "no encontrado")
    if confianza is not None:
        c3.metric("Confianza OCR", f"{confianza:.0%}")
        if confianza < 0.6:
            st.warning("Confianza baja: verifique los datos contra la etiqueta antes de guardar.")
    st.caption(f"Texto leído: {texto}")
    st.markdown("#### Confirmar y registrar")
    _form_registro(usuario, srv_inv.listar_carros(), srv_cat.listar_medicamentos(), prefijo="ocr",
                   lote_ini=lote or "", fecha_ini=date.fromisoformat(fecha) if fecha and
                   date.fromisoformat(fecha) > date.today() else None,
                   origen="OCR", confianza=confianza)
