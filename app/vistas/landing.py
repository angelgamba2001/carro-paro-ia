"""
Portada pública y pantalla de acceso.

Movimiento: todo en CSS, porque Streamlit no ejecuta JavaScript dentro de sus
bloques. Hay un único momento de autor —la entrada escalonada del hero y el
trazado del monitor— y después la línea roja que se dibuja al ritmo del scroll
(`animation-timeline: view()`). Las secciones NO llevan disolvencia propia: una
misma entrada repetida en cada bloque es ruido, no diseño. Donde el navegador no
soporta las animaciones ligadas al scroll, el contenido se ve igual gracias al
bloque `@supports`.
"""
import streamlit as st

from src import config
from app import legal, sesion
from app.filtros import solo_caracteres_de_correo
from app.estilos import BASE
from src.seguridad.autenticacion import autenticar, canal_mfa, completar_login_mfa
from src.servicios.consentimiento import TEXTO_ACEPTACION, VERSION_POLITICAS, registrar_aceptacion
from src.servicios.inventario import recalcular_estados

CSS = BASE + """
header[data-testid="stHeader"], [data-testid="stToolbar"], footer, #MainMenu { display: none; }
/* Un ancho de documento, no de tablero: a 1280px una columna de 70 caracteres deja
   media página vacía a la derecha. Todo —barra, texto, tabla y pie— comparte el
   mismo borde izquierdo, que es lo que hace que la página se lea como una sola pieza. */
.block-container { max-width: 1120px !important; padding: 0 clamp(1.1rem, 4vw, 3rem) 0 !important; }

/* ---------- Movimiento ----------
   Un solo momento de autor: la entrada del hero y, después, la línea roja que se
   va dibujando a medida que se lee. Nada de la misma disolvencia repetida en cada
   sección; el resto del contenido está visible desde el principio. */
@keyframes surgir { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }
@keyframes trazo  { to { stroke-dashoffset: 0; } }
@keyframes crecer { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@keyframes barrido { from { transform: scaleX(0); } to { transform: scaleX(1); } }

.entra { animation: surgir .7s cubic-bezier(.16,1,.3,1) backwards; }
.d1 { animation-delay: .05s; } .d2 { animation-delay: .16s; }
.d3 { animation-delay: .27s; } .d4 { animation-delay: .38s; }

/* ---------- Barra de navegación ---------- */
.barra {
  display: flex; align-items: center; gap: 2rem;
  padding: 1.05rem 0 .95rem; border-bottom: 1px solid var(--linea);
}
.marca { display: flex; align-items: baseline; gap: .55rem; }
.marca b { font-size: 1.04rem; font-weight: 600; letter-spacing: -.012em; white-space: nowrap; }
.marca span { font-size: .76rem; color: var(--acero); white-space: nowrap; letter-spacing: .035em; }
.nav { display: flex; gap: 1.6rem; margin-left: auto; }
.nav a {
  font-size: .89rem; color: var(--tinta-suave); text-decoration: none;
  padding-bottom: .22rem; border-bottom: 1px solid transparent; transition: color .18s, border-color .18s;
}
.nav a:hover { color: var(--tinta); border-bottom-color: var(--carro); }
.sello {
  font-family: var(--mono); font-size: .71rem; color: var(--carro);
  border: 1px solid var(--carro); padding: .12rem .42rem; white-space: nowrap;
}

/* ---------- Hero ---------- */
.hero { padding: clamp(3rem, 8vw, 5.5rem) 0 0; }
.hero h1 {
  font-size: clamp(2.5rem, 6.2vw, 4.9rem); line-height: .99; letter-spacing: -.038em;
  font-weight: 600; margin: 0 0 1.25rem; max-width: 16ch;
}
.hero h1 em { font-style: normal; color: var(--carro); }
/* Streamlit fija su propio tamaño para los <p> de markdown: hay que ganarle en
   especificidad o el texto de entrada se queda en 15px junto a un titular de 78px. */
.hero p.entrada {
  font-size: clamp(1.08rem, 1.5vw, 1.26rem); line-height: 1.62;
  color: var(--tinta-suave); max-width: 58ch; margin: 0 0 .2rem;
}
/* Las cifras van dentro de la frase que las explica, no en una banda aparte */
.entrada var {
  font-style: normal; font-family: var(--mono); font-variant-numeric: tabular-nums;
  font-feature-settings: "zero" 1; font-weight: 600; color: var(--tinta);
  font-size: .94em; letter-spacing: -.02em;
}

/* ---------- Trazado del monitor ---------- */
.monitor { margin: clamp(2.6rem, 5vw, 3.6rem) 0 0; border-top: 1px solid var(--linea); }
.monitor svg { display: block; width: 100%; height: 92px; }
.monitor path {
  fill: none; stroke: var(--monitor); stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round;
  stroke-dasharray: 2400; stroke-dashoffset: 2400;
  animation: trazo 2.8s cubic-bezier(.25,.1,.25,1) .35s forwards;
}
.monitor figcaption {
  font-size: .8rem; color: var(--acero); line-height: 1.5;
  padding: .4rem 0 0; border-top: 1px solid var(--linea);
}

/* ---------- Cajones ---------- */
.cajones { margin: clamp(3.5rem, 9vw, 6rem) 0 0; }

/* Cada sección dibuja su tramo de la columna al entrar en pantalla; juntos forman
   una línea continua que acompaña la lectura de principio a fin. */
.cajon { position: relative; }
.cajon::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 2px;
  background: var(--carro); transform-origin: top;
}
@supports (animation-timeline: view()) {
  .cajon::before {
    transform: scaleY(0);
    animation-name: crecer; animation-duration: auto; animation-timing-function: linear;
    animation-fill-mode: both;
    animation-timeline: view(); animation-range: entry 14% cover 42%;
  }
}

.cajon {
  padding: clamp(1.9rem, 3.8vw, 2.9rem) 0 clamp(1.9rem, 3.8vw, 2.9rem) clamp(1.3rem, 3vw, 2.4rem);
  border-top: 1px solid var(--linea);
}
.cajon:last-of-type { border-bottom: 1px solid var(--linea); }
.cajon h2 { font-size: clamp(1.45rem, 2.6vw, 2.05rem); line-height: 1.16; margin: 0 0 .9rem;
            max-width: 28ch; letter-spacing: -.026em; }
.cajon p { font-size: 1.04rem; line-height: 1.7; color: var(--tinta-suave); max-width: 70ch; margin: 0 0 .95rem; }
.cajon p:last-child { margin-bottom: 0; }
.cajon strong { color: var(--tinta); font-weight: 600; }

/* Medidas de seguridad: lista de definición con reglas, en el mismo idioma que la
   tabla de roles de más arriba. No una cuadrícula de bloques iguales. */
.medidas { margin: 1.6rem 0 0; display: grid; gap: 0; }
.medidas div { display: grid; grid-template-columns: 15rem minmax(0, 1fr); gap: 2rem;
               padding: .85rem 0; border-top: 1px solid var(--linea); align-items: baseline; }
.medidas div:last-child { border-bottom: 1px solid var(--linea); }
.medidas dt { font-size: .97rem; font-weight: 600; margin: 0; line-height: 1.45; }
.medidas dd { font-size: .94rem; line-height: 1.62; color: var(--tinta-suave);
              margin: 0; max-width: 64ch; }

/* Las cuatro etapas sí son una secuencia: el orden es la información */
.flujo { display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); margin-top: 1.7rem; }
.paso { border-top: 1px solid var(--linea); padding: .6rem 1.1rem .45rem 0; transition: border-color .2s; }
.paso:first-child { border-top-color: var(--carro); }
.paso:hover { border-top-color: var(--grafito); }
.paso b { display: block; font-size: .92rem; margin-bottom: .24rem; }
.paso b::before { content: attr(data-etapa) " · "; color: var(--acero); font-weight: 400;
                  font-family: var(--mono); font-variant-numeric: tabular-nums; }
.paso span { font-size: .84rem; color: var(--tinta-suave); line-height: 1.55; display: block; }

.roles { width: 100%; border-collapse: collapse; margin-top: 1.3rem; font-size: .9rem; }
.roles th, .roles td { border-left: 0; border-right: 0; border-top: 0; }
.roles th { text-align: left; font-weight: 600; font-size: .81rem; color: var(--tinta-suave);
            border-bottom: 1px solid var(--tinta); padding: 0 .8rem .42rem 0; }
.roles td { padding: .56rem .8rem .56rem 0; border-bottom: 1px solid var(--linea);
            vertical-align: top; color: var(--tinta-suave); }
.roles tr { transition: background .15s; }
.roles tbody tr:hover { background: var(--papel-hundido); }
.roles td:first-child { color: var(--tinta); font-weight: 500; white-space: nowrap; }
.roles td.factor { white-space: nowrap; font-size: .86rem; }
.roles td.factor.obligatorio { color: var(--carro); font-weight: 500; }

/* ---------- Cierre y pie ---------- */
.cierre { padding: clamp(3rem, 7vw, 4.5rem) 0 clamp(2rem, 4vw, 3rem); }
.cierre h2 { font-size: clamp(1.7rem, 3.6vw, 2.6rem); line-height: 1.12; letter-spacing: -.03em;
             margin: 0 0 .8rem; max-width: 20ch; }
.cierre p { font-size: 1rem; color: var(--tinta-suave); max-width: 52ch; line-height: 1.7; margin: 0; }

.pie { border-top: 2px solid var(--tinta); padding: 1.7rem 0 2.6rem; }
.pie-fila { display: flex; flex-wrap: wrap; gap: 1.6rem; justify-content: space-between; align-items: flex-start; }
.pie p { font-size: .82rem; color: var(--tinta-suave); line-height: 1.6; margin: 0; max-width: 54ch; }
.pie-marca { color: var(--tinta) !important; margin-bottom: .3rem !important; }
.pie .dato { font-family: var(--mono); }

/* ---------- Pantalla de acceso ---------- */
.acceso-marco { max-width: 430px; margin: 0 auto; padding: clamp(2rem, 7vw, 4rem) 0 0; }
.acceso-marco h1 { font-size: 1.95rem; letter-spacing: -.03em; margin: 0 0 .3rem; }
.acceso-marco .sub { color: var(--tinta-suave); font-size: .93rem; margin-bottom: 1.6rem; }
.regla-acceso { height: 2px; background: var(--carro); transform-origin: left;
                animation: barrido .5s cubic-bezier(.22,.61,.36,1) backwards; margin-bottom: 1.5rem; }
.nota-acceso { font-size: .8rem; color: var(--tinta-suave); line-height: 1.55; }

/* Acceso con Microsoft: el cuadro de cuatro colores es su marca registrada, y el
   botón sigue sus normas de identidad (fondo blanco, borde gris, texto oscuro). */
.boton-ms {
  display: flex; align-items: center; justify-content: center; gap: .6rem;
  background: #fff; border: 1px solid #8C8C8C; color: #5E5E5E !important;
  font-size: .92rem; font-weight: 600; text-decoration: none !important;
  padding: .62rem 1rem; margin-bottom: 1.1rem; transition: background .15s, border-color .15s;
}
.boton-ms:hover { background: #F3F3F3; border-color: #5E5E5E; }
.ms-cuadros { display: grid; grid-template-columns: 9px 9px; gap: 2px; }
.ms-cuadros i { width: 9px; height: 9px; display: block; }
.ms-cuadros i:nth-child(1) { background: #F25022; }
.ms-cuadros i:nth-child(2) { background: #7FBA00; }
.ms-cuadros i:nth-child(3) { background: #00A4EF; }
.ms-cuadros i:nth-child(4) { background: #FFB900; }

.separador { display: flex; align-items: center; gap: .8rem; margin: 0 0 1.1rem;
             font-size: .78rem; color: var(--acero); }
.separador::before, .separador::after {
  content: ""; flex: 1; height: 1px; background: var(--linea);
}

@media (max-width: 820px) {
  .nav { display: none; }
  .cajon { padding-left: 1.1rem; }
  .medidas div { grid-template-columns: 1fr; gap: .2rem; }
}

/* En pantalla estrecha, tres columnas dejan una palabra por línea. La tabla se
   reordena en fichas: el rol como título y los otros dos campos rotulados debajo. */
@media (max-width: 680px) {
  .roles, .roles tbody, .roles tr, .roles td { display: block; width: 100%; }
  .roles thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .roles tr { padding: .85rem 0; border-bottom: 1px solid var(--linea); }
  .roles td { border: 0; padding: 0; }
  .roles td:first-child { font-size: 1rem; margin-bottom: .3rem; white-space: normal; }
  .roles td:not(:first-child)::before {
    content: attr(data-campo); display: block; font-size: .73rem; color: var(--acero);
    letter-spacing: .04em; margin-top: .45rem;
  }
  .roles td.factor { font-size: .9rem; }
}
"""

ECG = """
<figure class="monitor">
<svg viewBox="0 0 1200 92" preserveAspectRatio="none" role="img"
     aria-label="Trazado de monitor cardiaco: ritmo normal, una arritmia y recuperación tras la reanimación">
<path d="M0 62 L60 62 L70 62 L76 44 L82 76 L88 62 L100 62 L160 62 L170 62 L176 44 L182 76 L188 62 L200 62
         L260 62 L270 62 L276 44 L282 76 L288 62 L300 62
         L330 62 L338 32 L346 80 L354 36 L362 74 L370 28 L378 82 L386 40 L394 72 L402 32 L410 76 L418 46 L430 62
         L470 62 L500 62 L520 16 L534 62 L560 62
         L640 62 L650 62 L656 46 L662 74 L668 62 L690 62
         L760 62 L770 62 L776 44 L782 76 L788 62 L810 62
         L880 62 L890 62 L896 44 L902 76 L908 62 L930 62
         L1000 62 L1010 62 L1016 44 L1022 76 L1028 62 L1050 62
         L1120 62 L1130 62 L1136 44 L1142 76 L1148 62 L1200 62"/>
</svg>
<figcaption>Ritmo estable, fibrilación ventricular, desfibrilación y ritmo recuperado</figcaption>
</figure>
"""


# ===========================================================================
def mostrar():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)

    if _procesar_retorno_microsoft():
        return
    if st.session_state.get("pagina_legal"):
        legal.mostrar_documento(st.session_state["pagina_legal"])
        return
    if st.session_state.get("pantalla") == "acceso" or st.session_state.get("mfa_pendiente"):
        _pantalla_acceso()
        return
    if st.session_state.get("pantalla") == "registro":
        from app.vistas import registro
        registro.mostrar()
        return
    if st.session_state.get("pantalla") == "recuperar":
        from app.vistas import recuperar
        recuperar.mostrar()
        return

    _barra()
    _hero()
    _cajones()
    _cierre()
    _pie()


def _barra():
    izq, der = st.columns([5.4, 1], vertical_alignment="center")
    with izq:
        st.markdown("""
        <div class="barra">
          <div class="marca"><b>SMARTDATA&nbsp;360</b><span>carro de paro</span></div>
          <nav class="nav">
            <a href="#el-problema">El problema</a>
            <a href="#como-funciona">Cómo funciona</a>
            <a href="#el-asistente">Asistente</a>
            <a href="#seguridad">Seguridad</a>
          </nav>
        </div>
        """, unsafe_allow_html=True)
    with der:
        if st.button("Acceder", type="primary", width="stretch"):
            st.session_state["pantalla"] = "acceso"
            st.rerun()


def _hero():
    st.markdown(f"""
    <div class="hero">
      <h1 class="entra d1">El carro de paro, revisado <em>antes</em> de que suene la alarma.</h1>
      <p class="entrada entra d2">Control de los medicamentos de reanimación de un hospital: qué hay en
      cada carro, cuándo vence y cuánto se consume. Sobre los <var>12</var> carros de seis servicios y
      <var>422.204</var> registros de histórico, el sistema calcula la demanda de los próximos
      <var>14</var> días y avisa qué carro va a quedar incompleto antes de que haga falta.</p>
    </div>
    <div class="entra d3">{ECG}</div>
    """, unsafe_allow_html=True)


def _cajones():
    st.markdown("""
    <div class="cajones">

      <section class="cajon" id="el-problema">
        <h2>Un carro incompleto no avisa hasta que se necesita</h2>
        <p>Durante un paro cardiorrespiratorio la probabilidad de supervivencia disminuye de forma
        acelerada con cada minuto que pasa sin desfibrilación y sin los medicamentos indicados; es el
        principio en que se basan las guías de reanimación cardiopulmonar. El tiempo que se pierde
        buscando una ampolla que faltaba, o descubriendo que la adrenalina venció, es tiempo que no
        se recupera.</p>
        <p>La revisión de los carros suele hacerse en papel, turno a turno. Cuando se hace bien deja
        constancia, pero <strong>no anticipa nada</strong>: no dice qué carro va a quedar incompleto la
        próxima semana ni dónde se están perdiendo medicamentos por vencimiento.</p>
      </section>

      <section class="cajon" id="como-funciona">
        <h2>Del registro diario a la decisión de reposición</h2>
        <p>El sistema integra el inventario en tiempo real con cinco años de histórico y con el
        catálogo público de medicamentos, procesa todo con PySpark y devuelve el resultado a la
        operación en forma de alertas concretas.</p>
        <div class="flujo">
          <div class="paso"><b data-etapa="1">Fuentes</b><span>Inventario operativo, histórico de revisiones y consumos, datos abiertos del CUM</span></div>
          <div class="paso"><b data-etapa="2">Procesamiento</b><span>Limpieza medida e integración por capas sobre el data lake</span></div>
          <div class="paso"><b data-etapa="3">Analítica</b><span>Demanda prevista a 14 días, consumos anómalos y matriz de riesgo</span></div>
          <div class="paso"><b data-etapa="4">Decisión</b><span>Alertas en la operación y recomendaciones del asistente</span></div>
        </div>
      </section>

      <section class="cajon" id="el-asistente">
        <h2>Pregunta en español; actúa con las reglas del sistema</h2>
        <p>El asistente no consulta la base de datos por su cuenta: solo puede usar las herramientas
        que el sistema le expone, y cada una exige el mismo permiso que exigiría a una persona. Un
        médico y un regente de farmacia obtienen respuestas distintas porque tienen permisos
        distintos.</p>
        <p>Está disponible desde cualquier pantalla, sin cambiar de sección. Además de responder, hace
        una <strong>revisión autónoma</strong>: recorre los doce carros, prioriza lo que encuentra y
        registra recomendaciones para el equipo. Cada consulta y cada acción quedan en el registro de
        auditoría.</p>
      </section>

      <section class="cajon" id="quien-entra">
        <h2>Nueve roles, dieciocho permisos</h2>
        <p>Los permisos se validan en la capa de servicios, no en la pantalla: la aplicación web, la
        API y el asistente comparten exactamente las mismas reglas, de modo que ninguna vía puede
        saltarse una restricción.</p>
        <table class="roles">
          <thead><tr><th>Rol</th><th>Qué puede hacer</th><th>Segundo factor</th></tr></thead>
          <tbody>
          <tr><td>Médico</td><td data-campo="Qué puede hacer">Consultar el carro y registrar el uso en código azul</td><td data-campo="Segundo factor" class="factor">opcional</td></tr>
          <tr><td>Enfermero(a)</td><td data-campo="Qué puede hacer">Revisión por turno, registro de lotes, lectura OCR y atención de alertas</td><td data-campo="Segundo factor" class="factor">opcional</td></tr>
          <tr><td>Regente de farmacia</td><td data-campo="Qué puede hacer">Catálogo, bajas por vencimiento y tablero analítico</td><td data-campo="Segundo factor" class="factor obligatorio">obligatorio</td></tr>
          <tr><td>Dirección médica</td><td data-campo="Qué puede hacer">Tablero ejecutivo y recomendaciones del asistente</td><td data-campo="Segundo factor" class="factor">opcional</td></tr>
          <tr><td>Analista de datos</td><td data-campo="Qué puede hacer">Ejecución del procesamiento y de los modelos</td><td data-campo="Segundo factor" class="factor">opcional</td></tr>
          <tr><td>Auditor</td><td data-campo="Qué puede hacer">Solo lectura, incluida la trazabilidad completa</td><td data-campo="Segundo factor" class="factor">opcional</td></tr>
          <tr><td>Oficial de seguridad</td><td data-campo="Qué puede hacer">Eventos de acceso, bloqueos y cumplimiento</td><td data-campo="Segundo factor" class="factor obligatorio">obligatorio</td></tr>
          <tr><td>Soporte TI y administrador</td><td data-campo="Qué puede hacer">Cuentas, desbloqueos y configuración</td><td data-campo="Segundo factor" class="factor obligatorio">obligatorio</td></tr>
          </tbody>
        </table>
      </section>

      <section class="cajon" id="seguridad">
        <h2>Lo que protege cada acceso</h2>
        <dl class="medidas">
          <div><dt>Contraseñas con bcrypt</dt><dd>Nunca se guardan ni se transmiten en claro. Política de diez caracteres con mayúscula, número y símbolo.</dd></div>
          <div><dt>Verificación en dos pasos</dt><dd>Código temporal de la aplicación de autenticación, con códigos de respaldo de un solo uso.</dd></div>
          <div><dt>Bloqueo por intentos</dt><dd>Cinco intentos fallidos bloquean la cuenta quince minutos y dejan registro del evento.</dd></div>
          <div><dt>Trazabilidad</dt><dd>Cada acción queda con usuario, fecha y origen. Los lotes no se borran: se dan de baja con motivo.</dd></div>
        </dl>
      </section>

    </div>
    """, unsafe_allow_html=True)


def _cierre():
    izq, der = st.columns([1.6, 1], vertical_alignment="center")
    with izq:
        st.markdown("""
        <div class="cierre">
          <h2>Entre al sistema con su cuenta institucional</h2>
          <p>El acceso está restringido al personal autorizado. Si no recuerda su contraseña y tiene
          activa la verificación en dos pasos, puede restablecerla usted mismo desde la pantalla de
          acceso.</p>
        </div>
        """, unsafe_allow_html=True)
    with der:
        st.write("")
        if st.button("Ir al acceso", type="primary", width="stretch", key="cierre_acceso"):
            st.session_state["pantalla"] = "acceso"
            st.rerun()


def _pie():
    st.markdown(f"""
    <div class="pie">
      <div class="pie-fila">
        <div>
          <p class="pie-marca"><b>SMARTDATA 360</b> · Módulo Carro de Paro</p>
          <p>Sistema de control de medicamentos de reanimación. El catálogo de referencia se
          sincroniza con los datos abiertos del Estado colombiano.</p>
        </div>
        <p class="dato">Políticas v{VERSION_POLITICAS}</p>
      </div>
    </div>
    """, unsafe_allow_html=True)
    _enlaces_legales(horizontal=True)


def _enlaces_legales(horizontal: bool = False):
    columnas = st.columns(4) if horizontal else [st]
    for i, (clave, etiqueta) in enumerate(legal.DOCUMENTOS.items()):
        destino = columnas[i] if horizontal else st
        if destino.button(etiqueta, key=f"legal_{clave}", width="stretch"):
            st.session_state["pagina_legal"] = clave
            st.rerun()


# ===========================================================================
# Acceso
# ===========================================================================
def _pantalla_acceso():
    _, centro, _ = st.columns([1, 1.25, 1])
    with centro:
        st.markdown('<div class="acceso-marco">', unsafe_allow_html=True)
        if st.session_state.get("mfa_pendiente"):
            _formulario_segundo_factor()
        else:
            _formulario_credenciales()
        st.markdown("</div>", unsafe_allow_html=True)


def _formulario_credenciales():
    st.markdown('<h1>Acceso</h1><p class="sub">Personal autorizado de la institución.</p>'
                '<div class="regla-acceso"></div>', unsafe_allow_html=True)

    if "motivo_salida" in st.session_state:
        st.info(st.session_state.pop("motivo_salida"))
    if "mensaje_acceso" in st.session_state:
        st.success(st.session_state.pop("mensaje_acceso"))

    from src.database.connection import base_disponible
    if not base_disponible():
        st.error("Sin conexión con la base de datos. Revise el archivo .env y que MySQL esté activo.")
        return

    _boton_microsoft()

    with st.form("acceso", border=False):
        correo = st.text_input("Correo institucional", placeholder="usuario@hospital.com", max_chars=254,
                               help="Solo letras, números y los símbolos . _ % + - @")
        password = st.text_input("Contraseña", type="password")
        acepta = st.checkbox(TEXTO_ACEPTACION)
        entrar = st.form_submit_button("Ingresar", type="primary", width="stretch")
    solo_caracteres_de_correo("Correo institucional")      # no deja escribir ni pegar otros caracteres

    if entrar:
        if not acepta:
            st.warning("Debe aceptar los términos y el aviso de tratamiento de datos para continuar.")
        else:
            st.session_state["acepto_en_login"] = True
            r = autenticar(correo, password)
            if r.ok:
                _iniciar(r.usuario)
            elif r.requiere_mfa:
                st.session_state["mfa_pendiente"] = r.usuario     # todavía NO es una sesión válida
                st.session_state["mfa_canal"] = r.canal_mfa
                st.session_state.pop("mfa_correo_pedido", None)
                st.rerun()
            else:
                st.error(r.mensaje)
                if r.intentos_restantes is not None and r.intentos_restantes <= 2:
                    st.warning(f"Intentos restantes antes del bloqueo temporal: {r.intentos_restantes}")

    izq, der = st.columns(2)
    if izq.button("Olvidé mi contraseña", width="stretch"):
        st.session_state["pantalla"] = "recuperar"
        st.rerun()
    if der.button("Volver al inicio", width="stretch"):
        st.session_state.pop("pantalla", None)
        st.rerun()

    if config.REGISTRO_ABIERTO:
        st.markdown('<div class="separador"><span>¿aún no tiene cuenta?</span></div>',
                    unsafe_allow_html=True)
        if st.button("Crear una cuenta", width="stretch", key="ir_registro"):
            st.session_state["pantalla"] = "registro"
            st.rerun()
    st.markdown('<p class="nota-acceso">El acceso queda registrado. Tras cinco intentos fallidos la '
                'cuenta se bloquea 15 minutos.</p>', unsafe_allow_html=True)


def _boton_microsoft():
    """Acceso con la cuenta institucional de Microsoft. Solo aparece si está configurado."""
    from src.seguridad import microsoft
    if not microsoft.configurado():
        return
    if "sso_ms" not in st.session_state:
        st.session_state["sso_ms"] = microsoft.preparar()
    destino = microsoft.url_de_ingreso(st.session_state["sso_ms"])
    st.markdown(
        f'<a class="boton-ms" href="{destino}" target="_self">'
        f'<span class="ms-cuadros"><i></i><i></i><i></i><i></i></span>'
        f'Continuar con Microsoft</a>'
        f'<div class="separador"><span>o con su contraseña</span></div>',
        unsafe_allow_html=True)


def _procesar_retorno_microsoft() -> bool:
    """Si Microsoft devolvió un código en la URL, lo canjea e inicia la sesión.

    Devuelve True si manejó el retorno (con éxito o con error), para que la
    portada no siga dibujándose por debajo.
    """
    from src.seguridad import microsoft
    parametros = st.query_params
    if "code" not in parametros and "error" not in parametros:
        return False

    if "error" in parametros:
        descripcion = parametros.get("error_description", parametros.get("error", ""))
        st.query_params.clear()
        st.session_state["pantalla"] = "acceso"
        st.error(f"Microsoft no autorizó el ingreso: {descripcion[:200]}")
        return True

    preparacion = st.session_state.get("sso_ms") or {}
    codigo, estado = parametros.get("code", ""), parametros.get("state", "")
    st.query_params.clear()

    if not preparacion or estado != preparacion.get("state"):
        # El state no coincide: o la sesión caducó, o alguien fabricó el retorno
        st.session_state["pantalla"] = "acceso"
        st.error("La solicitud de ingreso no es válida o caducó. Inténtelo de nuevo.")
        return True

    try:
        identidad = microsoft.canjear_codigo(codigo, preparacion["verificador"])
        usuario, aviso = microsoft.resolver_usuario(identidad)
    except Exception as e:                                    # noqa: BLE001
        st.session_state["pantalla"] = "acceso"
        st.error(f"No fue posible completar el ingreso con Microsoft: {e}")
        return True
    finally:
        st.session_state.pop("sso_ms", None)

    if not usuario:
        st.session_state["pantalla"] = "acceso"
        st.warning(aviso)
        return True

    st.session_state["acepto_en_login"] = True    # el consentimiento se registra igual que en el acceso normal
    # Microsoft comprobó quién es, pero el segundo factor de ESTE sistema se exige igual que
    # en el acceso con contraseña: si no, entrar por SSO sería una forma de saltárselo.
    canal = canal_mfa(usuario["id"])
    if canal:
        st.session_state["mfa_pendiente"] = usuario     # todavía NO es una sesión válida
        st.session_state["mfa_canal"] = canal
        st.session_state.pop("mfa_correo_pedido", None)
        st.session_state["pantalla"] = "acceso"
        st.rerun()
    _iniciar(usuario)
    return True


def _formulario_segundo_factor():
    from datetime import datetime

    from src.seguridad.mfa import pendiente_vencido
    desde = st.session_state.setdefault("mfa_pendiente_desde", datetime.now())
    if pendiente_vencido(desde):
        for clave in ("mfa_pendiente", "mfa_canal", "mfa_correo_pedido", "mfa_pendiente_desde"):
            st.session_state.pop(clave, None)
        st.session_state["mensaje_acceso"] = "La verificación expiró por inactividad. Inicie sesión de nuevo."
        st.rerun()
    pendiente = st.session_state["mfa_pendiente"]
    canal = st.session_state.get("mfa_canal", "app")
    st.markdown(f'<h1>Verificación</h1><p class="sub">Cuenta: {pendiente["correo"]}</p>'
                '<div class="regla-acceso"></div>', unsafe_allow_html=True)

    # Si el único canal es el correo, el código se pide solo al llegar aquí
    if canal == "correo" and not st.session_state.get("mfa_correo_pedido"):
        from src.seguridad.mfa_correo import enviar_codigo
        ok, aviso = enviar_codigo(pendiente["id"])
        st.session_state["mfa_correo_pedido"] = True
        (st.success if ok else st.error)(aviso)

    ayudas = {"app": "De su aplicación de autenticación. También sirve un código de respaldo.",
              "correo": "El código de seis dígitos que le llegó al correo institucional.",
              "ambos": "De su aplicación de autenticación, un código de respaldo, "
                       "o el que pida por correo."}
    with st.form("mfa", border=False):
        codigo = st.text_input("Código de 6 dígitos", max_chars=9, help=ayudas.get(canal, ayudas["app"]))
        verificar = st.form_submit_button("Verificar", type="primary", width="stretch")
    if verificar:
        r = completar_login_mfa(pendiente["id"], codigo)
        if r.ok:
            _iniciar(r.usuario)
        else:
            st.error(r.mensaje)
            if r.intentos_restantes is not None and r.intentos_restantes <= 2:
                st.warning(f"Intentos restantes antes del bloqueo temporal: {r.intentos_restantes}")
            if not r.requiere_mfa:
                st.session_state.pop("mfa_pendiente", None)

    if canal in ("correo", "ambos"):
        etiqueta = "Reenviar el código al correo" if canal == "correo" else "Enviarme el código al correo"
        if st.button(etiqueta, width="stretch"):
            from src.seguridad.mfa_correo import enviar_codigo
            ok, aviso = enviar_codigo(pendiente["id"])
            (st.success if ok else st.warning)(aviso)

    if st.button("Volver", width="stretch"):
        for clave in ("mfa_pendiente", "mfa_canal", "mfa_correo_pedido", "mfa_pendiente_desde"):
            st.session_state.pop(clave, None)
        st.rerun()


def _iniciar(usuario: dict):
    for clave in ("mfa_canal", "mfa_correo_pedido", "mfa_pendiente_desde"):
        st.session_state.pop(clave, None)
    if st.session_state.pop("acepto_en_login", False):
        registrar_aceptacion(usuario["id"], origen="WEB")
    sesion.iniciar_sesion(usuario)
    recalcular_estados()      # mantiene estados y alertas al día con la fecha actual
    st.rerun()
