"""Revisión final, selección y autorización de envíos."""

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import Response

from ..base_datos import obtener_sesion
from ..configuracion import Configuracion
from ..dominio.estados import EstadoCampana
from ..esquemas import (
    SolicitudConfirmacionEnvio,
    SolicitudSeleccion,
)
from ..integraciones.cifrado import ClaveCifradoInvalida
from ..modelos import Campana, Destinatario, HistorialEnvio, Usuario
from ..seguridad import obtener_usuario_actual, verificar_csrf
from ..servicios.campanas import (
    consultar_campana,
)
from ..servicios.campanas_envio import (
    EnvioNoPermitido,
    autorizar_envio,
    huella_preparacion,
    preparar_envio,
)
from ..servicios.planes import plan_disponible
from ..servicios.selecciones import SeleccionInvalida, guardar_seleccion


def crear_router(
    api: FastAPI,
    configuracion: Configuracion,
    cifrado_disponible: bool,
    firma_envio: URLSafeTimedSerializer,
) -> APIRouter:
    router = APIRouter()

    @router.put("/api/v1/campanas/{campana_id}/seleccion")
    def guardar_seleccion_campana(
        campana_id: str,
        solicitud: SolicitudSeleccion,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, int]:
        campana = sesion.scalar(
            select(Campana)
            .where(
                Campana.id == campana_id,
                Campana.usuario_id == usuario.id,
            )
            .with_for_update()
        )
        if campana is None:
            raise HTTPException(404, "Campaña no encontrada.")
        if campana.estado != EstadoCampana.ESPERANDO_CONFIRMACION:
            raise HTTPException(409, "La campaña aún no admite guardar destinatarios.")
        try:
            cantidad = guardar_seleccion(
                sesion, campana, plan_disponible(usuario), solicitud.destinatarios
            )
        except SeleccionInvalida as error:
            raise HTTPException(422, str(error)) from error
        return {"seleccionados": cantidad}

    @router.post("/api/v1/campanas/{campana_id}/turno-confirmacion")
    def solicitar_turno_confirmacion(
        campana_id: str,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, str | int]:
        campana = consultar_campana(sesion, usuario, campana_id)
        if campana is None:
            raise HTTPException(404, "Campaña no encontrada.")
        if campana.estado != EstadoCampana.ESPERANDO_CONFIRMACION:
            raise HTTPException(409, "Esta campaña ya no espera confirmación.")
        if not campana.seleccion_guardada:
            raise HTTPException(409, "Guarda tu selección antes de revisar el envío.")
        return api.state.turnos_confirmacion.solicitar(campana.id)

    @router.delete("/api/v1/campanas/{campana_id}/turno-confirmacion", status_code=204)
    def liberar_turno_confirmacion(
        campana_id: str,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> None:
        campana = consultar_campana(sesion, usuario, campana_id)
        if campana is None:
            raise HTTPException(404, "Campaña no encontrada.")
        api.state.turnos_confirmacion.liberar(campana.id)

    @router.get("/api/v1/campanas/{campana_id}/preparacion-envio")
    def preparacion_envio(
        campana_id: str,
        respuesta: Response,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict:
        campana = consultar_campana(sesion, usuario, campana_id)
        if campana is None:
            raise HTTPException(404, "Campaña no encontrada.")
        if not api.state.turnos_confirmacion.vigente(campana.id):
            raise HTTPException(409, "Espera tu turno para revisar el envío.")
        if not configuracion.sgva_activo or not cifrado_disponible:
            raise HTTPException(503, "El envío de campañas no está configurado.")
        try:
            vista = preparar_envio(sesion, campana, usuario, configuracion.clave_cifrado)
        except (EnvioNoPermitido, ClaveCifradoInvalida) as error:
            raise HTTPException(409, str(error)) from error
        respuesta.headers["Cache-Control"] = "no-store"
        vista["confirmacion"] = firma_envio.dumps(
            {
                "campana": campana.id,
                "usuario": usuario.id,
                "huella": huella_preparacion(vista),
            }
        )
        return vista

    @router.post("/api/v1/campanas/{campana_id}/enviar", status_code=202)
    async def confirmar_envio(
        campana_id: str,
        solicitud: SolicitudConfirmacionEnvio,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, int]:
        if (
            not configuracion.sgva_activo
            or not cifrado_disponible
            or not configuracion.google_cliente_id
        ):
            raise HTTPException(503, "El envío de campañas no está configurado.")
        if api.state.cola_envios.full():
            raise HTTPException(429, "La cola de envíos está llena.")
        campana = sesion.scalar(
            select(Campana)
            .where(
                Campana.id == campana_id,
                Campana.usuario_id == usuario.id,
            )
            .with_for_update()
        )
        if campana is None:
            raise HTTPException(404, "Campaña no encontrada.")
        try:
            firma = firma_envio.loads(solicitud.confirmacion, max_age=600)
        except (BadSignature, SignatureExpired) as error:
            raise HTTPException(
                409, "La revisión final venció. Abre de nuevo la lista antes de enviar."
            ) from error
        if firma.get("campana") != campana.id or firma.get("usuario") != usuario.id:
            raise HTTPException(409, "La confirmación no corresponde a esta campaña.")
        if not api.state.turnos_confirmacion.vigente(campana.id):
            raise HTTPException(409, "Tu turno de revisión venció. Abre de nuevo la lista.")
        try:
            cantidad = autorizar_envio(
                sesion,
                campana,
                usuario,
                configuracion.clave_cifrado,
                solicitud.destinatarios,
                firma["huella"],
            )
        except (EnvioNoPermitido, ClaveCifradoInvalida) as error:
            raise HTTPException(409, str(error)) from error
        api.state.cola_envios.put_nowait(campana.id)
        api.state.turnos_confirmacion.liberar(campana.id)
        return {"autorizados": cantidad}

    @router.get("/api/v1/campanas/{campana_id}/resultado-envio")
    def resultado_envio(
        campana_id: str,
        respuesta: Response,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[dict]:
        campana = consultar_campana(sesion, usuario, campana_id)
        if campana is None:
            raise HTTPException(404, "Campaña no encontrada.")
        respuesta.headers["Cache-Control"] = "no-store"
        consulta = (
            select(HistorialEnvio, Destinatario)
            .join(
                Destinatario,
                HistorialEnvio.destinatario_id == Destinatario.id,
            )
            .where(HistorialEnvio.campana_id == campana.id)
            .order_by(HistorialEnvio.enviado_en)
        )
        return [
            {
                "nombre_empresa": destino.nombre_empresa,
                "correo": envio.correo,
                "telefono_original": destino.telefono_original,
                "motivo": destino.motivo,
                "puntuacion": destino.puntuacion,
                "estado": envio.estado,
                "enviado_en": envio.enviado_en.isoformat() if envio.estado == "enviado" else None,
            }
            for envio, destino in sesion.execute(consulta)
        ]

    return router
