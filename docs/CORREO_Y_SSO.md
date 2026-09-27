# Correos reales e inicio de sesión con Microsoft

Cómo pasar de los usuarios de demostración `@hospital.com` a correos institucionales
que reciben mensajes de verdad, y cómo permitir el ingreso con la cuenta de Microsoft.

Las tres piezas son independientes: puede activar una sin las otras.

| Pieza | Depende de | Dificultad |
|---|---|---|
| 1. Aceptar dominios reales | Nada | Inmediato |
| 2. Enviar correos de verdad | Un buzón con SMTP habilitado | Media |
| 3. Inicio de sesión con Microsoft | Que TI registre la aplicación | Alta |
| 4. Registro por cuenta propia | Que el correo funcione | Baja |

---

## 0. Antes de empezar

```powershell
python scripts/migrar_correo.py
```

Añade siete columnas a `usuarios` y un índice. No toca los datos existentes y se
puede ejecutar las veces que haga falta.

---

## 1. Aceptar dominios de correo reales

Hasta ahora el sistema solo comprobaba que el texto tuviera una arroba. Ahora valida
el formato completo y, si usted lo indica, que el dominio sea uno de los suyos.

En el `.env`:

```
DOMINIOS_CORREO=unipamplona.edu.co,husanrafael.co
CORREO_INSTITUCION=Hospital Universitario San Rafael
```

Vacío significa «cualquier dominio válido», que es lo cómodo mientras desarrolla.
Con la lista puesta, `crear_usuario` rechaza cualquier otro dominio con un mensaje
que dice cuáles se admiten.

**Una decisión deliberada:** la restricción se aplica al *crear* usuarios, no al
*iniciar sesión*. Si se aplicara al entrar, el día que alguien acorte la lista
dejaría fuera a gente que lleva meses trabajando, sin previo aviso y sin entender
por qué. Quien ya tiene cuenta entra; quien se crea desde hoy debe cumplir.

### Cambiar los usuarios de demostración

```sql
UPDATE usuarios SET correo = 'jefatura.urgencias@husanrafael.co'
WHERE correo = 'medico@hospital.com';
```

Hágalo antes de activar el envío real, o los correos saldrán hacia direcciones
inexistentes y su buzón acumulará rebotes.

---

## 2. Enviar correos de verdad

### Qué envía el sistema

| Momento | Mensaje | Por qué importa |
|---|---|---|
| Se crea una cuenta | Bienvenida con el perfil asignado | La persona sabe que existe y qué puede hacer |
| Cuenta bloqueada | Aviso con el motivo y la duración | Si no fue ella, alguien está atacando su cuenta |
| Contraseña cambiada | Constancia del cambio | Convierte un cambio no autorizado en un incidente detectado en minutos |
| Segundo factor | Código de seis dígitos | Ver el apartado 3 |

Lo que **nunca** se envía: contraseñas, ni enlaces que por sí solos cambien algo.
La contraseña inicial la entrega el área de sistemas por otro canal.

### Modo archivo: probarlo sin credenciales

Es el modo por defecto y conviene dejarlo así mientras desarrolla:

```
CORREO_MODO=archivo
```

Cada mensaje se guarda como `.html` en `data/correo_saliente` con el destinatario y
el asunto en la primera línea. Ábralos con doble clic. Para la sustentación es
mejor que el envío real: se ve exactamente el mismo correo, sin depender de la red
de la sala ni de que el servidor de la universidad esté de buen humor.

### Modo SMTP: Microsoft 365

```
CORREO_MODO=smtp
SMTP_HOST=smtp.office365.com
SMTP_PUERTO=587
SMTP_SSL=false
SMTP_USUARIO=carrodeparo@suuniversidad.edu.co
SMTP_PASSWORD=la-clave-de-ese-buzon
CORREO_REMITENTE=carrodeparo@suuniversidad.edu.co
```

Después:

```powershell
python scripts/probar_correo.py su.correo@unipamplona.edu.co
```

### El obstáculo que se va a encontrar

Microsoft **desactiva la autenticación SMTP básica por defecto** en los inquilinos de
Microsoft 365 desde 2022, por seguridad. Si le aparece:

```
535 5.7.139 Authentication unsuccessful, SmtpClientAuthentication is disabled for the Mailbox
```

no es un error suyo: el buzón tiene el envío por SMTP deshabilitado. Salidas, de
mejor a peor:

1. **Pedir a TI que habilite SMTP AUTH en un buzón de servicio.** Se hace por buzón,
   no para todo el dominio, así que es una petición acotada y razonable. Es lo que
   pediría un proveedor de software real.
2. **Usar Microsoft Graph con un registro de aplicación** (permiso `Mail.Send`). Más
   moderno y lo que Microsoft recomienda, pero requiere el mismo registro del
   apartado 3 y consentimiento de administrador.
3. **Un buzón de Gmail con clave de aplicación** (`smtp.gmail.com`, puerto 587). Es
   lo más rápido para una demostración, aunque el remitente no será institucional.
4. **Dejarlo en modo archivo** y mostrar los correos generados. Para sustentar es
   perfectamente defendible: la lógica es idéntica, solo cambia el transporte.

Si la cuenta tiene verificación en dos pasos, una contraseña normal no sirve para
SMTP: hay que generar una *contraseña de aplicación*.

---

## 3. Segundo factor por correo

Alternativa a la aplicación de autenticación, para quien no pueda o no quiera
instalarla. Cada usuario lo activa desde **Mi cuenta**.

### Cómo está construido

| Medida | Valor | Razón |
|---|---|---|
| Longitud | 6 dígitos | Un millón de combinaciones |
| Vigencia | 10 minutos | Acota la ventana de un código interceptado |
| Usos | Uno | Se borra al validarlo |
| Intentos | 5 | Al sexto se anula el código |
| Entre envíos | 60 segundos | Impide usar el sistema para bombardear un buzón |
| Guardado | bcrypt | En la base de datos nunca hay un código legible |
| En los registros | No aparece | Un código en el log vale tanto como no tenerlo |

Adivinarlo tiene una probabilidad de 5 entre 10⁶.

### Lo que hay que decir en la sustentación

**El correo es un segundo factor más débil que el TOTP.** El código viaja por la red
y queda en un buzón; quien controle ese buzón controla el factor. El TOTP se calcula
en el dispositivo y no viaja nunca.

Por eso los roles con permisos críticos —administrador, regente de farmacia, soporte
TI y oficial de seguridad— **siguen obligados a usar la aplicación**. El correo se
les ofrece como canal adicional, no como sustituto. Esa distinción, y no el hecho de
tener dos factores, es lo que muestra criterio.

---

## 4. Inicio de sesión con Microsoft

### Qué gana el sistema

La contraseña deja de pasar por aquí. El usuario se autentica en Microsoft, con la
política de la universidad —incluido el segundo factor de ellos—, y vuelve con un
código de un solo uso que el servidor canjea por su identidad.

Técnicamente es **OpenID Connect con authorization code + PKCE**. Se usa PKCE aunque
haya secreto de cliente porque Streamlit devuelve el código en la barra de
direcciones, donde lo ven el historial y las extensiones; con PKCE, un código robado
de ahí no sirve sin el verificador, que nunca sale del servidor.

### Registrar la aplicación (lo hace TI, o usted si tiene permisos)

1. Entrar al **portal de Azure** → *Microsoft Entra ID* → *Registros de aplicaciones*
   → **Nuevo registro**.
2. Nombre: `SMARTDATA 360 - Carro de Paro`.
3. Tipos de cuenta: **solo este directorio organizativo** (single tenant).
4. URI de redirección: tipo **Web**, valor `http://localhost:8501`.
   Si despliega en un servidor, será su URL real con `https://`.
5. Al crearlo, copiar de la pantalla de resumen:
   - *Id. de aplicación (cliente)* → `MS_CLIENT_ID`
   - *Id. de directorio (inquilino)* → `MS_TENANT_ID`
6. **Certificados y secretos** → *Nuevo secreto de cliente* → copiar el **Valor**
   (no el Id.) → `MS_CLIENT_SECRET`. Solo se ve una vez.
7. **Permisos de API**: `Microsoft Graph` → *Permisos delegados* → `openid`,
   `profile`, `email`, `User.Read`. Los cuatro son de bajo riesgo y no suelen
   requerir consentimiento de administrador.

En el `.env`:

```
MS_CLIENT_ID=00000000-0000-0000-0000-000000000000
MS_CLIENT_SECRET=el-valor-del-secreto
MS_TENANT_ID=11111111-1111-1111-1111-111111111111
MS_REDIRECT_URI=http://localhost:8501
MS_ROL_POR_DEFECTO=
```

El botón *Continuar con Microsoft* aparece solo cuando las tres primeras están
puestas. Sin ellas, la pantalla de acceso se ve como siempre.

### La decisión importante: `MS_ROL_POR_DEFECTO`

**Vacío (recomendado).** Una cuenta de Microsoft válida que no esté dada de alta en
el sistema **no entra**. Alguien debe crearla antes y asignarle un rol.

**Con un rol.** Cualquiera del directorio entra y se le crea la cuenta con ese rol.
Cómodo, y peligroso: en un sistema donde el rol decide quién puede dar de baja
medicamentos, dejar que la pertenencia al directorio otorgue acceso es un error de
diseño. Si lo usa, que sea con el rol de menos privilegios.

### Cómo se identifica a la persona

Por el `oid` de Entra ID, no por el correo. El correo cambia —matrimonio, cambio de
dependencia, corrección de un apellido— y el `oid` no. La primera vez se vincula la
cuenta existente por el correo que Microsoft ya verificó; a partir de ahí manda el
`oid`.

### Si no consigue el registro

Es lo más probable: las áreas de TI universitarias no suelen registrar aplicaciones
de estudiantes. No es un problema para la tesis. El código está completo y probado;
lo que falta son credenciales ajenas. En el documento puede describir el flujo,
mostrar el código y explicar por qué se usa PKCE. Eso demuestra lo mismo que una
demostración en vivo, y es honesto.

---

## 5. Registro por cuenta propia

Cualquier persona puede crear su cuenta desde la pantalla de acceso, como en
cualquier sitio web. El recorrido tiene tres momentos:

```
Crear cuenta  ──▶  Código al correo  ──▶  Autorización  ──▶  Acceso
(nombre, correo,    6 dígitos, 20 min     un administrador    con su perfil
 contraseña)        de vigencia           asigna el perfil
```

### Por qué el formulario no deja elegir el perfil

Es la decisión de diseño que hay que saber defender. En este sistema el perfil
determina quién puede dar de baja medicamentos, modificar el catálogo o gestionar
cuentas. Si el registro dejara elegirlo, registrarse equivaldría a autoasignarse
permisos sobre los carros de paro de un hospital.

La separación es la siguiente: **verificar el correo demuestra que el buzón es
suyo; que además deba operar carros de paro lo decide la institución.** Mientras
tanto la cuenta existe con el perfil `SIN_ASIGNAR`, que no tiene ningún permiso, y
`activo = 0`, de modo que ni siquiera puede iniciar sesión.

Quien administre verá las solicitudes en **Usuarios → Solicitudes de acceso**, con
el nombre, el correo y la fecha, y les asignará el perfil de un desplegable.

### Si prefiere que se active solo

```
REGISTRO_ROL_INICIAL=MEDICO
```

Con eso, verificar el correo activa la cuenta de inmediato con ese perfil, sin que
nadie autorice nada. Es más cómodo y es lo que hace un sitio web corriente. Si lo
usa, que sea con el perfil de menos privilegios; nunca con `ADMIN`,
`REGENTE_FARMACIA`, `TI` ni `OFICIAL_SEGURIDAD`, que son los cuatro que pueden
modificar inventario o cuentas.

Para cerrar el registro del todo: `REGISTRO_ABIERTO=false`.

### Qué pasa si alguien se registra con un correo que ya existe

El mensaje es idéntico al de un correo nuevo. Decir «esa cuenta ya existe» permite
averiguar quién está registrado probando direcciones. En su lugar, al **dueño** del
buzón le llega un aviso de que alguien intentó registrarse con su dirección, que es
información útil para él y para nadie más.

---

## 6. Hacer que los correos lleguen de verdad a Gmail

Esta es la parte con truco. Su cuenta de la universidad es Microsoft 365, y
**Microsoft trae el envío por SMTP deshabilitado desde 2022**. Habilitarlo requiere
que TI lo active buzón por buzón, y puede tardar o no llegar nunca.

La ruta que funciona hoy, sin depender de nadie, es usar una cuenta de Gmail como
remitente. Gmail sí permite el envío por SMTP, con una condición: no acepta la
contraseña normal, exige una **contraseña de aplicación**.

### Paso a paso

1. Cree una cuenta de Gmail para el sistema, por ejemplo
   `carrodeparo.smartdata@gmail.com`. Conviene que sea aparte de la suya personal:
   así el remitente se ve institucional y no mezcla su correo con el del proyecto.

2. En esa cuenta, active la **verificación en dos pasos**:
   *Cuenta de Google → Seguridad → Verificación en dos pasos*.
   Sin esto, el paso siguiente no aparece.

3. Vaya a **myaccount.google.com/apppasswords**, escriba un nombre
   (`SMARTDATA 360`) y genere la contraseña. Google le muestra **16 caracteres**
   en cuatro grupos. Cópielos.

4. En el `.env`:

```
CORREO_MODO=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PUERTO=587
SMTP_SSL=false
SMTP_USUARIO=carrodeparo.smartdata@gmail.com
SMTP_PASSWORD=los16caracteressinespacios
CORREO_REMITENTE=carrodeparo.smartdata@gmail.com
CORREO_INSTITUCION=Hospital Universitario San Rafael
```

Los 16 caracteres van **sin espacios**, aunque Google los muestre separados.

5. Compruébelo:

```powershell
python scripts/probar_correo.py sucorreo@gmail.com
```

### Si algo falla

| Mensaje | Qué pasa |
|---|---|
| `Username and Password not accepted` | Está usando la contraseña normal. Necesita la de aplicación de 16 caracteres |
| No aparece la opción de contraseñas de aplicación | Falta activar la verificación en dos pasos en esa cuenta |
| `SmtpClientAuthentication is disabled` | Está apuntando a Microsoft 365, no a Gmail. Revise `SMTP_HOST` |

### Lo que hay que saber sobre esta solución

Gmail limita el envío a unos **500 correos diarios** por cuenta. Para un sistema
hospitalario real es insuficiente, y además el remitente sería una dirección de
Gmail y no del dominio del hospital, lo que perjudica la entrega y la confianza.

En producción lo correcto es un servicio de correo transaccional con el dominio
propio y sus registros SPF, DKIM y DMARC configurados. **Dígalo usted en el
documento antes de que se lo pregunten**: conocer el límite de la solución que uno
eligió vale más que la solución misma. Para una tesis, Gmail con contraseña de
aplicación es una decisión razonable y documentada.

---

## 7. Comprobar que todo está bien

```powershell
python scripts/probar_correo.py destino@dominio.com
```

Informa el modo activo, si faltan credenciales, e intenta un envío real. Los errores
de Microsoft los traduce a español con la causa y la salida.
