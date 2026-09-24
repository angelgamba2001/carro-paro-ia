# Cambios de la versión 1 a la 2

## Defectos corregidos
| Defecto en v1 | Efecto | Corrección |
|---|---|---|
| `auth.py` aceptaba la contraseña en texto plano si coincidía con el campo `password_hash` | Cualquiera que leyera la BD podía entrar | Solo bcrypt; los hash SHA-256 de v1 se migran a bcrypt en el primer login |
| SHA-256 sin sal | Vulnerable a tablas precalculadas | bcrypt (12 rondas) |
| La pestaña de alertas consultaba `resuelta` y `fecha_creacion`, que no existían | La pestaña fallaba siempre | Consultas alineadas con el esquema |
| `log_auditoria.accion` era ENUM sin `CREACION_USUARIO` | La auditoría de creación de usuarios se perdía | `accion` es VARCHAR |
| El estado del lote se calculaba solo al registrar | Un lote seguía "vigente" después de vencer | `recalcular_estados()` al iniciar sesión y en el pipeline |
| Una fila por unidad física | 10 ampollas = 10 filas; sin cantidades | Lotes con `cantidad` + tabla `movimientos` |
| `DELETE` físico de inventario y alertas | Se perdía la trazabilidad | Baja lógica con motivo y movimiento `BAJA_VENCIMIENTO` |
| OCR: el patrón MM/AAAA se evaluaba antes que la fecha completa | `12/05/2027` se leía como diciembre de 2005 | Orden de patrones corregido, prioridad a la palabra clave de vencimiento |
| Edición/eliminación por ID escrito a mano sin validar existencia | Operaciones silenciosas sobre IDs inexistentes | Selección de registros existentes y validación en el servicio |
| Permisos validados en la vista (`if rol in [...]`) | Cualquier otro canal (API, agente) quedaba sin control | RBAC por permiso validado en la capa de servicios |
| Errores de BD mostrados al usuario | Filtración de detalles internos | Mensajes genéricos, detalle solo en logs |
| `verificar_entorno.py` importaba torch | Fallaba sin PyTorch | Verifica solo lo necesario |

## Seguridad heredada de SGHCU
9 roles y 18 permisos, bloqueo tras 5 intentos por 15 minutos, mensaje genérico de login,
política de contraseñas, cambio obligatorio en el primer ingreso, expiración de sesión por
inactividad, revalidación de rol/estado contra la BD en cada solicitud, JWT para la API,
cabeceras de seguridad, registro de eventos de seguridad y de accesos denegados.

## Segundo factor de autenticación (v2.1)
TOTP compatible con Microsoft/Google Authenticator: activación con código QR, códigos de
respaldo de un solo uso (guardados con bcrypt), bloqueo de códigos reutilizados, obligatorio
para ADMIN, REGENTE_FARMACIA, TI y OFICIAL_SEGURIDAD, y login en dos pasos también en la API
(token temporal de 5 minutos que no da acceso a ningún recurso).

## Nuevo
Carros y servicios, movimientos, pipeline Big Data medallón con PySpark, analítica
(predicción, anomalías, riesgo), API REST, agente con herramientas, dashboard operativo y
analítico, pruebas automatizadas y Docker Compose.
