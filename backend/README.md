# Backend de DEBUPA

Base local en FastAPI y SQLAlchemy. El código, las rutas y los modelos usan nombres descriptivos en español. La API sirve también el frontend en el mismo origen para que Google OAuth comparta la cookie de sesión.

## Lo que funciona ahora

- Borradores con modalidad, ubicación, antigüedad, consentimiento y plan asignado por el servidor.
- Exclusiones de correo normalizadas y persistentes por usuario.
- Historial mínimo de correos enviados por la aplicación; la regla de seis meses no lee Gmail.
- Reglas de límites: gratis hasta ocho destinatarios y dos tarjetas; premium hasta treinta destinatarios, siempre según coincidencias disponibles.
- Un adjunto para gratis, dos para premium, ambos de hasta 5 MB; la espera de un mes calendario para gratis comienza solo después de un envío registrado. Premium no espera y una búsqueda sin envíos permite reintentar.
- Separación de alta coincidencia y «por revisar», y validación de ubicación, fecha y adjuntos.
- Selección local de ciudades y municipios principales verificada con [DIVIPOLA](https://www.datos.gov.co/Mapas-Nacionales/DIVIPOLA-C-digos-municipios/gdxc-w37w), sincronizada con el frontend mediante `python -m herramientas.actualizar_municipios`.
- Consulta de SGVA con un único navegador Chromium, lectura del listado y detalles sin pulsar «Aplicar».
- Consulta de todos los departamentos en dos búsquedas y lectura de ofertas recientes primero. Clasificación optativa en Gemini con puntuación y motivo, sujeta a autorización del aprendiz.
- Modelo y servicio de aprobación manual del pago. El cliente nunca puede asignarse premium.
- Migraciones de PostgreSQL para el esquema inicial, identidad de Google y permiso de Gmail cifrado, con acceso a las tablas cerrado para los roles públicos de Supabase.
- Guardado opcional y cifrado de perfil, mensaje y adjuntos por campaña durante 24 horas; máximo dos borradores activos por cuenta, borrado manual y limpieza periódica.

`POST /api/v1/campanas` guarda únicamente filtros. Con `DEBUPA_SGVA_ACTIVO=true`, `/api/v1/campanas/{id}/iniciar` recibe documento y clave SGVA una sola vez. Se colocan en una cola de memoria y el trabajador consulta las ofertas con Playwright, hasta 70 por campaña. Si existe `GEMINI_API_KEY` y el aprendiz marca `acepta_ia`, el mismo pedido lleva `perfil_ia` a la cola volátil. Gemini recibe los intereses y las funciones sin identidad ni datos de contacto; devuelve puntuación y motivo. Si no hay clave, autorización o respuesta válida, las ofertas quedan sin puntuación para revisión humana. El proceso continúa si se cierra el navegador del usuario mientras el servidor permanezca encendido. Al reiniciarse el servidor, las consultas activas o en cola se marcan interrumpidas; el aprendiz debe crear otra búsqueda e introducir sus credenciales de nuevo. El modo de demostración permanece disponible con `DEBUPA_SGVA_ACTIVO=false`. Ningún modo postula al aprendiz ni envía correos a empresas.

La interfaz recuerda que un patrocinio activo o una postulación en curso pueden impedir la búsqueda de empresas en SGVA. Estas condiciones no se comprueban automáticamente. El adaptador distingue un rechazo de cuenta (`sgva_restringido`) de una caída del servicio (`sgva_no_disponible`), sin atribuir una causa específica que SGVA no confirme. El aviso recurrente de actualización de contacto se cierra pulsando «Actualizar» con sus datos actuales y «Cancelar» en la confirmación, como se comprobó en la sesión de prueba.

## Desarrollo local en Windows

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-desarrollo.txt
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Resolve-Path '.venv').Path 'ms-playwright'
.\.venv\Scripts\python.exe -m playwright install chromium
$env:DEBUPA_SGVA_ACTIVO = "true"
$env:DEBUPA_CLAVE_PRUEBAS = "una-clave-larga-y-aleatoria-solo-local"
.\.venv\Scripts\python.exe -m backend.aplicacion.inicializar
.\.venv\Scripts\python.exe -m uvicorn backend.aplicacion.principal:aplicacion --host 127.0.0.1 --port 8001
```

La página local queda en `http://127.0.0.1:8001/` y la documentación interactiva en `http://127.0.0.1:8001/docs`. Las rutas privadas usan temporalmente `Authorization: Bearer <DEBUPA_CLAVE_PRUEBAS>` solo en desarrollo cuando no hay sesión de Google. No se debe publicar este modo ni usar una contraseña real del SGVA. En producción, la identidad de prueba queda desactivada.

Pruebas:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\pruebas -q
```

La base local SQLite se crea en `backend/datos/` y Git la ignora. Para producción se usará PostgreSQL y migraciones versionadas; `create_all` solo se permite en desarrollo.

## Preparar PostgreSQL en Supabase

DEBUPA usa PostgreSQL desde el backend; **no utiliza la Data API de Supabase desde el navegador**. La configuración siguiente prepara la base. La consulta de SGVA y la clasificación por IA siguen siendo experimentales; antes de abrir el servicio a otros aprendices faltan la política de datos definitiva, controles operativos y una prueba real del proveedor de IA.

1. Crea un proyecto nuevo en [Supabase](https://supabase.com/dashboard), elige una región apropiada y genera una contraseña larga y única. Guárdala en tu gestor de contraseñas. Si aparece «Automatically expose new tables», déjalo desactivado.
2. En el proyecto, ve a **Integrations → Data API** y desactiva **Enable Data API**. Así las tablas no tendrán endpoints REST automáticos. En **Database Settings → SSL Configuration**, activa la obligación de SSL y descarga el certificado CA a una carpeta privada fuera del repositorio.
3. En **Connect**, copia la cadena **Direct connection** si tu red admite IPv6; de lo contrario, usa **Session pooler** (puerto 5432). No uses **Transaction pooler** para estas migraciones. Conserva exactamente el usuario, servidor y puerto que entregue Supabase.
4. En tu cadena, cambia solo `postgresql://` por `postgresql+psycopg://`, sustituye el marcador de contraseña y añade `?sslmode=verify-full` (o `&sslmode=verify-full` si ya hay otros parámetros). Codifica los caracteres especiales de la contraseña como exige una URL. **No pegues la cadena en GitHub, el frontend, capturas ni chats.**
5. Desde la raíz del repositorio instala los paquetes de PostgreSQL y configura temporalmente las variables en la misma terminal PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-postgresql.txt
$env:DEBUPA_ENTORNO = "produccion"
$env:PGSSLROOTCERT = "C:\ruta\privada\certificado-ca.crt"
$direccionProtegida = Read-Host "Cadena PostgreSQL completa" -AsSecureString
$env:DEBUPA_BASE_DATOS = [System.Net.NetworkCredential]::new("", $direccionProtegida).Password
Remove-Variable direccionProtegida
```

6. Comprueba la conexión y aplica las migraciones pendientes en la base de este proyecto. Si ya llegaste a `0004`, `upgrade head` añade `0005` sin borrar las tablas anteriores:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini check
```

`current` debe mostrar `0005_consulta_sgva (head)` después de aplicar las migraciones; `check` debe indicar que no hay operaciones nuevas. En el editor SQL de Supabase puedes comprobarlo sin modificar datos:

```sql
select version_num from alembic_version;
select id from navegador_sgva;
```

La segunda consulta debe devolver únicamente `1`. Cierra la terminal cuando termines para retirar la cadena de su entorno. En Supabase Free debes organizar copias de seguridad externas antes de almacenar datos reales. No ejecutes `downgrade` en una base con información: eliminaría tablas.

## Google OAuth y permiso de Gmail

La API usa OpenID Connect de Google para identificar al aprendiz y solicita `gmail.send` en el mismo consentimiento. El callback crea o actualiza el usuario local con el identificador estable de Google, el correo verificado y el nombre visible; cifra el token de renovación antes de persistirlo.

En Google Cloud Console crea un cliente OAuth de tipo **Aplicación web** y registra exactamente:

```text
http://127.0.0.1:8000/api/v1/autenticacion/google/callback
```

En la terminal donde se levanta la API configura:

```powershell
$env:GOOGLE_CLIENTE_ID = "tu-cliente-id.apps.googleusercontent.com"
$env:GOOGLE_CLIENTE_SECRETO = "tu-secreto"
$env:GOOGLE_URI_REDIRECCION = "http://127.0.0.1:8000/api/v1/autenticacion/google/callback"
$env:GOOGLE_URL_INICIO = "/#inicio"
$env:DEBUPA_SECRETO_SESION = "genera-un-secreto-aleatorio-de-al-menos-32-caracteres"
$env:DEBUPA_CLAVE_CIFRADO = "una-clave-Fernet-estable-y-guardada-fuera-del-repositorio"
```

Después aplica la migración de identidad:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

Para probar en tu computador con PostgreSQL, usa `DEBUPA_ENTORNO=desarrollo` y levanta la API solo en `127.0.0.1`. Puedes conservar `DEBUPA_BASE_DATOS` y `PGSSLROOTCERT` ya configuradas. La cookie de producción exige HTTPS y por eso no sirve para esta prueba local con HTTP.

```powershell
$env:DEBUPA_ENTORNO = "desarrollo"
$env:GOOGLE_URL_INICIO = "/#inicio"
$env:DEBUPA_SECRETO_SESION = ((New-Guid).Guid + (New-Guid).Guid).Replace("-", "")
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-postgresql.txt
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.aplicacion.principal:aplicacion --reload --host 127.0.0.1 --port 8000
```

Activa Gmail API en Google Cloud y declara únicamente el permiso `https://www.googleapis.com/auth/gmail.send`. Con la clave de cifrado configurada, «Entrar con Google» autoriza la cuenta y Gmail en un solo paso. DEBUPA solicita acceso offline y guarda únicamente el token de renovación cifrado. «Cerrar sesión» elimina ese token local e intenta revocar el permiso en Google; si Google no responde, el acceso local queda eliminado. Para volver a vincular Gmail, inicia sesión de nuevo. En desarrollo local puedes enviar una prueba únicamente a tu propia cuenta; las campañas todavía no envían mensajes y DEBUPA no lee la bandeja.

## Rutas disponibles

| Ruta | Acceso | Estado |
| --- | --- | --- |
| `GET /api/v1/salud` | Público | Comprueba que la API y la base responden. |
| `GET /api/v1/autenticacion/google/iniciar` y callback | Público | Completa el inicio de sesión con Google y guarda el permiso de Gmail cifrado. |
| `GET /api/v1/autenticacion/yo` y `POST /api/v1/autenticacion/cerrar-sesion` | Sesión | Muestra la cuenta actual; al salir elimina la conexión de Gmail. |
| `GET /api/v1/gmail/estado` | Sesión | Indica si Gmail quedó vinculado en el inicio de sesión. |
| `POST /api/v1/gmail/prueba` | Sesión + CSRF, solo local | Envía una prueba fija a la propia cuenta, una vez por sesión. |
| `PUT /api/v1/campanas/{id}/contenido` | Sesión + CSRF | Guarda perfil, mensaje y adjuntos cifrados durante 24 horas. |
| `GET /api/v1/contenidos-temporales` | Sesión | Lista los borradores temporales propios vigentes. |
| `GET /api/v1/campanas/{id}/contenido` | Sesión | Consulta fecha y nombres de adjuntos propios. |
| `DELETE /api/v1/campanas/{id}/contenido` | Sesión + CSRF | Borra contenido propio antes de la etapa de envío, incluso después de encolar. |
| `GET /api/v1/capacidades` | Público | Declara claramente qué integraciones faltan. |
| `GET /api/v1/planes` | Público | Muestra los límites, no promete una cantidad mínima. |
| `GET /api/v1/disponibilidad` | Sesión | Indica si el aprendiz puede crear otra búsqueda y la próxima fecha. |
| `POST /api/v1/campanas` | Sesión | Guarda solo un borrador de filtros. |
| `GET /api/v1/campanas` y `GET /api/v1/campanas/{id}` | Sesión | Muestra solo campañas del usuario. |
| `POST /api/v1/campanas/{id}/iniciar` | Sesión + CSRF | En modo SGVA recibe credenciales y, si el usuario autoriza IA, `acepta_ia` y `perfil_ia`; en modo demo prepara ejemplos. No envía mensajes. |
| `GET /api/v1/campanas/{id}/destinatarios` | Sesión | Devuelve los resultados de la campaña propia cuando están listos. |
| `GET /api/v1/correos-excluidos` y `DELETE /api/v1/correos-excluidos/{correo}` | Sesión | Gestiona exclusiones propias. |
| `GET /api/v1/historial` | Sesión | Lee solo envíos propios registrados por DEBUPA. |

El navegador no recibe CORS abierto: el frontend y la API comparten origen. Antes de publicar faltan controles operativos adicionales, entre ellos límites de solicitudes y control de administrador.

## Integraciones para continuar

1. **Google Identity Services / OAuth 2.0:** inicio de sesión verificable con permiso `gmail.send` y acceso offline. No se necesita `gmail.readonly` si el historial se basa en los envíos registrados por DEBUPA. Para campañas que sigan cuando el usuario cierre el navegador se usará el token de renovación cifrado.
2. **SGVA:** confirmar con SENA si ofrece una integración autorizada. Si no, un adaptador Playwright con una sola sesión, límites y manejo de caídas. Nunca se pulsará «Aplicar» automáticamente.
3. **IA:** el adaptador Gemini 3.5 Flash-Lite clasifica en lotes con una clave `GEMINI_API_KEY` creada en Google AI Studio y autorización específica en el formulario. El perfil y las funciones se transmiten al proveedor tras retirar patrones de contacto; no se envían credenciales, correo redactado ni adjuntos. La modalidad no mencionada queda «posible» y requiere revisión. En el nivel gratuito Google puede usar las entradas para mejorar sus productos. Los límites gratuitos varían y el servicio puede devolver ofertas sin puntuación. Esta integración se ha probado con respuestas simuladas; falta comprobar una llamada real con una clave propia antes de un piloto.
4. **Gmail API:** el envío local de prueba ya renueva el permiso y usa `users.messages.send`. Para campañas faltan envíos individuales confirmados e historial idempotente que evite duplicar destinatarios ante reintentos.
5. **Almacenamiento temporal cifrado:** el perfil, asunto, cuerpo y hasta dos adjuntos ya se pueden guardar de forma opcional durante 24 horas. El servidor borra vencidos al arrancar y cada 15 minutos mientras está activo; el usuario puede borrar antes. Las credenciales SGVA no se escriben en tablas ni archivos y se pierden si el proceso se reinicia. La comprobación de firmas de archivo no sustituye un análisis antimalware. Las copias de seguridad del proveedor pueden conservar datos cifrados más tiempo que las tablas activas.
6. **Nequi:** QR y comprobante en almacenamiento privado. El administrador contrastará el movimiento real y aprobará desde un panel protegido; no se necesita API de Nequi para la verificación manual.
7. **PostgreSQL:** la migración inicial está lista, pero aún falta verificarla contra una instancia PostgreSQL real y preparar copias de seguridad. La reserva de un solo navegador usa bloqueo de fila. SQLite queda limitada a desarrollo y pruebas.

Antes de un piloto real deberán completarse las políticas de privacidad, plazos de conservación, eliminación de cuenta, revisión legal y autorización operativa para la consulta automatizada.
También faltan definir el precio y la duración del plan premium antes de aceptar pagos.
