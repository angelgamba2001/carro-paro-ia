import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os

# Permitir importar módulos desde src/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.connection import obtener_conexion

st.set_page_config(page_title="Carro de Paro IA", layout="wide")

st.title("🚑 Control e Inventario de Medicamentos - Carro de Paro")

# --- BLOQUE 1: MÉTRICAS Y DASHBOARD EN TIEMPO REAL ---
conn = obtener_conexion()
if conn:
    query_kpi = """
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN estado = 'vigente' THEN 1 ELSE 0 END) as vigentes,
            SUM(CASE WHEN estado = 'proximo_a_vencer' THEN 1 ELSE 0 END) as proximos,
            SUM(CASE WHEN estado = 'vencido' THEN 1 ELSE 0 END) as vencidos
        FROM inventario_carro;
    """
    df_kpi = pd.read_sql(query_kpi, conn)
    conn.close()
    
    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    col_kpi1.metric("Total Medicamentos", df_kpi['total'][0] if not df_kpi.empty else 0)
    col_kpi2.metric("🟢 Vigentes", df_kpi['vigentes'][0] if not df_kpi.empty else 0)
    col_kpi3.metric("🟡 Próximos a Vencer", df_kpi['proximos'][0] if not df_kpi.empty else 0)
    col_kpi4.metric("🔴 Vencidos", df_kpi['vencidos'][0] if not df_kpi.empty else 0)

st.write("---")

# --- BLOQUE 2: FORMULARIO DE REGISTRO MANIFESTADO ---
st.subheader("Fase 1: Registro Asistido e Ingreso por Lotes")

with st.form("form_registro"):
    st.write("### Registrar Nuevo Medicamento / Lote")
    
    conn = obtener_conexion()
    opciones_cat = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, nombre, criticidad FROM cat_medicamentos;")
        opciones_cat = cursor.fetchall()
        cursor.close()
        conn.close()
    
    nombres_medicamentos = [f"{m['id']} - {m['nombre']} (Criticidad: {m['criticidad']})" for m in opciones_cat]
    
    col1, col2 = st.columns(2)
    
    with col1:
        medicamento_seleccionado = st.selectbox(
            "Seleccione el Medicamento del Catálogo:",
            options=nombres_medicamentos if nombres_medicamentos else ["No hay catálogo disponible"]
        )
        lote = st.text_input("Número de Lote:", placeholder="Ej: LOTE-8942")
        cantidad = st.number_input("Cantidad de Unidades a Ingresar:", min_value=1, value=1, step=1)
        
    with col2:
        fecha_vencimiento = st.date_input("Fecha de Vencimiento:", min_value=datetime.today())
        usuario_id = st.number_input("ID del Usuario Responsable (Enfermero):", min_value=1, value=1)

    btn_guardar = st.form_submit_button("Guardar en Inventario")

if btn_guardar:
    if not opciones_cat:
        st.error("Debe existir al menos un medicamento en 'cat_medicamentos' para guardar.")
    elif not lote:
        st.warning("Por favor ingrese el número de lote.")
    else:
        med_id = int(medicamento_seleccionado.split(" - ")[0])
        
        conn = obtener_conexion()
        if conn:
            cursor = conn.cursor()
            query_inv = """
                INSERT INTO inventario_carro 
                (medicamento_id, usuario_id, lote, fecha_vencimiento, estado, editado_manual)
                VALUES (%s, %s, %s, %s, %s, 1);
            """
            
            dias_para_vencer = (fecha_vencimiento - datetime.now().date()).days
            estado = "vigente"
            tipo_alerta = None
            
            if dias_para_vencer <= 0:
                estado = "vencido"
                tipo_alerta = "VENCIDO"
            elif dias_para_vencer <= 30:
                estado = "proximo_a_vencer"
                tipo_alerta = "PROXIMO_VENCER"
            
            for _ in range(cantidad):
                cursor.execute(query_inv, (med_id, usuario_id, lote, fecha_vencimiento, estado))
                inv_id = cursor.lastrowid
                
                # Generar alerta automática si aplica
                if tipo_alerta:
                    query_alerta = "INSERT INTO alertas (medicamento_id, tipo) VALUES (%s, %s);"
                    cursor.execute(query_alerta, (inv_id, tipo_alerta))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            st.success(f"¡Se registraron correctamente {cantidad} unidades del lote {lote}!")
            st.rerun()

# --- BLOQUE 3: TABLA VISUAL DE INVENTARIO ---
st.write("---")
st.write("### 📊 Inventario Actual en el Carro de Paro")

conn = obtener_conexion()
if conn:
    query_vista = """
        SELECT 
            i.id AS 'ID Registro',
            c.nombre AS 'Medicamento',
            c.criticidad AS 'Criticidad',
            i.lote AS 'Lote',
            i.fecha_vencimiento AS 'Fecha Vencimiento',
            i.estado AS 'Estado',
            u.nombre AS 'Registrado por'
        FROM inventario_carro i
        JOIN cat_medicamentos c ON i.medicamento_id = c.id
        JOIN usuarios u ON i.usuario_id = u.id
        ORDER BY i.fecha_registro DESC;
    """
    df_inventario = pd.read_sql(query_vista, conn)
    conn.close()
    
    if not df_inventario.empty:
        st.dataframe(df_inventario, use_container_width=True)
    else:
        st.info("Aún no hay medicamentos registrados en el inventario.")