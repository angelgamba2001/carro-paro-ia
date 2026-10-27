"""
Filtros de entrada que corren en el navegador (Streamlit no los trae de fábrica).

* solo_caracteres_de_correo: el campo de usuario del acceso no deja ESCRIBIR, PEGAR ni
  soltar nada que no sea letra, número o . _ % + - @. Es una ayuda de interfaz: la
  barrera real sigue siendo la validación del servidor (autenticar y la API).
* La mirilla que muestra la contraseña se quita por CSS (ver componentes.OCULTAR_MIRILLA):
  un campo de contraseña nunca debe poder copiarse.
"""
import json

import streamlit.components.v1 as components


def solo_caracteres_de_correo(etiqueta: str = "Correo institucional", maximo: int = 254):
    script = """
<script>
(function () {
  var ETQ = %s, MAX = %d, OK = /^[A-Za-z0-9._%%+\\-@]$/;
  var pw; try { pw = window.parent; pw.document.body; } catch (e) { return; }
  var doc = pw.document;
  function limpiar(t) { return Array.from(t || '').filter(function (c) { return OK.test(c); }).join('').slice(0, MAX); }
  function fijar(el, v) {
    Object.getOwnPropertyDescriptor(pw.HTMLInputElement.prototype, 'value').set.call(el, v);
    el.dispatchEvent(new pw.Event('input', { bubbles: true }));
  }
  function enganchar() {
    doc.querySelectorAll('input').forEach(function (el) {
      if (el.getAttribute('aria-label') !== ETQ || el.dataset.soloCorreo) return;
      el.dataset.soloCorreo = '1';
      el.addEventListener('beforeinput', function (e) {            // tecla normal
        if (e.inputType === 'insertText' && e.data && limpiar(e.data) !== e.data) e.preventDefault();
      });
      el.addEventListener('paste', function (e) {                  // pegar: se pega solo lo permitido
        e.preventDefault();
        var t = limpiar((e.clipboardData || pw.clipboardData).getData('text'));
        var a = el.selectionStart, b = el.selectionEnd;
        fijar(el, (el.value.slice(0, a) + t + el.value.slice(b)).slice(0, MAX));
      });
      el.addEventListener('drop', function (e) { e.preventDefault(); });
      el.addEventListener('input', function () {                   // red de seguridad: autocompletar, teclados móviles
        var l = limpiar(el.value); if (l !== el.value) fijar(el, l);
      });
    });
  }
  enganchar();
  if (!pw.__soloCorreoObs) {
    pw.__soloCorreoObs = new pw.MutationObserver(enganchar);
    pw.__soloCorreoObs.observe(doc.body, { childList: true, subtree: true });
  }
})();
</script>""" % (json.dumps(etiqueta), maximo)
    components.html(script, height=0)
