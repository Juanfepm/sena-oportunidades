"""Ciclo de vida, errores y cabeceras HTTP."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import Response

from ..configuracion import Configuracion
from ..integraciones.contratos import (
    AccesoSGVARestringido,
    IntegracionNoDisponible,
    SGVANoDisponible,
)
from ..modelos import (
    PagoPremium,
)
from ..rutas.autenticacion import pagina_error
from ..servicios.campanas_envio import interrumpir_envios
from ..servicios.temporales import limpiar_expirados
from ..servicios.trabajador_demo import vigilar_cola
from ..servicios.trabajador_envio import vigilar_envios
from ..servicios.trabajador_sgva import interrumpir_sin_credenciales, vigilar_consultas
from .limites import regla_para

MAXIMO_PETICION_TEMPORAL = 11 * 1024 * 1024
POLITICA_CONTENIDO = (
    "default-src 'self'; img-src 'self' data: blob:; frame-src 'self' blob:; "
    "script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def crear_ciclo_vida(configuracion: Configuracion):
    @asynccontextmanager
    async def ciclo_limpieza(api: FastAPI):
        def depurar() -> None:
            try:
                with api.state.fabrica_sesiones() as sesion:
                    limpiar_expirados(sesion)
            except SQLAlchemyError:
                pass  # La API informará de la caída al recibir una solicitud.

        async def repetir() -> None:
            while True:
                await asyncio.sleep(15 * 60)
                await asyncio.to_thread(depurar)

        await asyncio.to_thread(depurar)
        tarea = asyncio.create_task(repetir())
        if configuracion.sgva_activo:
            with api.state.fabrica_sesiones() as sesion:
                interrumpir_sin_credenciales(sesion)
            trabajador = asyncio.create_task(
                vigilar_consultas(
                    api.state.fabrica_sesiones,
                    api.state.cola_sgva,
                    configuracion.gemini_clave,
                    api.state.tareas_sgva,
                )
            )
        else:
            trabajador = asyncio.create_task(
                vigilar_cola(api.state.fabrica_sesiones, api.state.aviso_cola)
            )
        with api.state.fabrica_sesiones() as sesion:
            interrumpir_envios(sesion)
            sesion.execute(
                update(PagoPremium)
                .where(PagoPremium.notificacion_estado == "en_proceso")
                .values(notificacion_estado="incierto")
            )
            sesion.commit()
        trabajador_envios = asyncio.create_task(
            vigilar_envios(api.state.fabrica_sesiones, configuracion, api.state.cola_envios)
        )
        try:
            yield
        finally:
            for activa in (tarea, trabajador, trabajador_envios):
                activa.cancel()
            for activa in (tarea, trabajador, trabajador_envios):
                with suppress(asyncio.CancelledError):
                    await activa

    return ciclo_limpieza


def registrar_respuestas(api: FastAPI) -> None:
    @api.exception_handler(AccesoSGVARestringido)
    async def acceso_sgva_restringido(_: Request, __: AccesoSGVARestringido) -> JSONResponse:
        return JSONResponse(
            {
                "codigo": "sgva_restringido",
                "detail": "SGVA no permitió consultar empresas para esta cuenta.",
            },
            status_code=409,
        )

    @api.exception_handler(SGVANoDisponible)
    async def sgva_no_disponible(_: Request, __: SGVANoDisponible) -> JSONResponse:
        return JSONResponse(
            {
                "codigo": "sgva_no_disponible",
                "detail": "El servicio SGVA no respondió. Inténtalo más tarde.",
            },
            status_code=503,
        )

    @api.exception_handler(IntegracionNoDisponible)
    async def integracion_no_disponible(_: Request, __: IntegracionNoDisponible) -> JSONResponse:
        return JSONResponse(
            {
                "codigo": "servicio_no_disponible",
                "detail": "Un servicio necesario no respondió. Inténtalo más tarde.",
            },
            status_code=503,
        )

    @api.middleware("http")
    async def proteger_respuestas(peticion: Request, siguiente) -> Response:
        try:
            origen = peticion.headers.get("origin")
            permitido = api.state.configuracion.origen_publico or str(peticion.base_url).rstrip(
                "/"
            )
            if (
                peticion.url.path.startswith("/api/v1/")
                and origen is not None
                and origen != permitido
            ):
                respuesta = JSONResponse({"detail": "Origen no autorizado."}, status_code=403)
            elif regla := regla_para(peticion.method, peticion.url.path):
                operacion, cantidad, ventana = regla
                cliente = peticion.session.get("usuario_id") or (
                    peticion.client.host if peticion.client else "desconocido"
                )
                espera = await api.state.limites.comprobar(cliente, operacion, cantidad, ventana)
                if espera:
                    respuesta = JSONResponse(
                        {"detail": "Demasiadas solicitudes. Inténtalo más tarde."},
                        status_code=429,
                        headers={"Retry-After": str(espera)},
                    )
                else:
                    respuesta = await _procesar_peticion(peticion, siguiente)
            else:
                respuesta = await _procesar_peticion(peticion, siguiente)
        except SQLAlchemyError:
            if (
                peticion.method == "GET"
                and peticion.url.path == "/api/v1/autenticacion/google/callback"
            ):
                respuesta = pagina_error("base-datos")
            else:
                respuesta = JSONResponse(
                    {
                        "detail": "La base de datos no está disponible.",
                        "codigo": "base_datos",
                    },
                    status_code=503,
                )
        respuesta.headers["Cache-Control"] = "no-store"
        respuesta.headers["Content-Security-Policy"] = POLITICA_CONTENIDO
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        return respuesta

    async def _procesar_peticion(peticion: Request, siguiente) -> Response:
        if peticion.method == "POST" and peticion.url.path == "/api/v1/pagos-premium":
            longitud = peticion.headers.get("content-length", "")
            if not longitud.isdigit():
                respuesta = JSONResponse(
                    {"detail": "Indica el tamaño del comprobante."}, status_code=411
                )
            elif int(longitud) > 3 * 1024 * 1024:
                respuesta = JSONResponse(
                    {"detail": "El comprobante supera el límite."}, status_code=413
                )
            else:
                respuesta = await siguiente(peticion)
        elif peticion.method == "PUT" and peticion.url.path.endswith("/contenido"):
            longitud = peticion.headers.get("content-length", "")
            if not longitud.isdigit():
                respuesta = JSONResponse(
                    {"detail": "Indica el tamaño total de la solicitud."},
                    status_code=411,
                )
            elif int(longitud) > MAXIMO_PETICION_TEMPORAL:
                respuesta = JSONResponse(
                    {"detail": "El contenido supera el límite permitido."},
                    status_code=413,
                )
            else:
                respuesta = await siguiente(peticion)
        else:
            respuesta = await siguiente(peticion)
        return respuesta
