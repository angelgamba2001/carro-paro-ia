# Remediación de hallazgos OWASP ZAP (localhost:8501)

| Hallazgo | Tratamiento |
|---|---|
| CSP no configurada / directivas ausentes | `Content-Security-Policy` en `despliegue/nginx.conf` (incluye `frame-ancestors 'none'`). |
| Falta protección anti-clickjacking | `X-Frame-Options: DENY` + `frame-ancestors`. |
| `X-Content-Type-Options` ausente | `nosniff`. |
| Referrer / Permissions / CORP / COOP | Cabeceras añadidas en el proxy. |
| Fuga de versión del servidor | `server_tokens off`. |
| Timestamp Disclosure (Unix) | Falso positivo: valores numéricos de los recursos estáticos de Streamlit, sin información sensible. |
| Modern Web Application | Informativo (aplicación SPA); sin acción. |

Streamlit no permite fijar cabeceras HTTP, por eso se añade el servicio `proxy` (nginx) en `docker-compose.yml`.
Los escaneos deben apuntar al puerto 8501 del proxy. La CSP usa `unsafe-inline`/`unsafe-eval`
porque el frontend de Streamlit los necesita; debe validarse en el navegador tras desplegar
(`docker compose up -d --build`) y repetir el escaneo.

## Segundo escaneo: alertas de CSP restantes
- La CSP se probó en un navegador real (Chromium) contra Streamlit 1.66 con gráficos Plotly/Vega, tablas y entrada de audio: se retiraron `unsafe-eval`, `ws:`/`wss:` y los orígenes externos de fuentes sin que la interfaz dejara de renderizar.
- **Riesgo aceptado:** `script-src 'unsafe-inline'` y `style-src 'unsafe-inline'`. Streamlit inyecta un script en línea en su `index.html` y su biblioteca de estilos (emotion) genera estilos en línea; quitarlos deja la aplicación en blanco. Sustituirlos por hashes/nonces dependería de la versión exacta de Streamlit y no es mantenible. Mitigación: el resto de la política (`default-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, `form-action 'self'`, `connect-src 'self'`) limita el impacto.
- Divulgación de marcas de tiempo (Unix) en `emotion-styled...js` y `opacities...js`: falso positivo, son constantes numéricas de librerías públicas.
- Aplicación Web Moderna: informativa.
