# Backend de DEBUPA

Base local en FastAPI y SQLAlchemy. El código, las rutas y los modelos usan nombres descriptivos en español. La interfaz actual todavía no llama a esta API.

## Lo que funciona ahora

- Borradores con modalidad, ubicación, antigüedad, consentimiento y plan asignado por el servidor.
- Exclusiones de correo normalizadas y persistentes por usuario.
- Historial mínimo de correos enviados por la aplicación; la regla de seis meses no lee Gmail.
- Reglas de límites: gratis hasta ocho destinatarios y dos tarjetas; premium hasta treinta destinatarios, siempre según coincidencias disponibles.
- Un adjunto para gratis, dos para premium, ambos de hasta 5 MB; la espera de un mes calendario para gratis comienza solo después de un envío registrado. Premium no espera y una búsqueda sin envíos permite reintentar.
- Separación de alta coincidencia y «por revisar», y validación de ubicación, fecha y adjuntos.
- Selección local de ciudades y municipios principales verificada con [DIVIPOLA](https://www.datos.gov.co/Mapas-Nacionales/DIVIPOLA-C-digos-municipios/gdxc-w37w), sincronizada con el frontend mediante `python -m herramientas.actualizar_municipios`.
- Reserva persistente y renovable de un único navegador para el futuro trabajador SGVA.
- Modelo y servicio de aprobación manual del pago. El cliente nunca puede asignarse premium.
- Migración inicial de PostgreSQL, con acceso a las tablas cerrado para los roles públicos de Supabase.

No se aceptan contraseñas SGVA, cuerpos de correo ni archivos en los borradores. El endpoint `/api/v1/campanas/{id}/iniciar` devuelve 503 hasta que existan las integraciones seguras. La cola es una base de datos y reglas; todavía no hay un trabajador que consulte SGVA o envíe Gmail.

## Desarrollo local en Windows

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-desarrollo.txt
$env:DEBUPA_CLAVE_PRUEBAS = "una-clave-larga-y-aleatoria-solo-local"
.\.venv\Scripts\python.exe -m backend.aplicacion.inicializar
.\.venv\Scripts\python.exe -m uvicorn backend.aplicacion.principal:aplicacion --host 127.0.0.1 --port 8001
```

La documentación interactiva local queda en `http://127.0.0.1:8001/docs`. Las rutas privadas usan temporalmente `Authorization: Bearer <DEBUPA_CLAVE_PRUEBAS>` solo en desarrollo. No se debe publicar este modo ni usar una contraseña real del SGVA. Si no se configura la clave, esas rutas responden 503. En producción, la identidad de prueba también queda desactivada.

Pruebas:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\pruebas -q
```

La base local SQLite se crea en `backend/datos/` y Git la ignora. Para producción se usará PostgreSQL y migraciones versionadas; `create_all` solo se permite en desarrollo.

## Preparar PostgreSQL en Supabase

DEBUPA usa PostgreSQL desde el backend; **no utiliza la Data API de Supabase desde el navegador**. La configuración siguiente prepara la base, pero **no habilita aún el servicio para usuarios reales**: faltan inicio de sesión, trabajador, almacenamiento temporal y política de datos definitiva.

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

6. Comprueba la conexión y aplica la migración **solo en una base nueva y vacía**:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini check
```

`current` debe mostrar `0001_esquema_inicial (head)` después de la migración; `check` debe indicar que no hay operaciones nuevas. En el editor SQL de Supabase puedes comprobarlo sin modificar datos:

```sql
select version_num from alembic_version;
select id from navegador_sgva;
```

La segunda consulta debe devolver únicamente `1`. Cierra la terminal cuando termines para retirar la cadena de su entorno. En Supabase Free debes organizar copias de seguridad externas antes de almacenar datos reales. No ejecutes `downgrade` en una base con información: eliminaría tablas.

## Rutas disponibles

| Ruta | Acceso | Estado |
| --- | --- | --- |
| `GET /api/v1/salud` | Público | Comprueba que la API y la base responden. |
| `GET /api/v1/capacidades` | Público | Declara claramente qué integraciones faltan. |
| `GET /api/v1/planes` | Público | Muestra los límites, no promete una cantidad mínima. |
| `GET /api/v1/disponibilidad` | Desarrollo autenticado | Indica si el aprendiz puede crear otra búsqueda y la próxima fecha. |
| `POST /api/v1/campanas` | Desarrollo autenticado | Guarda solo un borrador de filtros. |
| `GET /api/v1/campanas` y `GET /api/v1/campanas/{id}` | Desarrollo autenticado | Muestra solo campañas del usuario. |
| `POST /api/v1/campanas/{id}/iniciar` | Desarrollo autenticado | Bloqueado con 503 hasta conectar proveedores. |
| `GET /api/v1/correos-excluidos` y `DELETE /api/v1/correos-excluidos/{correo}` | Desarrollo autenticado | Gestiona exclusiones propias. |
| `GET /api/v1/historial` | Desarrollo autenticado | Lee solo envíos propios registrados por DEBUPA. |

El navegador no recibe CORS abierto. La futura publicación deberá servir el frontend y la API bajo el mismo origen o configurar orígenes concretos, además de sesión segura, CSRF, límites de solicitudes y control de administrador.

## Integraciones para continuar

1. **Google Identity Services / OAuth 2.0:** inicio de sesión verificable en el servidor. Para enviar se solicitará `gmail.send`; no se necesita `gmail.readonly` si el historial se basa en los envíos registrados por DEBUPA. Para campañas que sigan cuando el usuario cierre el navegador hará falta acceso offline y proteger el token de actualización.
2. **SGVA:** confirmar con SENA si ofrece una integración autorizada. Si no, un adaptador Playwright con una sola sesión, límites y manejo de caídas. Nunca se pulsará «Aplicar» automáticamente.
3. **IA:** un adaptador de clasificación que devuelva puntuación, motivo y grado de certeza. Una modalidad remota no mencionada expresamente quedará «por revisar», no confirmada.
4. **Gmail API:** envíos individuales confirmados, identificación del mensaje enviado e historial idempotente para no duplicar destinatarios ante reintentos.
5. **Almacenamiento temporal cifrado:** contraseña SGVA, perfil, asunto, cuerpo y hasta dos adjuntos deben sobrevivir al cierre del navegador solo mientras dure la campaña, con TTL, claves fuera del repositorio, borrado y pruebas de recuperación. La validación actual de adjuntos no sustituye inspección real de contenido ni análisis antimalware.
6. **Nequi:** QR y comprobante en almacenamiento privado. El administrador contrastará el movimiento real y aprobará desde un panel protegido; no se necesita API de Nequi para la verificación manual.
7. **PostgreSQL:** la migración inicial está lista, pero aún falta verificarla contra una instancia PostgreSQL real y preparar copias de seguridad. La reserva de un solo navegador usa bloqueo de fila. SQLite queda limitada a desarrollo y pruebas.

Antes de un piloto real deberán completarse las políticas de privacidad, plazos de conservación, eliminación de cuenta, revisión legal y autorización operativa para la consulta automatizada.
También faltan definir el precio y la duración del plan premium antes de aceptar pagos.
