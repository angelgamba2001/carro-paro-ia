/*
  Cliente de la API REST del Carro de Paro.

  Toda la app pasa por aquí: una sola pieza que sabe dónde está el servidor, cómo
  se guarda el token y qué hacer cuando caduca. Si mañana cambia la dirección del
  backend, se cambia en un sitio.

  Sobre dónde se guarda el token: en localStorage. Es lo que permite Cordova sin
  plugins adicionales, y en un dispositivo con bloqueo de pantalla es aceptable
  para un token que caduca en 30 minutos. Para producción real conviene
  cordova-plugin-secure-storage, que lo guarda en el llavero del sistema.
*/
const API = (() => {
  'use strict';

  // ------------------------------------------------------------------
  // Dirección del servidor. Ver movil/README.md: el teléfono NO alcanza el
  // localhost del computador; hay que poner la IP de red o usar adb reverse.
  // ------------------------------------------------------------------
  // Semgrep url-de-api-fija-en-codigo: una IP fija obliga a recompilar para cambiar
  // de servidor. Si la app se sirve por http(s) tomamos el propio origen; en el
  // WebView de Cordova (file://) no hay origen util y la direccion se indica en la
  // pantalla de ajustes, que ya existe y la guarda en LLAVE_URL.
  const POR_DEFECTO = /^https?:$/.test(location.protocol) ? location.origin : '';

  const LLAVE_URL = 'cp_api_url';
  const LLAVE_TOKEN = 'cp_token';
  const LLAVE_USUARIO = 'cp_usuario';
  const LLAVE_PERMISOS = 'cp_permisos';

  function leer(llave, defecto = null) {
    try { return localStorage.getItem(llave) ?? defecto; } catch (e) { return defecto; }
  }
  function escribir(llave, valor) {
    try { valor === null ? localStorage.removeItem(llave) : localStorage.setItem(llave, valor); }
    catch (e) { /* modo privado: la sesión durará lo que dure la app abierta */ }
  }

  const base = () => (leer(LLAVE_URL, POR_DEFECTO) || POR_DEFECTO).replace(/\/+$/, '');
  const token = () => leer(LLAVE_TOKEN);

  function usuario() {
    try { return JSON.parse(leer(LLAVE_USUARIO, 'null')); } catch (e) { return null; }
  }
  function permisos() {
    try { return JSON.parse(leer(LLAVE_PERMISOS, '[]')) || []; } catch (e) { return []; }
  }
  const puede = (permiso) => permisos().includes(permiso);

  function guardarSesion(datos) {
    escribir(LLAVE_TOKEN, datos.access_token);
    escribir(LLAVE_USUARIO, JSON.stringify(datos.usuario || {}));
  }

  function cerrarSesion(motivo) {
    [LLAVE_TOKEN, LLAVE_USUARIO, LLAVE_PERMISOS].forEach((k) => escribir(k, null));
    const destino = 'index.html' + (motivo ? '?motivo=' + encodeURIComponent(motivo) : '');
    if (!location.pathname.endsWith('index.html')) location.replace(destino);
  }

  // ------------------------------------------------------------------
  // Petición base
  // ------------------------------------------------------------------
  async function pedir(ruta, opciones = {}) {
    const cabeceras = Object.assign({ 'Content-Type': 'application/json' }, opciones.headers || {});
    if (opciones.token !== false && token()) cabeceras.Authorization = 'Bearer ' + token();

    let respuesta;
    try {
      const control = new AbortController();
      const corte = setTimeout(() => control.abort(), opciones.timeout || 20000);
      respuesta = await fetch(base() + ruta, {
        method: opciones.method || 'GET',
        headers: cabeceras,
        body: opciones.body ? JSON.stringify(opciones.body) : undefined,
        signal: control.signal,
      });
      clearTimeout(corte);
    } catch (e) {
      // Distinguir "no hay red" de "el servidor respondió mal" evita que la gente
      // crea que sus credenciales están mal cuando lo que falta es conexión.
      const err = new Error(e.name === 'AbortError'
        ? 'El servidor tardó demasiado en responder.'
        : 'No se pudo conectar con el servidor. Revise la red y la dirección configurada.');
      err.sinRed = true;
      throw err;
    }

    if (respuesta.status === 401 && opciones.token !== false) {
      cerrarSesion('Su sesión expiró. Vuelva a ingresar.');
      throw new Error('Sesión expirada');
    }

    let cuerpo = null;
    try { cuerpo = await respuesta.json(); } catch (e) { /* 204 o cuerpo vacío */ }

    if (!respuesta.ok) {
      const err = new Error((cuerpo && (cuerpo.detail || cuerpo.mensaje)) || 'No se pudo completar la operación.');
      err.estado = respuesta.status;
      throw err;
    }
    return cuerpo;
  }

  // ------------------------------------------------------------------
  // Operaciones
  // ------------------------------------------------------------------
  return {
    // --- configuración ---
    urlBase: base,
    fijarUrl: (u) => escribir(LLAVE_URL, (u || '').trim().replace(/\/+$/, '') || null),
    hayToken: () => Boolean(token()),
    usuario, permisos, puede, cerrarSesion,

    salud: () => pedir('/api/salud', { token: false, timeout: 8000 }),

    // --- acceso ---
    async login(correo, password) {
      const r = await pedir('/api/auth/login', {
        method: 'POST', token: false, body: { correo, password },
      });
      if (r.mfa_requerido) {
        escribir(LLAVE_TOKEN, r.token_temporal);   // solo sirve para /api/auth/mfa
        return { mfa: true, mensaje: r.mensaje };
      }
      guardarSesion(r);
      await this.cargarPermisos();
      return { mfa: false, debeCambiar: r.debe_cambiar_password };
    },

    async verificarMfa(codigo) {
      const r = await pedir('/api/auth/mfa', { method: 'POST', body: { codigo } });
      guardarSesion(r);
      await this.cargarPermisos();
      return { debeCambiar: r.debe_cambiar_password };
    },

    async cargarPermisos() {
      const yo = await pedir('/api/auth/yo');
      escribir(LLAVE_PERMISOS, JSON.stringify(yo.permisos || []));
      escribir(LLAVE_USUARIO, JSON.stringify({ id: yo.id, nombre: yo.nombre, rol: yo.rol }));
      return yo;
    },

    // --- inventario ---
    carros: () => pedir('/api/carros'),
    inventario: (filtros = {}) => {
      const q = new URLSearchParams();
      if (filtros.carro_id) q.set('carro_id', filtros.carro_id);
      if (filtros.estado) q.set('estado', filtros.estado);
      const cola = q.toString();
      return pedir('/api/inventario' + (cola ? '?' + cola : ''));
    },
    stock: () => pedir('/api/inventario/stock'),
    registrarConsumo: (invId, cantidad, motivo) =>
      pedir(`/api/inventario/${invId}/consumo`, { method: 'POST', body: { cantidad, motivo } }),

    // --- alertas ---
    alertas: (pendientes = true) => pedir('/api/alertas?pendientes=' + (pendientes ? 'true' : 'false')),
    atenderAlerta: (id, nota) => pedir(`/api/alertas/${id}/atender`, { method: 'POST', body: { nota } }),

    // --- analítica ---
    kpis: () => pedir('/api/analitica/kpis'),
    predicciones: (soloRiesgo = true) =>
      pedir('/api/analitica/predicciones?solo_riesgo=' + (soloRiesgo ? 'true' : 'false')),

    // --- agente ---
    preguntarAgente: (pregunta) =>
      pedir('/api/agente/consulta', { method: 'POST', body: { pregunta }, timeout: 120000 }),
  };
})();


/* ---------------------------------------------------------------------
   Utilidades compartidas por las pantallas
   --------------------------------------------------------------------- */
const UI = {
  /** Formato colombiano: coma decimal y punto de miles, igual que en la web. */
  numero(valor, decimales = 0) {
    if (valor === null || valor === undefined || valor === '') return '—';
    const n = Number(valor);
    if (Number.isNaN(n)) return String(valor);
    return n.toLocaleString('es-CO', {
      minimumFractionDigits: decimales, maximumFractionDigits: decimales,
    });
  },

  moneda(valor) {
    if (valor === null || valor === undefined) return '—';
    const n = Number(valor);
    if (Number.isNaN(n)) return String(valor);
    if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toLocaleString('es-CO', { maximumFractionDigits: 1 }) + ' M';
    if (Math.abs(n) >= 1e3) return '$' + (n / 1e3).toLocaleString('es-CO', { maximumFractionDigits: 0 }) + ' mil';
    return '$' + UI.numero(n);
  },

  fecha(valor) {
    if (!valor) return '—';
    const d = new Date(valor);
    if (Number.isNaN(d.getTime())) return String(valor);
    return d.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
  },

  /** Escapa lo que venga del servidor antes de inyectarlo como HTML. */
  limpio(texto) {
    const d = document.createElement('div');
    d.textContent = texto === null || texto === undefined ? '' : String(texto);
    return d.innerHTML;
  },

  aviso(contenedor, mensaje, tipo = 'error') {
    const el = typeof contenedor === 'string' ? document.getElementById(contenedor) : contenedor;
    if (!el) return;
    el.innerHTML = `<div class="aviso ${tipo}">${UI.limpio(mensaje)}</div>`;
  },

  cargando(contenedor, texto = 'Consultando…') {
    const el = typeof contenedor === 'string' ? document.getElementById(contenedor) : contenedor;
    if (el) el.innerHTML = `<div class="cargando">${UI.limpio(texto)}</div>`;
  },

  vacio(contenedor, texto) {
    const el = typeof contenedor === 'string' ? document.getElementById(contenedor) : contenedor;
    if (el) el.innerHTML = `<div class="vacio">${UI.limpio(texto)}</div>`;
  },

  /** Exige sesión. Devuelve false si no la hay (y ya redirigió). */
  exigirSesion() {
    if (!API.hayToken()) { location.replace('index.html'); return false; }
    return true;
  },

  /** Barra inferior: solo los destinos que el rol tiene permitidos. */
  navegacion(actual) {
    const iconos = {
      tablero: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 9h8V3h-8z"/>',
      inventario: '<path d="M4 7h16M4 12h16M4 17h16"/>',
      alertas: '<path d="M12 3a6 6 0 0 0-6 6c0 5-2 6-2 6h16s-2-1-2-6a6 6 0 0 0-6-6zM10.5 20a1.8 1.8 0 0 0 3 0"/>',
      agente: '<path d="M21 12a8 8 0 1 1-3.2-6.4M21 4v5h-5"/>',
      perfil: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/>',
    };
    const destinos = [
      { id: 'tablero', archivo: 'tablero.html', etiqueta: 'Tablero', permiso: 'dashboard.operativo' },
      { id: 'inventario', archivo: 'inventario.html', etiqueta: 'Inventario', permiso: 'inventario.ver' },
      { id: 'alertas', archivo: 'alertas.html', etiqueta: 'Alertas', permiso: 'alertas.ver' },
      { id: 'agente', archivo: 'agente.html', etiqueta: 'Asistente', permiso: 'agente.usar' },
      { id: 'perfil', archivo: 'perfil.html', etiqueta: 'Mi cuenta', permiso: null },
    ];
    const html = destinos
      .filter((d) => d.permiso === null || API.puede(d.permiso))
      .map((d) => `<a href="${d.archivo}" class="${d.id === actual ? 'activo' : ''}">
           <svg viewBox="0 0 24 24">${iconos[d.id]}</svg><span>${d.etiqueta}</span></a>`)
      .join('');
    const barra = document.getElementById('navegacion');
    if (barra) barra.innerHTML = html;
  },

  /** Cabecera con el nombre de quien está usando la app. */
  cabecera(titulo, subtitulo) {
    const u = API.usuario() || {};
    const el = document.getElementById('cabecera');
    if (el) {
      el.innerHTML = `<h1>${UI.limpio(titulo)}</h1>
        <span class="sub">${UI.limpio(subtitulo || u.nombre || '')}</span>`;
    }
  },
};
