# Instrucciones para el backend de DEBUPA

Sigue `ARQUITECTURA.md` y `ruff.toml` en cualquier cambio de Python. El dominio
debe seguir independiente de FastAPI, SQLAlchemy y proveedores externos. Mantén
las rutas HTTP estables; sitúa reglas en `dominio`, orquestación en `servicios`,
proveedores en `integraciones` y configuración del servidor en `infraestructura`.
Evita capas, interfaces y código repetido sin una necesidad concreta.

Antes de entregar, ejecuta `python -m ruff check backend`,
`python -m ruff format backend --check` y `python -m pytest backend/pruebas -q`.
No modifiques `frontend/` durante una refactorización limitada al backend.
