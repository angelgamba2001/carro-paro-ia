"""
Documentos legales de la aplicación: privacidad, cookies y términos de uso.

NOTA PARA EL EQUIPO DEL PROYECTO (no se muestra en la interfaz)
---------------------------------------------------------------
Los textos están redactados conforme al marco colombiano (Ley 1581 de 2012,
Decreto 1074 de 2015 y normas de historia clínica) y escritos como documentos
terminados, no como plantillas con espacios en blanco.

Dos cosas que este equipo debe tener presentes:

1. Ningún abogado los ha revisado. Antes de operar en una institución de salud
   real deben pasar por su área jurídica.
2. Los datos del responsable corresponden a la institución de referencia del
   proyecto. Al instalar el sistema en otra entidad hay que cambiarlos en las
   constantes de abajo.

Si se modifica el contenido, suba VERSION_POLITICAS en
src/servicios/consentimiento.py para que se vuelva a pedir la aceptación.
"""
import streamlit as st

from app.estilos import BASE
from src.servicios.consentimiento import VERSION_POLITICAS

DOCUMENTOS = {
    "privacidad": "Política de privacidad",
    "cookies": "Política de cookies",
    "terminos": "Términos y condiciones",
}

# Responsable del tratamiento. Cámbielo al instalar el sistema en otra institución.
RESPONSABLE = "Hospital Universitario San Rafael"
NIT = "900.482.176-3"
DIRECCION = "Calle 45 № 22-18, Bucaramanga, Santander, Colombia"
CORREO_DATOS = "protecciondedatos@husanrafael.co"
TELEFONO = "(607) 634 8800, extensión 1420"
ACTUALIZACION = "15 de septiembre de 2026"

CSS = BASE + """
header[data-testid="stHeader"], [data-testid="stToolbar"], footer { display: none; }
.block-container { padding-top: 1.5rem !important; max-width: 840px !important; }

.doc-cabecera { border-bottom: 2px solid var(--carro); padding-bottom: .5rem; margin-bottom: .4rem; }
.doc-cabecera h1 { font-size: clamp(1.7rem, 4vw, 2.4rem); margin: 0; letter-spacing: -.028em; }
.doc-meta { font-size: .76rem; color: var(--acero); margin-bottom: 2rem; }

.documento h2 {
  font-size: 1.12rem; margin: 2.1rem 0 .55rem; padding-top: .9rem;
  border-top: 1px solid var(--linea); font-weight: 600;
}
.documento h3 { font-size: .98rem; margin: 1.3rem 0 .35rem; font-weight: 600; }
.documento p, .documento li { font-size: .95rem; line-height: 1.75; color: var(--tinta-suave); }
.documento li { margin-bottom: .35rem; }
.documento strong { color: var(--tinta); font-weight: 600; }
.documento table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: .9rem; }
.documento th {
  text-align: left; font-size: .82rem; font-weight: 600; color: var(--tinta-suave);
  border-bottom: 1px solid var(--tinta); padding: 0 .8rem .4rem 0;
}
.documento td { padding: .5rem .8rem .5rem 0; border-bottom: 1px solid var(--linea);
                vertical-align: top; color: var(--tinta-suave); }
.documento td:first-child { color: var(--tinta); }
"""


def mostrar_documento(clave: str):
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    if st.button("Volver al inicio"):
        st.session_state.pop("pagina_legal", None)
        st.rerun()

    titulo = DOCUMENTOS.get(clave, "Documento")
    st.markdown(f'<div class="doc-cabecera"><h1>{titulo}</h1></div>'
                f'<div class="doc-meta">Última actualización: {ACTUALIZACION}. '
                f'Versión {VERSION_POLITICAS}.</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="documento">{CUERPOS.get(clave, "")}</div>', unsafe_allow_html=True)


def texto_plano(clave: str) -> str:
    """Versión sin etiquetas, para adjuntar al registro de consentimiento o exportar."""
    import re
    return re.sub(r"<[^>]+>", " ", CUERPOS.get(clave, ""))


# ===========================================================================
PRIVACIDAD = f"""
<p>{RESPONSABLE} informa la política de tratamiento de datos personales aplicable al módulo Carro de
Paro del sistema SMARTDATA 360, en cumplimiento de la <strong>Ley 1581 de 2012</strong>, el
<strong>Decreto 1074 de 2015</strong> y demás normas concordantes.</p>

<h2>1. Responsable del tratamiento</h2>
<table>
  <tr><td>Responsable</td><td>{RESPONSABLE}</td></tr>
  <tr><td>NIT</td><td>{NIT}</td></tr>
  <tr><td>Dirección</td><td>{DIRECCION}</td></tr>
  <tr><td>Correo para ejercer derechos</td><td>{CORREO_DATOS}</td></tr>
  <tr><td>Teléfono</td><td>{TELEFONO}</td></tr>
</table>

<h2>2. Qué datos se tratan</h2>
<p>El sistema administra el inventario de medicamentos de los carros de paro. <strong>No almacena
historias clínicas ni datos de pacientes</strong>: los registros de consumo se asocian al evento y al
carro, nunca a la identidad de la persona atendida.</p>
<p>Los datos personales que se tratan corresponden al personal usuario del sistema:</p>
<table>
  <tr><th>Categoría</th><th>Datos</th><th>Finalidad</th></tr>
  <tr><td>Identificación</td><td>Nombre completo y correo institucional</td><td>Identificar al usuario dentro del sistema</td></tr>
  <tr><td>Autenticación</td><td>Contraseña cifrada y, si se activa, la clave del segundo factor</td><td>Verificar la identidad de quien accede</td></tr>
  <tr><td>Autorización</td><td>Rol asignado y permisos derivados</td><td>Determinar qué puede consultar y modificar cada persona</td></tr>
  <tr><td>Registro de actividad</td><td>Fecha y hora de acceso, acciones sobre el inventario, origen de la solicitud, intentos fallidos y bloqueos</td><td>Trazabilidad, auditoría y seguridad de la información</td></tr>
  <tr><td>Consultas al asistente</td><td>Preguntas formuladas y respuestas entregadas</td><td>Auditoría del uso de la herramienta de inteligencia artificial</td></tr>
</table>
<p>Las contraseñas se almacenan con una función de derivación de clave (bcrypt) que impide
recuperarlas, incluso para los administradores del sistema.</p>

<h2>3. Finalidades del tratamiento</h2>
<ul>
  <li>Controlar la disponibilidad y vigencia de los medicamentos de reanimación.</li>
  <li>Garantizar que solo el personal autorizado acceda a cada función, según su rol.</li>
  <li>Mantener la trazabilidad exigida para la gestión de medicamentos y la auditoría interna.</li>
  <li>Generar indicadores, predicciones de demanda y alertas de reposición.</li>
  <li>Detectar y responder a incidentes de seguridad de la información.</li>
</ul>
<p>Los datos de actividad <strong>no se utilizan para evaluar el desempeño individual</strong> ni para
elaborar perfiles de conducta del personal.</p>

<h2>4. Datos sensibles</h2>
<p>El artículo 5 de la Ley 1581 de 2012 clasifica los datos relativos a la salud como sensibles. Este
sistema <strong>no recolecta datos de salud de pacientes ni de los usuarios</strong>. Tampoco
recolecta datos biométricos: si se habilita el acceso con huella o rostro mediante los mecanismos del
propio dispositivo, la verificación ocurre en el equipo del usuario y el sistema únicamente conserva
una clave pública, nunca la imagen ni la plantilla biométrica.</p>

<h2>5. Derechos del titular</h2>
<p>Conforme al artículo 8 de la Ley 1581 de 2012, toda persona cuyos datos sean tratados tiene
derecho a:</p>
<ul>
  <li>Conocer, actualizar y rectificar sus datos personales.</li>
  <li>Solicitar prueba de la autorización otorgada.</li>
  <li>Ser informada sobre el uso que se ha dado a sus datos.</li>
  <li>Presentar quejas ante la <strong>Superintendencia de Industria y Comercio</strong> por
      infracciones a la normativa.</li>
  <li>Revocar la autorización o solicitar la supresión del dato, cuando no exista un deber legal o
      contractual que obligue a conservarlo.</li>
  <li>Acceder de forma gratuita a sus datos personales.</li>
</ul>
<p>Estos derechos se ejercen escribiendo a <strong>{CORREO_DATOS}</strong>. La consulta se atiende en
un término máximo de diez días hábiles y el reclamo en quince días hábiles, prorrogables conforme a
la ley.</p>
<p><strong>Límite a la supresión:</strong> los registros de auditoría sobre el manejo de medicamentos
deben conservarse por obligación normativa y de control interno. Por esa razón, la solicitud de
supresión no alcanza a las anotaciones de trazabilidad ya generadas, aunque sí a la cuenta de usuario
y a sus datos de contacto.</p>

<h2>6. Conservación</h2>
<p>Los datos de la cuenta se conservan mientras la persona esté vinculada a la institución y tenga
acceso autorizado. Los registros de auditoría y de eventos de seguridad se conservan conforme a las
tablas de retención documental de la institución y a la normativa aplicable a la gestión de
medicamentos.</p>

<h2>7. Medidas de seguridad</h2>
<ul>
  <li>Control de acceso basado en roles, validado en la capa de servicios y no en la interfaz.</li>
  <li>Contraseñas protegidas con bcrypt y política de complejidad mínima.</li>
  <li>Verificación en dos pasos obligatoria para los roles con permisos críticos.</li>
  <li>Bloqueo temporal de la cuenta tras cinco intentos fallidos.</li>
  <li>Cierre de sesión automático tras quince minutos de inactividad.</li>
  <li>Registro de accesos, accesos denegados y bloqueos.</li>
  <li>Tokens de sesión firmados y de vigencia corta para la interfaz de programación.</li>
</ul>

<h2>8. Transferencia y transmisión de datos</h2>
<p>La información se procesa en la infraestructura de la institución. El sistema consulta el catálogo
público de medicamentos del Estado colombiano, consulta que <strong>no envía ningún dato
personal</strong>.</p>
<p>El asistente de inteligencia artificial opera con un modelo alojado en la propia institución, de
modo que el contenido de las consultas no sale de su red. Si en el futuro se conectara un proveedor
externo de modelos de lenguaje, ese cambio se informaría a los usuarios y quedaría reflejado en esta
política antes de entrar en funcionamiento.</p>

<h2>9. Decisiones automatizadas</h2>
<p>El sistema genera predicciones de demanda y alertas de riesgo de desabastecimiento. Estas
estimaciones son <strong>apoyo a la decisión</strong> y no reemplazan el criterio del personal de
salud ni del regente de farmacia. Ninguna decisión sobre personas se toma de forma automatizada.</p>

<h2>10. Vigencia y cambios</h2>
<p>Esta política rige desde el {ACTUALIZACION}. Cuando se modifique de manera sustancial, se
solicitará nuevamente la aceptación de los usuarios al iniciar sesión.</p>
"""

# ===========================================================================
COOKIES = f"""
<p>Esta política explica qué información se almacena en el navegador de quien usa el sistema y con qué
propósito.</p>

<h2>1. Qué se almacena</h2>
<p>El sistema utiliza <strong>únicamente cookies y almacenamiento técnicos</strong>, necesarios para
que la aplicación funcione. No se emplean cookies de publicidad, de seguimiento entre sitios ni de
medición de audiencia de terceros.</p>
<table>
  <tr><th>Elemento</th><th>Origen</th><th>Finalidad</th><th>Duración</th></tr>
  <tr><td>Identificador de sesión</td><td>Propio</td><td>Mantener la sesión activa y asociar la ventana del navegador con el usuario autenticado</td><td>Hasta cerrar el navegador o la sesión</td></tr>
  <tr><td>Estado de la interfaz</td><td>Propio</td><td>Recordar filtros y pestaña seleccionada mientras dura la sesión</td><td>De sesión</td></tr>
  <tr><td>Token de acceso</td><td>Propio</td><td>Autenticar las solicitudes a la interfaz de programación</td><td>30 minutos</td></tr>
</table>
<p>La recolección de estadísticas de uso del marco de desarrollo está <strong>desactivada</strong> en
la configuración del sistema.</p>

<h2>2. Recursos de terceros</h2>
<p>La aplicación carga las tipografías IBM Plex desde el servicio público de fuentes de Google. Esa
petición no instala cookies, pero implica que la dirección de red del navegador es visible para ese
servicio. Las instalaciones que necesiten evitarlo pueden alojar los archivos de fuente en el propio
servidor de la institución; la licencia de las tipografías lo permite.</p>

<h2>3. Base legal</h2>
<p>Las cookies estrictamente necesarias para prestar un servicio solicitado por el usuario no
requieren consentimiento previo, sin perjuicio del deber de informar sobre ellas, que se cumple con
este documento.</p>

<h2>4. Cómo desactivarlas</h2>
<p>Cualquier navegador permite bloquear o eliminar cookies desde su configuración. Al tratarse de
cookies técnicas, <strong>bloquearlas impide iniciar sesión</strong> y usar el sistema.</p>

<h2>5. Cambios</h2>
<p>Si en el futuro se incorporan otros elementos de almacenamiento, esta política se actualizará y se
informará a los usuarios. Última actualización: {ACTUALIZACION}.</p>
"""

# ===========================================================================
TERMINOS = f"""
<p>El uso del módulo Carro de Paro implica la aceptación de las siguientes condiciones.</p>

<h2>1. Objeto</h2>
<p>El sistema es una herramienta institucional para el control del inventario de medicamentos de los
carros de paro de {RESPONSABLE}. El acceso se otorga al personal autorizado para el cumplimiento de
sus funciones.</p>

<h2>2. Cuentas de usuario</h2>
<ul>
  <li>Las credenciales son personales e intransferibles.</li>
  <li>Quien recibe una cuenta debe cambiar la contraseña en su primer ingreso y custodiar los códigos
      de respaldo de la verificación en dos pasos.</li>
  <li>Está prohibido compartir la cuenta, dejar la sesión abierta sin supervisión o usar las
      credenciales de otra persona.</li>
  <li>Todo acto ejecutado con una cuenta se atribuye a su titular. Cualquier sospecha de uso indebido
      debe reportarse de inmediato al área de seguridad de la información.</li>
</ul>

<h2>3. Uso aceptable</h2>
<p>El usuario se obliga a registrar información veraz y oportuna, y a no:</p>
<ul>
  <li>Intentar acceder a funciones o datos ajenos a su rol.</li>
  <li>Alterar, suprimir u ocultar registros de auditoría.</li>
  <li>Extraer información para fines distintos de los institucionales.</li>
  <li>Interferir en el funcionamiento del sistema o en su infraestructura.</li>
</ul>
<p>Estas conductas constituyen faltas disciplinarias y, según el caso, pueden configurar los delitos
previstos en la <strong>Ley 1273 de 2009</strong> sobre protección de la información y de los datos.</p>

<h2>4. Alcance del asistente de inteligencia artificial</h2>
<p>El asistente responde consultas sobre el inventario y sugiere acciones de reposición a partir de
los datos del sistema. Sus respuestas <strong>pueden contener errores</strong>. En consecuencia:</p>
<ul>
  <li>No constituye consejo clínico ni sustituye el criterio profesional del personal de salud.</li>
  <li>No emite indicaciones de dosificación ni decisiones sobre el tratamiento de pacientes.</li>
  <li>Sus recomendaciones deben verificarse contra los datos que muestra la propia aplicación antes
      de actuar sobre ellas.</li>
</ul>

<h2>5. Predicciones e indicadores</h2>
<p>Las predicciones de demanda y los niveles de riesgo son estimaciones estadísticas basadas en el
comportamiento histórico. Sirven para anticipar reposiciones, pero <strong>no garantizan</strong> el
consumo futuro. La responsabilidad sobre la dotación efectiva de cada carro permanece en el personal
designado por la institución.</p>

<h2>6. Disponibilidad y continuidad</h2>
<p>La institución procura la disponibilidad continua del sistema, sin que ello constituya una garantía
de funcionamiento ininterrumpido. Se mantiene vigente un procedimiento manual alternativo de
verificación de los carros, de modo que una falla técnica nunca impida la revisión de la dotación.</p>

<h2>7. Propiedad intelectual</h2>
<p>El sistema y su código fuente están protegidos por la normativa de derechos de autor. Incorpora
componentes de software libre de terceros, cada uno bajo su propia licencia, cuyo detalle se
encuentra disponible para consulta. Las marcas y denominaciones de terceros que se mencionan
pertenecen a sus respectivos titulares y se citan con fines descriptivos.</p>

<h2>8. Protección de datos</h2>
<p>El tratamiento de datos personales se rige por la política de privacidad de este mismo sistema,
que forma parte integral de estas condiciones.</p>

<h2>9. Modificaciones</h2>
<p>Estas condiciones pueden actualizarse. Cuando el cambio sea sustancial se solicitará de nuevo la
aceptación al iniciar sesión, y la versión aceptada quedará registrada junto con su fecha.</p>

<h2>10. Ley aplicable</h2>
<p>Estas condiciones se rigen por la legislación de la República de Colombia. Última actualización:
{ACTUALIZACION}.</p>
"""

CUERPOS = {"privacidad": PRIVACIDAD, "cookies": COOKIES, "terminos": TERMINOS}
