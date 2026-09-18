import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.connection import obtener_conexion
from src.database.auth import verificar_credenciales
from src.database.auditoria import registrar_log

st.set_page_config(page_title="Carro de Paro IA", layout="wide")

# --- CONTROL DE SESIÓN Y LOGIN ---
if "usuario" not in st.session_state:
    st.session_state["usuario"] = None

if st.session_state["usuario"] is None:
    st.title("🔑 Iniciar Sesión - Carro de Paro")
    
    with st.form("form_login"):
        correo = st.text_input("Correo Electrónico:", placeholder="usuario@hospital.com")
        password = st.text_input("Contraseña:", type="password")
        btn_login = st.form_submit_button("Ingresar")
        
        if btn_login:
            user = verificar_credenciales(correo, password)
            if user:
                st.session_state["usuario"] = user
                st.success(f"Bienvenido/a, {user['nombre']} ({user['rol']})")
                st.rerun()
            else:
                st.error("Credenciales incorrectas o usuario inactivo.")
    
    st.info("💡 Credenciales de prueba (Contraseña: 123456):\n- Enfermero: enfermero@hospital.com\n- Admin: admin@hospital.com\n- Auditor: auditor@hospital.com")
    st.stop()

# --- BARRA LATERAL (USUARIO ACTIVO Y CERRAR SESIÓN) ---
user_actual = st.session_state["usuario"]
st.sidebar.title(f"👤 {user_actual['nombre']}")
st.sidebar.caption(f"Rol: **{user_actual['rol']}**")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state["usuario"] = None
    st.rerun()

st.title("🚑 Control e Inventario de Medicamentos - Carro de Paro")

# --- BLOQUE 1: KPIs ---
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

# --- BLOQUE 2: PERMISOS Y REGISTRO DE INVENTARIO (ENFERMERO Y ADMIN) ---
if user_actual['rol'] in ['ENFERMERO', 'ADMINISTRADOR']:
    st.subheader("📋 Registro Asistido e Ingreso por Lotes")

    with st.form("form_registro"):
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
        with col2:
            cantidad = st.number_input("Cantidad de Unidades:", min_value=1, value=1, step=1)
            fecha_vencimiento = st.date_input("Fecha de Vencimiento:", min_value=datetime.today())

        btn_guardar = st.form_submit_button("Guardar en Inventario")

    if btn_guardar:
        if not opciones_cat or not lote:
            st.warning("Complete todos los campos requeridos.")
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
                
                ultimos_ids = []
                for _ in range(cantidad):
                    cursor.execute(query_inv, (med_id, user_actual['id'], lote, fecha_vencimiento, estado))
                    inv_id = cursor.lastrowid
                    ultimos_ids.append(inv_id)
                    
                    if tipo_alerta:
                        cursor.execute("INSERT INTO alertas (medicamento_id, tipo) VALUES (%s, %s);", (inv_id, tipo_alerta))
                
                conn.commit()
                cursor.close()
                conn.close()
                
                # TRAZABILIDAD: Registrar en log_auditoria
                registrar_log(
                    usuario_id=user_actual['id'],
                    accion="INSERCION",
                    entidad="inventario_carro",
                    entidad_id=ultimos_ids[0] if ultimos_ids else None,
                    detalle=f"Ingreso masivo de {cantidad} unidades del lote {lote}"
                )
                
                st.success(f"¡Registradas {cantidad} unidades correctamente!")
                st.rerun()

# --- BLOQUE 3: INVENTARIO Y VISTA DE AUDITORÍA (AUDITOR Y ADMIN) ---
st.write("---")
tab1, tab2 = st.tabs(["📊 Inventario Actual", "📜 Log de Auditoría (Trazabilidad)"])

with tab1:
    conn = obtener_conexion()
    if conn:
        query_vista = """
            SELECT i.id AS 'ID', c.nombre AS 'Medicamento', i.lote AS 'Lote', 
                   i.fecha_vencimiento AS 'Vencimiento', i.estado AS 'Estado', u.nombre AS 'Registrado Por'
            FROM inventario_carro i
            JOIN cat_medicamentos c ON i.medicamento_id = c.id
            JOIN usuarios u ON i.usuario_id = u.id
            ORDER BY i.fecha_registro DESC;
        """
        df_inv = pd.read_sql(query_vista, conn)
        conn.close()
        st.dataframe(df_inv, use_container_width=True)

with tab2:
    if user_actual['rol'] in ['AUDITOR', 'ADMINISTRADOR']:
        conn = obtener_conexion()
        if conn:
            query_audit = """
                SELECT a.id AS 'ID Log', u.nombre AS 'Usuario', u.rol AS 'Rol', 
                       a.accion AS 'Acción', a.entidad AS 'Entidad', a.entidad_id AS 'ID Entidad', 
                       a.fecha AS 'Fecha/Hora', a.detalle AS 'Detalle'
                FROM log_auditoria a
                JOIN usuarios u ON a.usuario_id = u.id
                ORDER BY a.fecha DESC;
            """
            df_audit = pd.read_sql(query_audit, conn)
            conn.close()
            st.dataframe(df_audit, use_container_width=True)
    else:
        st.warning("⚠️ Su rol de usuario no tiene permisos para consultar los logs de auditoría.")