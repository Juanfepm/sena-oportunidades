"""Composición de la API de DEBUPA."""

import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker
from starlette.formparsers import MultiPartParser
from starlette.middleware.sessions import SessionMiddleware

from .base_datos import crear_motor
from .configuracion import Configuracion
from .dominio.archivos import MAXIMO_BYTES
from .infraestructura.servidor import crear_ciclo_vida, registrar_respuestas
from .integraciones.cifrado import ClaveCifradoInvalida, obtener_cifrador
from .rutas.administracion import router as router_administracion
from .rutas.autenticacion import crear_router as rutas_autenticacion
from .rutas.campanas import crear_router as rutas_campanas
from .rutas.consultas import crear_router as rutas_consultas
from .rutas.envios import crear_router as rutas_envios
from .rutas.premium import router as router_premium
from .rutas.temporales import router as router_temporales
from .servicios.turnos_confirmacion import TurnosConfirmacion


def crear_aplicacion(
    configuracion: Configuracion | None = None, motor: Engine | None = None
) -> FastAPI:
    configuracion = configuracion or Configuracion.desde_entorno()
    if configuracion.entorno == "produccion" and not configuracion.secreto_sesion:
        raise ValueError("Producción requiere DEBUPA_SECRETO_SESION para firmar las sesiones.")
    if (
        configuracion.google_cliente_id
        and configuracion.google_cliente_secreto
        and not configuracion.secreto_sesion
    ):
        raise ValueError("Google OAuth requiere DEBUPA_SECRETO_SESION.")
    try:
        obtener_cifrador(configuracion.clave_cifrado)
        cifrado_disponible = True
    except ClaveCifradoInvalida:
        cifrado_disponible = False

    motor = motor or crear_motor(configuracion)
    MultiPartParser.spool_max_size = MAXIMO_BYTES + 1
    api = FastAPI(title="API de DEBUPA", version="0.1.0", lifespan=crear_ciclo_vida(configuracion))
    api.state.configuracion = configuracion
    api.state.cifrado_disponible = cifrado_disponible
    api.state.fabrica_sesiones = sessionmaker(motor, expire_on_commit=False)
    api.state.aviso_cola = asyncio.Event()
    api.state.cola_sgva = asyncio.Queue(maxsize=10)
    api.state.tareas_sgva = {}
    api.state.cola_envios = asyncio.Queue(maxsize=10)
    api.state.turnos_confirmacion = TurnosConfirmacion()
    firma_envio = URLSafeTimedSerializer(
        configuracion.secreto_sesion or "solo-pruebas-locales",
        salt="debupa-confirmar-envio",
    )
    api.add_middleware(
        SessionMiddleware,
        secret_key=configuracion.secreto_sesion
        or configuracion.clave_pruebas
        or "clave-sesion-pruebas-locales",
        https_only=configuracion.entorno == "produccion",
        same_site="lax",
        max_age=7 * 24 * 60 * 60,
    )
    registrar_respuestas(api)
    api.include_router(rutas_autenticacion(configuracion, cifrado_disponible))
    api.include_router(rutas_consultas(configuracion, cifrado_disponible))
    api.include_router(rutas_campanas(api, configuracion))
    api.include_router(rutas_envios(api, configuracion, cifrado_disponible, firma_envio))
    api.include_router(router_temporales)
    api.include_router(router_premium)
    api.include_router(router_administracion)
    ruta_frontend = Path(__file__).resolve().parents[2] / "frontend"
    api.mount("/", StaticFiles(directory=ruta_frontend, html=True), name="frontend")
    return api


aplicacion = crear_aplicacion()
