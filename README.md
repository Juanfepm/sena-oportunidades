# DEBUPA · SENA Oportunidades

Prototipo de una herramienta independiente para ayudar a aprendices del SENA a ordenar oportunidades del SGVA y revisar posibles destinatarios antes de iniciar una campaña de contacto externo.

## Estado actual

El frontend es una vista previa navegable con empresas ficticias. El backend ya ofrece borradores, exclusiones persistentes, historial mínimo, reglas de selección, cola para un navegador y verificación manual de pagos como servicios internos. Aún no se conectan entre sí ni se ejecuta una campaña real: faltan Google, SGVA, Gmail, almacenamiento temporal cifrado y el trabajador de la cola. Las credenciales SGVA siguen desactivadas en el frontend.

El selector de municipio o localidad usa un catálogo DIVIPOLA local. Para actualizarlo desde la fuente oficial, ejecuta `python -m herramientas.actualizar_municipios` desde la raíz del repositorio. El script actualiza las copias del frontend y el backend.

## Ejecutar la vista previa

Sirve `frontend/` con cualquier servidor HTTP estático y abre su dirección local. Por ejemplo:

```bash
python -m http.server 8000 --directory frontend
```

Luego abre `http://localhost:8000/`. No abras el archivo HTML mediante `file://`: los módulos JavaScript y los SVG externos requieren un servidor HTTP.

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

- Inicio de sesión con Google y permiso mínimo de Gmail.
- Integración autorizada con SGVA y trabajador Playwright de una sola sesión.
- Carga temporal cifrada de credenciales, correo y adjuntos, con eliminación verificable.
- Clasificación explicable, revisión humana y envío individual real.
- Panel administrativo protegido, almacenamiento privado de comprobantes Nequi y migraciones PostgreSQL.

Las instrucciones del servidor y su alcance exacto están en [backend/README.md](backend/README.md).

El código y las páginas de información están redactados en español. Las políticas mostradas en la interfaz son borradores informativos que deberán completarse y revisarse antes de tratar datos reales.
