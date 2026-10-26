# DEBUPA · SENA Oportunidades

Prototipo de una herramienta independiente para ayudar a aprendices del SENA a ordenar oportunidades del SGVA y revisar posibles destinatarios antes de iniciar una campaña de contacto externo.

## Estado actual

Un único acceso con Google vincula el permiso de envío de Gmail; su token de renovación se conserva cifrado. El primer formulario guarda filtros y el segundo guarda perfil, mensaje y adjuntos cifrados durante un máximo de 24 horas al iniciar la consulta. Con `DEBUPA_SGVA_ACTIVO=true`, el servidor usa una sesión aislada de Chromium para consultar solicitudes visibles en SGVA. Para «todos los departamentos» hace primero una búsqueda concreta y después otra con el selector vacío, como exige la interfaz SGVA. Prioriza las ofertas recientes del listado completo antes de leer sus detalles. Con `GEMINI_API_KEY` y autorización específica, Gemini clasifica perfil y funciones y guarda puntuación y motivo; sin ambos requisitos, las ofertas quedan pendientes de IA. Las credenciales SGVA permanecen solo en memoria durante la consulta. La interfaz no postula aprendices. Después de revisar empresas y mensaje, el usuario autoriza expresamente el envío desde su Gmail. Con el modo SGVA desactivado, continúa la demostración con empresas ficticias y sin envíos reales.

El selector muestra una selección práctica de ciudades y municipios principales, verificada con DIVIPOLA. Si una población no aparece, se puede elegir «Todos los municipios». Para actualizar la selección desde la fuente oficial, ejecuta `python -m herramientas.actualizar_municipios` desde la raíz del repositorio. El script actualiza las copias del frontend y el backend.

La estructura inicial de PostgreSQL ya tiene migraciones versionadas. El procedimiento de creación y conexión segura está en [backend/README.md](backend/README.md#preparar-postgresql-en-supabase).

## Ejecutar la aplicación local

Para probar el inicio de sesión, sirve frontend y API juntos:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-postgresql.txt
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Resolve-Path '.venv').Path 'ms-playwright'
.\.venv\Scripts\python.exe -m playwright install chromium
$env:DEBUPA_ENTORNO = "desarrollo"
$env:DEBUPA_SGVA_ACTIVO = "true"
$env:DEBUPA_CORREO_ADMIN = "debupawebapp@gmail.com"
$env:GOOGLE_URL_INICIO = "/#inicio"
$env:DEBUPA_SECRETO_SESION = ((New-Guid).Guid + (New-Guid).Guid).Replace("-", "")
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.aplicacion.principal:aplicacion --host 127.0.0.1 --port 8000
```

Estas órdenes suponen que ya configuraste la conexión PostgreSQL, el certificado SSL, `GOOGLE_CLIENTE_ID`, `GOOGLE_CLIENTE_SECRETO`, `DEBUPA_CLAVE_CIFRADO` y la URI de callback en la misma terminal. Abre `http://127.0.0.1:8000/` y pulsa «Entrar con Google». La guía completa está en [INICIAR_SERVICIOS.txt](INICIAR_SERVICIOS.txt).

Para comprobar Gmail, en la portada pulsa «Enviar prueba a mi correo». Se enviará un solo mensaje a tu propia dirección, con un adjunto de texto pequeño; revisa «Recibidos» y «Enviados». El botón funciona una vez por sesión local y no consume el límite mensual de campañas. Si Gmail no confirma el resultado, revisa «Enviados» antes de iniciar otra sesión: repetir una solicitud incierta podría duplicar el mensaje. No se necesita una nueva migración para esta prueba.

Para probar el guardado temporal, actualiza la base con `.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head`, llena las preferencias y el correo y pulsa «Guardar borrador cifrado». Puedes eliminarlo desde esa pantalla o desde «Tus datos temporales guardados» al volver a entrar. El servidor elimina los borradores vencidos al iniciarse y cada 15 minutos mientras está activo. La vista previa muestra metadatos, pero todavía no permite reabrir el texto para editarlo.

Para usar la consulta y el envío real, instala Chromium como se indica arriba, aplica las migraciones hasta `0008`, activa `DEBUPA_SGVA_ACTIVO=true` y llena los formularios con tus datos SGVA. El servidor consulta empresas visibles y deja los resultados para revisión. Puedes cerrar y reabrir la página mientras el servidor trabaja. Tras elegir empresas, pulsa «Revisar envío»: se muestran remitente, destinatarios aptos y omitidos, texto y adjuntos. Solo «Confirmar y enviar» inicia los mensajes reales, uno por empresa. El registro local impide recontactar antes de seis meses y no reintenta automáticamente un resultado incierto; en ese caso revisa Gmail «Enviados». Al terminar, DEBUPA envía desde `debupawebapp@gmail.com` a la cuenta del aprendiz un resumen de teléfonos válidos y elimina el contenido temporal. Para probar IA configura `GEMINI_API_KEY` y marca su autorización. La clave se crea en Google AI Studio, por separado del cliente OAuth. El nivel gratuito de Gemini puede usar los textos enviados para mejorar productos de Google. La consulta de IA no incluye documento, contraseña, datos de contacto ni adjuntos. El historial previo a DEBUPA no se puede verificar con el permiso actual de Gmail.

### Vincular el correo de DEBUPA para los resúmenes

1. Añade `debupawebapp@gmail.com` a los usuarios de prueba de Google Auth Platform si el proyecto OAuth sigue en estado «Prueba».
2. Configura `DEBUPA_CORREO_ADMIN=debupawebapp@gmail.com`, reinicia el servidor y entra con esa cuenta. Acepta el permiso de envío de Gmail.
3. Abre «Administración» y pulsa «Probar envío propio». Comprueba Recibidos y Enviados de DEBUPA. Puedes cerrar sesión: el permiso cifrado de esa cuenta permanece disponible para resúmenes y avisos; los permisos de las cuentas de aprendices se revocan al salir.

Si el correo de DEBUPA no está conectado, la revisión final rechaza el envío antes de contactar empresas. Si Google revoca el permiso durante una campaña, los envíos a empresas ya confirmados se conservan y el resultado avisa que el resumen no pudo confirmarse. Si falla la prueba de envío propia, vuelve a vincular la cuenta de DEBUPA.

## Estructura actual

```text
frontend/
  index.html                 Páginas y formularios semánticos
  estilos/                   Variables, base, componentes y páginas
  guiones/                   Rutas, validaciones, ubicaciones y ejemplos
  recursos/iconos.svg        Iconografía reutilizable
docs/
  diseno-experiencia.md      Decisiones de contenido y usabilidad
backend/
  aplicacion/               API, reglas, modelos y contratos de integración
  pruebas/                  Pruebas de permisos y reglas críticas
  README.md                 Instalación, endpoints y trabajo pendiente
```

## Activación Premium local

El plan cuesta $7.500 COP por tres meses desde su aprobación. El aprendiz adjunta un comprobante PNG, JPG o PDF; solo la cuenta administradora puede abrirlo y aprobar o rechazar después de comprobar el movimiento en Nequi. La aplicación cifra el comprobante y lo elimina de la base activa al decidir. El panel muestra usuarios, planes, solicitudes y avisos no confirmados. La cola de SGVA muestra cuántas búsquedas preceden a la propia y una animación de espera. No se ha desplegado públicamente.

Las instrucciones del servidor y su alcance exacto están en [backend/README.md](backend/README.md).

El código y las páginas de información están redactados en español. Las políticas mostradas en la interfaz son borradores informativos que deberán completarse y revisarse antes de tratar datos reales.
