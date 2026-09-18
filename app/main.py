import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.connection import obtener_conexion
from src.database.auth import verificar_credenciales, hash_password
from src.database.auditoria import registrar_log
from src.utils.exportador import generar_csv

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
    st.stop()

# --- BARRA LATERAL ---
user_actual = st.session_state["usuario"]
st.sidebar.title(f"👤 {user_actual['nombre']}")
st.sidebar.caption(f"Rol: **{user_actual['rol']}**")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state["usuario"] = None
    st.rerun()

st.title("🚑 Control e Inventario de Medicamentos - Carro de Paro")

# Mensaje de éxito persistente
if "mensaje_exito" in st.session_state:
    st.success(st.session_state["mensaje_exito"])
    del st.session_state["mensaje_exito"]

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

# --- PESTAÑAS DEL SISTEMA ---
pestanias = ["📊 Inventario y Gestión", "⚠️ Alertas Preventivas", "📜 Log de Auditoría"]
if user_actual['rol'] == 'ADMINISTRADOR':
    pestanias.append("⚙️ Administración del Sistema")

tabs = st.tabs(pestanias)

# ==========================================
# PESTAÑA 1: INVENTARIO Y EXPORTACIÓN
# ==========================================
with tabs[0]:
    if user_actual['rol'] in ['ENFERMERO', 'ADMINISTRADOR']:
        st.subheader("📋 Registro de Medicamentos e Ingreso por Lotes")
        with st.form("form_registro"):
            conn = obtener_conexion()
            opciones_cat = []
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT id, nombre, criticidad FROM cat_medicamentos;")
                opciones_cat = cursor.fetchall()
                cursor.close()
                conn.close()
            
            nombres_cat = [f"{m['id']} - {m['nombre']} ({m['criticidad']})" for m in opciones_cat]
            
            col1, col2 = st.columns(2)
            with col1:
                med_sel = st.selectbox("Medicamento del Catálogo:", options=nombres_cat if nombres_cat else ["Sin catálogo"])
                lote = st.text_input("Número de Lote:", placeholder="Ej: LOT-9942")
            with col2:
                cantidad = st.number_input("Cantidad a Ingresar:", min_value=1, value=1, step=1)
                fecha_venc = st.date_input("Fecha de Vencimiento:", min_value=datetime.today())

            btn_guardar = st.form_submit_button("Guardar en Inventario")

        if btn_guardar and opciones_cat and lote:
            med_id = int(med_sel.split(" - ")[0])
            conn = obtener_conexion()
            if conn:
                cursor = conn.cursor()
                query_inv = """
                    INSERT INTO inventario_carro (medicamento_id, usuario_id, lote, fecha_vencimiento, estado, editado_manual)
                    VALUES (%s, %s, %s, %s, %s, 1);
                """
                dias = (fecha_venc - datetime.now().date()).days
                estado = "vencido" if dias <= 0 else ("proximo_a_vencer" if dias <= 30 else "vigente")
                tipo_alerta = "VENCIDO" if dias <= 0 else ("PROXIMO_VENCER" if dias <= 30 else None)
                
                ult_ids = []
                for _ in range(cantidad):
                    cursor.execute(query_inv, (med_id, user_actual['id'], lote, fecha_venc, estado))
                    inv_id = cursor.lastrowid
                    ult_ids.append(inv_id)
                    if tipo_alerta:
                        cursor.execute("INSERT INTO alertas (medicamento_id, tipo) VALUES (%s, %s);", (inv_id, tipo_alerta))
                
                conn.commit()
                cursor.close()
                conn.close()
                
                registrar_log(user_actual['id'], "INSERCION", "inventario_carro", ult_ids[0], f"Ingreso masivo de {cantidad} unidades del lote {lote}")
                st.session_state["mensaje_exito"] = f"¡Se registraron {cantidad} unidades correctamente!"
                st.rerun()

    st.write("### 📦 Lista de Inventario Actual")
    conn = obtener_conexion()
    if conn:
        query_inv = """
            SELECT i.id AS 'ID', c.nombre AS 'Medicamento', i.lote AS 'Lote', 
                   i.fecha_vencimiento AS 'Vencimiento', i.estado AS 'Estado', u.nombre AS 'Registrado Por'
            FROM inventario_carro i
            JOIN cat_medicamentos c ON i.medicamento_id = c.id
            JOIN usuarios u ON i.usuario_id = u.id
            ORDER BY i.fecha_registro DESC;
        """
        df_inv = pd.read_sql(query_inv, conn)
        conn.close()
        st.dataframe(df_inv, use_container_width=True)

        # Botón para exportar el Inventario a CSV
        st.download_button(
            label="📥 Descargar Reporte de Inventario (CSV)",
            data=generar_csv(df_inv),
            file_name=f"reporte_inventario_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

    # --- EDICIÓN / ELIMINACIÓN ---
    if user_actual['rol'] in ['ENFERMERO', 'ADMINISTRADOR']:
        st.write("---")
        st.subheader("🛠️ Modificar o Eliminar Registro")
        col_edit1, col_edit2 = st.columns(2)
        
        with col_edit1:
            st.write("#### ✏️ Editar Lote (Fecha Protegida)")
            id_mod = st.number_input("ID del Registro:", min_value=1, step=1)
            nuevo_lote = st.text_input("Nuevo Lote:")
            st.warning("🔒 La fecha de vencimiento es inmutable por seguridad.")
            if st.button("Actualizar Lote") and nuevo_lote.strip():
                conn = obtener_conexion()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE inventario_carro SET lote = %s WHERE id = %s;", (nuevo_lote, id_mod))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    registrar_log(user_actual['id'], "ACTUALIZACION", "inventario_carro", id_mod, f"Lote actualizado a: {nuevo_lote}")
                    st.session_state["mensaje_exito"] = f"Registro ID {id_mod} actualizado."
                    st.rerun()

        with col_edit2:
            st.write("#### 🗑️ Eliminar Registro")
            id_del = st.number_input("ID del Registro a Eliminar:", min_value=1, step=1, key="del_id")
            if st.button("Eliminar Registro", type="primary"):
                conn = obtener_conexion()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM alertas WHERE medicamento_id = %s;", (id_del,))
                    cursor.execute("DELETE FROM inventario_carro WHERE id = %s;", (id_del,))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    registrar_log(user_actual['id'], "ELIMINACION", "inventario_carro", id_del, f"Registro ID {id_del} eliminado")
                    st.session_state["mensaje_exito"] = f"Registro ID {id_del} eliminado."
                    st.rerun()

# ==========================================
# PESTAÑA 2: ALERTAS PREVENTIVAS VISUALES
# ==========================================
with tabs[1]:
    st.subheader("🚨 Panel de Alertas Preventivas y Notificaciones")
    conn = obtener_conexion()
    if conn:
        query_alertas = """
            SELECT a.id AS 'ID Alerta', c.nombre AS 'Medicamento', i.lote AS 'Lote', 
                   i.fecha_vencimiento AS 'Fecha Vencimiento', a.tipo AS 'Tipo Alerta', 
                   a.resuelta AS 'Resuelta', a.fecha_creacion AS 'Fecha Detección'
            FROM alertas a
            JOIN inventario_carro i ON a.medicamento_id = i.id
            JOIN cat_medicamentos c ON i.medicamento_id = c.id
            ORDER BY a.resuelta ASC, i.fecha_vencimiento ASC;
        """
        df_alertas = pd.read_sql(query_alertas, conn)
        conn.close()

        if not df_alertas.empty:
            df_alertas['Estado Alerta'] = df_alertas['Resuelta'].apply(lambda x: "✅ Resuelta" if x == 1 else "🔴 Pendiente")
            st.dataframe(df_alertas[['ID Alerta', 'Medicamento', 'Lote', 'Fecha Vencimiento', 'Tipo Alerta', 'Estado Alerta', 'Fecha Detección']], use_container_width=True)
            
            # Exportar Alertas
            st.download_button(
                label="📥 Exportar Alertas a CSV",
                data=generar_csv(df_alertas),
                file_name=f"reporte_alertas_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

            # Acción: Marcar Alerta como Resuelta
            if user_actual['rol'] in ['ENFERMERO', 'ADMINISTRADOR']:
                st.write("---")
                col_al1, col_al2 = st.columns(2)
                with col_al1:
                    al_id = st.number_input("ID de Alerta a gestionar:", min_value=1, step=1)
                with col_al2:
                    if st.button("Marcar Alerta como Resuelta"):
                        conn = obtener_conexion()
                        if conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE alertas SET resuelta = 1 WHERE id = %s;", (al_id,))
                            conn.commit()
                            cursor.close()
                            conn.close()
                            registrar_log(user_actual['id'], "ACTUALIZACION", "alertas", al_id, "Alerta marcada como resuelta")
                            st.session_state["mensaje_exito"] = f"Alerta ID {al_id} marcada como resuelta."
                            st.rerun()
        else:
            st.info("🟢 No hay alertas pendientes en este momento.")

# ==========================================
# PESTAÑA 3: LOG DE AUDITORÍA (TRAZABILIDAD)
# ==========================================
with tabs[2]:
    if user_actual['rol'] in ['AUDITOR', 'ADMINISTRADOR']:
        st.subheader("📜 Auditoría y Registro de Eventos del Sistema")
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
            
            # Exportar Auditoría
            st.download_button(
                label="📥 Exportar Logs de Auditoría (CSV)",
                data=generar_csv(df_audit),
                file_name=f"log_auditoria_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    else:
        st.warning("⚠️ Su rol de usuario no tiene permisos para consultar los logs de auditoría.")

# ==========================================
# PESTAÑA 4: ADMINISTRACIÓN DEL SISTEMA
# ==========================================
if user_actual['rol'] == 'ADMINISTRADOR':
    with tabs[3]:
        col_admin1, col_admin2 = st.columns(2)

        with col_admin1:
            st.subheader("💊 Agregar Medicamento al Catálogo")
            with st.form("form_cat_med"):
                c_nombre = st.text_input("Nombre y Concentración:", placeholder="Ej: Dopamina 200mg/5ml")
                c_desc = st.text_area("Descripción / Indicación:", placeholder="Ampolla para soporte inotrópico")
                c_criticidad = st.selectbox("Nivel de Criticidad:", options=["ALTA", "MEDIA", "BAJA"])
                btn_crear_cat = st.form_submit_button("Guardar en Catálogo")

            if btn_crear_cat:
                if c_nombre:
                    conn = obtener_conexion()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            query_c = "INSERT INTO cat_medicamentos (nombre, descripcion, criticidad) VALUES (%s, %s, %s);"
                            cursor.execute(query_c, (c_nombre, c_desc, c_criticidad))
                            new_cat_id = cursor.lastrowid
                            conn.commit()
                            cursor.close()
                            conn.close()

                            registrar_log(user_actual['id'], "INSERCION", "cat_medicamentos", new_cat_id, f"Nuevo medicamento en catálogo: {c_nombre}")
                            st.session_state["mensaje_exito"] = f"¡Medicamento '{c_nombre}' agregado al catálogo!"
                            st.rerun()
                        except Exception as e:
                            if "1062" in str(e):
                                st.warning(f"⚠️ El medicamento '{c_nombre}' ya se encuentra registrado en el catálogo.")
                            else:
                                st.error(f"Error al guardar en el catálogo: {e}")
                else:
                    st.warning("Ingrese el nombre del medicamento.")

        with col_admin2:
            st.subheader("👤 Crear Nuevo Usuario del Sistema")
            with st.form("form_crear_usuario"):
                u_nombre = st.text_input("Nombre Completo:")
                u_correo = st.text_input("Correo Electrónico:")
                u_pass = st.text_input("Contraseña:", type="password")
                u_rol = st.selectbox("Rol Asignado:", options=["ENFERMERO", "AUDITOR", "ADMINISTRADOR"])
                btn_crear_u = st.form_submit_button("Crear Usuario")

            if btn_crear_u:
                if u_nombre and u_correo and u_pass:
                    pass_h = hash_password(u_pass)
                    conn = obtener_conexion()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            query_u = "INSERT INTO usuarios (nombre, correo, password_hash, rol, activo) VALUES (%s, %s, %s, %s, 1);"
                            cursor.execute(query_u, (u_nombre, u_correo, pass_h, u_rol))
                            new_u_id = cursor.lastrowid
                            conn.commit()
                            cursor.close()
                            conn.close()

                            registrar_log(user_actual['id'], "CREACION_USUARIO", "usuarios", new_u_id, f"Se creó el usuario {u_nombre} con rol {u_rol}")
                            st.session_state["mensaje_exito"] = f"¡Usuario '{u_nombre}' creado exitosamente!"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al crear usuario: {e}")
                else:
                    st.warning("Complete todos los campos del usuario.")

        st.write("---")
        st.subheader("🔄 Activar / Desactivar Usuarios del Sistema")

        conn = obtener_conexion()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, nombre, correo, rol, activo FROM usuarios WHERE id != %s;", (user_actual['id'],))
            lista_usuarios = cursor.fetchall()
            cursor.close()
            conn.close()

            if lista_usuarios:
                df_u = pd.DataFrame(lista_usuarios)
                df_u['Estado'] = df_u['activo'].apply(lambda x: "🟢 Activo" if x == 1 else "🔴 Inactivo")
                st.dataframe(df_u[['id', 'nombre', 'correo', 'rol', 'Estado']], use_container_width=True)

                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    u_select_id = st.number_input("ID del Usuario a cambiar estado:", min_value=1, step=1, key="u_sec_id")
                with col_u2:
                    nuevo_estado = st.selectbox("Nuevo Estado:", options=["Desactivar (Inactivo)", "Activar (Activo)"])
                    btn_cambiar_estado = st.button("Actualizar Estado de Usuario")

                if btn_cambiar_estado:
                    val_activo = 1 if "Activar" in nuevo_estado else 0
                    conn = obtener_conexion()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE usuarios SET activo = %s WHERE id = %s;", (val_activo, u_select_id))
                        conn.commit()
                        cursor.close()
                        conn.close()

                        registrar_log(user_actual['id'], "ACTUALIZACION", "usuarios", u_select_id, f"Cambio de estado a {'ACTIVO' if val_activo == 1 else 'INACTIVO'}")
                        st.session_state["mensaje_exito"] = f"Estado del usuario ID {u_select_id} actualizado."
                        st.rerun()