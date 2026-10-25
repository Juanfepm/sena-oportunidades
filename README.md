# DEBUPA · SENA Oportunidades

Prototipo de una herramienta independiente para ayudar a aprendices del SENA a ordenar oportunidades del SGVA y revisar posibles destinatarios antes de iniciar una campaña de contacto externo.

## Estado actual

El frontend es una vista previa navegable con empresas ficticias. Un único acceso con Google vincula el permiso mínimo de envío de Gmail; su token de renovación se conserva cifrado. La cabecera muestra la cuenta y permite cerrar la sesión y desconectar Gmail con el mismo botón, que elimina el token guardado. El primer formulario guarda los filtros en la base de datos. La búsqueda, selección de empresas y envío siguen siendo demostraciones: faltan SGVA, almacenamiento temporal cifrado del contenido de campaña y el trabajador de la cola. Las credenciales SGVA siguen desactivadas en el frontend.

El selector muestra una selección práctica de ciudades y municipios principales, verificada con DIVIPOLA. Si una población no aparece, se puede elegir «Todos los municipios». Para actualizar la selección desde la fuente oficial, ejecuta `python -m herramientas.actualizar_municipios` desde la raíz del repositorio. El script actualiza las copias del frontend y el backend.

La estructura inicial de PostgreSQL ya tiene migraciones versionadas. El procedimiento de creación y conexión segura está en [backend/README.md](backend/README.md#preparar-postgresql-en-supabase).

## Ejecutar la aplicación local

Para probar el inicio de sesión, sirve frontend y API juntos:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-postgresql.txt
$env:DEBUPA_ENTORNO = "desarrollo"
$env:GOOGLE_URL_INICIO = "/#inicio"
$env:DEBUPA_SECRETO_SESION = ((New-Guid).Guid + (New-Guid).Guid).Replace("-", "")
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.aplicacion.principal:aplicacion --reload --host 127.0.0.1 --port 8000
```

Estas órdenes suponen que ya configuraste la conexión PostgreSQL, el certificado SSL, `GOOGLE_CLIENTE_ID`, `GOOGLE_CLIENTE_SECRETO`, `DEBUPA_CLAVE_CIFRADO` y la URI de callback en la misma terminal. Abre `http://127.0.0.1:8000/` y pulsa «Entrar con Google». La guía completa está en [INICIAR_SERVICIOS.txt](INICIAR_SERVICIOS.txt).

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

## Próximas piezas

- Envío individual de correos tras la confirmación del aprendiz.
- Integración autorizada con SGVA y trabajador Playwright de una sola sesión.
- Carga temporal cifrada de credenciales, correo y adjuntos, con eliminación verificable.
- Clasificación explicable, revisión humana y envío individual real.
- Panel administrativo protegido, almacenamiento privado de comprobantes Nequi y migraciones PostgreSQL.

Las instrucciones del servidor y su alcance exacto están en [backend/README.md](backend/README.md).

El código y las páginas de información están redactados en español. Las políticas mostradas en la interfaz son borradores informativos que deberán completarse y revisarse antes de tratar datos reales.
