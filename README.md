# Rumbo · SENA Oportunidades

Prototipo de una herramienta independiente para ayudar a aprendices del SENA a ordenar oportunidades del SGVA y revisar posibles destinatarios antes de iniciar una campaña de contacto externo.

## Estado actual

La primera entrega es una interfaz estática navegable en `frontend/`. Usa empresas, correos y porcentajes ficticios; no consulta el SGVA, no inicia sesión con Google, no recibe pagos y no envía mensajes. El formulario de credenciales SGVA permanece desactivado hasta que exista un backend seguro.

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
```

## Próximas piezas

- API Python/FastAPI y PostgreSQL para usuarios, campañas e historial.
- Inicio de sesión con Google y permiso mínimo de Gmail.
- Una cola persistente con un solo navegador Playwright para SGVA.
- Clasificación local y explicable de empresas.
- Revisión humana, envío individual y seguimiento real.
- Panel administrativo protegido y verificación manual de Nequi.

El código y las páginas de información están redactados en español. Las políticas mostradas en la interfaz son borradores informativos que deberán completarse y revisarse antes de tratar datos reales.
