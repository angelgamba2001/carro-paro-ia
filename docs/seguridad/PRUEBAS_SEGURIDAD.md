# Pruebas de seguridad: guía de ejecución y evidencia

Antes de empezar (una sola vez, tras actualizar el código):

```powershell
docker compose up -d --build        # reconstruye la imagen (nueva dependencia: cryptography)
docker compose logs inicializador   # debe terminar sin errores; aplica scripts/migrar_seguridad.py
```
Sin Docker: `python scripts/migrar_seguridad.py`. Contraseña de las cuentas de demostración: `Carro#Paro2026`.
En modo de correo «archivo» (por defecto) los mensajes y códigos no salen por internet: quedan en
`data/correo_saliente` (`docker compose exec web ls data/correo_saliente`).

| # | Prueba | Cómo hacerla | Resultado esperado | Evidencia |
|---|---|---|---|---|
| 1 | Sesión en otro navegador | Iniciar sesión, copiar la URL y abrirla en otro navegador | Pide iniciar sesión: la URL no lleva la sesión | Captura de la portada de acceso |
| 2 | 15 caracteres especiales | Escribir `!#$%&/()=?¡¿*{}[]` en el usuario | «El correo solo puede llevar letras, números y . _ % + - @»; no se consulta la base | Captura + evento `LOGIN_FALLIDO` |
| 3 | Olvidé mi contraseña | «Restablecer contraseña» con una cuenta con MFA (código de la app/respaldo) y con una sin MFA (código enviado al correo) | Mensaje genérico si el correo no existe; con la cuenta válida pide el código y cambia la contraseña | Eventos `RECUPERACION_*`, correo en `data/correo_saliente` |
| 4 | 5 contraseñas incorrectas | Fallar 5 veces con la misma cuenta | «Cuenta bloqueada por 15 minutos»; aviso por correo | Evento `BLOQUEO` |
| 5 | Rol nuevo, 2 personas, permisos distintos | Usuarios → *Roles personalizados* → crear «Lector» (alertas.ver, inventario.ver) y «Bajas» (inventario.baja, catalogo.gestionar); crear 2 usuarios, uno con cada rol | Cada persona ve solo los módulos de sus permisos (pestaña *Mi cuenta → Mis permisos*) | Auditoría: `CREACION_ROL`, `CREACION_USUARIO` |
| 6 | Correo duplicado | Crear dos usuarios con el mismo correo (también en mayúsculas) | «Ya existe un usuario con ese correo.» (y la columna es UNIQUE) | Captura del mensaje |
| 7 | Contraseña de 1 carácter (admin) | Usuarios → Restablecer contraseña con `a` | Rechazada: mínimo 10 caracteres, mayúscula, minúscula, número y símbolo | Captura |
| 8 | Dos roles a un usuario | Usuarios → *Modificar cuenta* → «Roles adicionales» → elegir 2 → Guardar. Luego cambiar el rol principal y los adicionales | Los permisos son la unión de los roles; al quitarlos desaparecen | Auditoría: `CAMBIO_ROLES_ADICIONALES` con valor anterior y nuevo |
| 9 | Auditoría | Auditoría y seguridad → Log de auditoría | Aparecen creación de usuario, cambios de rol, de permisos, de módulos, restablecimientos y bloqueos, con valor anterior y nuevo | Captura del log |
| 10 | Reducir expiración del token | Como admin: *Auditoría y seguridad → Configuración* → «Expiración del token de la API» de 15 a 2 min (se aplica sin reiniciar); obtener token en `/docs` y esperar 3 min | La API responde 401 «Token inválido o expirado» | Captura de `/docs` y evento `CAMBIO_CONFIGURACION` en el log de auditoría |
| 11 | Aumentar inactividad de sesión | Como admin: *Auditoría y seguridad → Configuración* → «Expiración de la sesión web por inactividad» de 15 a 30 min; dejar la sesión quieta 20 min | La sesión sigue abierta; con el valor anterior (15) ya habría expirado | Evento `CAMBIO_CONFIGURACION` y, al superar el límite, `SESION_EXPIRADA` |
| 12 | Secuencia 1…15 al iniciar sesión | Contraseña `123456789101112131415` | «Correo o contraseña incorrectos.»; cuenta a la que se le cuentan los intentos | Evento `LOGIN_FALLIDO` |
| 13 | Usuario con contraseña 1…15 | Crear usuario con `123456789101112131415` | Rechazada por la política | Captura |
| 14 | Contraseña enmascarada | Escribir `ABC`, intentar copiar y pegar en el Bloc de notas | Se ve `•••`; el navegador no copia el valor | Captura |
| 15 | `.exe` renombrado a `.pdf`/`.png` | Lectura OCR → subir un `.exe` renombrado a `.png` | «El archivo no es una imagen: su contenido es un ejecutable de Windows con extensión cambiada.» (un `.pdf` ni siquiera se ofrece) | Evento `ARCHIVO_RECHAZADO` |
| 16 | Dos navegadores a la vez | Iniciar sesión con el mismo usuario en dos navegadores | Con `SESION_UNICA=1` (por defecto) la primera sesión se cierra con aviso al siguiente clic; con `0` conviven. | Evento `SESION_REEMPLAZADA` |
| 17 | Forzar un fallo | `docker compose stop mysql`, usar la aplicación, luego `docker compose start mysql` | El error queda en `data/logs/errores.log` (`docker compose exec web tail -n 30 data/logs/errores.log`) y, con la base arriba, en Auditoría y seguridad → *Errores del sistema* | Captura de la pestaña y del archivo |
| 18 | Cerrar sesión y usar otra pestaña | Con la sesión abierta en dos pestañas, cerrar sesión en la primera y hacer clic en la segunda | La segunda vuelve a la pantalla de acceso («Su sesión se cerró…») | Evento `LOGOUT` |
| 19 | Cifrado en la base de datos | `docker compose exec mysql mysql -uroot -pcarro_paro_local carro_paro_db -e "SELECT correo, LEFT(password_hash,7) AS hash, LEFT(totp_secret,8) AS totp FROM usuarios WHERE totp_secret IS NOT NULL OR id<4;"` | `password_hash` empieza con `$2b$12$` (bcrypt) y `totp_secret` con `enc:` (Fernet) | Captura de la consulta |
| 20 | Cambiar contraseña y correo | Mi cuenta → Contraseña, y Mi cuenta → Correo (contraseña actual + código enviado al correo nuevo) | Ambos cambios se aplican; se avisa al correo anterior; hay que entrar con el correo nuevo | Eventos `CAMBIO_PASSWORD`, `CAMBIO_CORREO` |

## Límites conocidos (para el informe)
* La API usa tokens JWT sin lista de revocación: un token robado vale hasta que expira (`JWT_MINUTOS_EXPIRACION`).
  La web sí revoca sesiones en el servidor.
* El cambio de correo y la recuperación sin MFA dependen de que el correo registrado sea de la persona.
  Con `CORREO_MODO=desactivado` no hay forma de enviar códigos.
* `script-src`/`style-src 'unsafe-inline'` en la CSP son un riesgo aceptado (ver REMEDIACION.md).

## Ajustes posteriores (revisión del usuario)

- **Caso 2:** el campo «Correo institucional» del acceso ya no deja *escribir, pegar ni soltar* caracteres distintos de letras, números y `. _ % + - @` (filtro en el navegador, `app/filtros.py`). La validación del servidor se mantiene.
- **Caso 14:** se eliminó la «mirilla» de las contraseñas (CSS `OCULTAR_MIRILLA`); el campo queda `type="password"` y no se puede copiar.
- **Caso 10:** vencimiento del token del segundo factor (autenticador): `MFA_PENDIENTE_MINUTOS` (la pantalla del código expira por inactividad, por defecto 5; `.env.example` sugiere 2) y `MFA_VENTANA` (0 = solo se acepta el código TOTP actual). Probar: iniciar sesión como admin, esperar el tiempo configurado en la pantalla del código y pulsar Verificar → vuelve al inicio con aviso.
