import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.connection import obtener_conexion
from src.database.auth import verificar_credenciales, hash_password
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
    st.stop()

# --- BARRA LATERAL ---
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

# --- PESTAÑAS PRINCIPALES DEL SISTEMA ---
pestanias = ["📊 Inventario y Gestión", "📜 Log de Auditoría"]
if user_actual['rol'] == 'ADMINISTRADOR':
    pestanias.append("👥 Gestión de Usuarios")

tabs = st.tabs(pestanias)

# ==========================================
# PESTAÑA 1: INVENTARIO Y GESTIÓN (CRUD)
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
                st.success(f"¡Se registraron {cantidad} unidades correctamente!")
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

    # --- EDICIÓN / ELIMINACIÓN CONTROLADA ---
    if user_actual['rol'] in ['ENFERMERO', 'ADMINISTRADOR']:
        st.write("---")
        st.subheader("🛠️ Modificar o Eliminar Registro de Inventario")
        col_edit1, col_edit2 = st.columns(2)
        
        with col_edit1:
            st.write("#### ✏️ Editar Registro (Fecha Protegida)")
            id_mod = st.number_input("Ingrese el ID del Registro a Modificar:", min_value=1, step=1)
            nuevo_lote = st.text_input("Nuevo Número de Lote:", placeholder="Dejar vacío si no cambia")
            st.warning("🔒 La fecha de vencimiento NO se puede modificar por normatividad de seguridad médica.")
            btn_modificar = st.button("Actualizar Lote")
            
            if btn_modificar:
                if nuevo_lote.strip():
                    conn = obtener_conexion()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE inventario_carro SET lote = %s WHERE id = %s;", (nuevo_lote, id_mod))
                        conn.commit()
                        cursor.close()
                        conn.close()
                        registrar_log(user_actual['id'], "ACTUALIZACION", "inventario_carro", id_mod, f"Se actualizó el lote a: {nuevo_lote}")
                        st.success(f"Registro ID {id_mod} actualizado.")
                        st.rerun()
                else:
                    st.error("Ingrese el nuevo lote para actualizar.")

        with col_edit2:
            st.write("#### 🗑️ Eliminar Registro Erróneo")
            id_del = st.number_input("Ingrese el ID del Registro a Eliminar:", min_value=1, step=1, key="del_id")
            btn_eliminar = st.button("Eliminar Registro", type="primary")
            
            if btn_eliminar:
                conn = obtener_conexion()
                if conn:
                    cursor = conn.cursor()
                    # Eliminar alertas asociadas primero para mantener integridad referencial
                    cursor.execute("DELETE FROM alertas WHERE medicamento_id = %s;", (id_del,))
                    cursor.execute("DELETE FROM inventario_carro WHERE id = %s;", (id_del,))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    registrar_log(user_actual['id'], "ELIMINACION", "inventario_carro", id_del, f"Se eliminó el registro ID {id_del}")
                    st.success(f"Registro ID {id_del} eliminado del inventario.")
                    st.rerun()

# ==========================================
# PESTAÑA 2: LOG DE AUDITORÍA (TRAZABILIDAD)
# ==========================================
with tabs[1]:
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
    else:
        st.warning("⚠️ Su rol de usuario no tiene permisos para consultar los logs de auditoría.")

# ==========================================
# PESTAÑA 3: GESTIÓN DE USUARIOS (SOLO ADMIN)
# ==========================================
# ==========================================
# PESTAÑA 3: GESTIÓN DE USUARIOS (SOLO ADMIN)
# ==========================================
if user_actual['rol'] == 'ADMINISTRADOR':
    with tabs[2]:
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
                        st.success(f"¡Usuario '{u_nombre}' creado exitosamente!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al crear usuario (verifique si el correo ya existe): {e}")
            else:
                st.warning("Por favor complete todos los campos del usuario.")

        # --- SECCIÓN: ACTIVAR / DESACTIVAR USUARIOS ---
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

                        registrar_log(
                            user_actual['id'], 
                            "ACTUALIZACION", 
                            "usuarios", 
                            u_select_id, 
                            f"Cambio de estado a {'ACTIVO' if val_activo == 1 else 'INACTIVO'}"
                        )
                        st.success(f"Estado del usuario ID {u_select_id} actualizado correctamente.")
                        st.rerun()