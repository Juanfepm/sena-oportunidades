# Arquitectura del backend

Las reglas puras viven en `aplicacion/dominio`; no importan FastAPI, SQLAlchemy,
Playwright ni clientes HTTP. `aplicacion/servicios` coordina casos de uso y
`aplicacion/integraciones` encapsula SGVA, Gemini, Google OAuth, Gmail y
cifrado. `aplicacion/rutas` convierte peticiones y errores en respuestas HTTP;
`aplicacion/infraestructura` gestiona el ciclo de vida del servidor.
`principal.py` solo compone la aplicación.

Cada cambio debe conservar los contratos de la API y verificar los flujos
afectados con pruebas. Se prefieren nombres descriptivos en español, estilo
PEP 8, funciones pequeñas y dependencias que apunten hacia las reglas del
negocio. Una abstracción nueva necesita un caso de uso real; no se crean capas
vacías para imitar una plantilla.

Referencias:

- https://peps.python.org/pep-0008/
- https://github.com/alefeans/python-clean-architecture
- https://github.com/javiertelioz/clean-architecture-python
