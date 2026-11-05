"""Revisión administrativa de pagos y acceso al comprobante."""

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..base_datos import obtener_sesion
from ..dominio.estados import EstadoPago
from ..integraciones.cifrado import ClaveCifradoInvalida, obtener_cifrador
from ..integraciones.gmail import (
    EnvioGmailNoConfirmado,
    GmailNoDisponible,
    PermisoGmailInvalido,
    enviar_gmail,
)
from ..modelos import PagoPremium, Usuario
from ..seguridad import obtener_administrador, verificar_csrf
from ..servicios.avisos_premium import notificar_decision
from ..servicios.conexiones_gmail import obtener_conexion_resumen
from ..servicios.correo_marca import aviso_html
from ..servicios.estadisticas_administracion import obtener_estadisticas
from ..servicios.pagos import verificar_pago
from ..servicios.resumen_correo import CORREO_DEBUPA

router = APIRouter(prefix="/api/v1")


class DecisionPago(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aprobar: bool


@router.get("/administracion/resumen")
def resumen_administracion(
    _: Usuario = Depends(obtener_administrador),
    sesion: Session = Depends(obtener_sesion),
) -> dict:
    estadisticas = obtener_estadisticas(sesion)
    pagos = sesion.execute(
        select(PagoPremium, Usuario)
        .join(Usuario, Usuario.id == PagoPremium.usuario_id)
        .where(PagoPremium.estado == EstadoPago.PENDIENTE)
        .order_by(PagoPremium.creado_en)
        .limit(100)
    ).all()
    avisos = sesion.execute(
        select(PagoPremium, Usuario)
        .join(Usuario, Usuario.id == PagoPremium.usuario_id)
        .where(
            PagoPremium.estado != EstadoPago.PENDIENTE,
            PagoPremium.notificacion_estado.in_(("pendiente", "incierto", "en_proceso")),
        )
        .order_by(PagoPremium.verificado_en.desc())
        .limit(50)
    ).all()
    conexion = obtener_conexion_resumen(sesion)
    return {
        **estadisticas,
        "correo_servicio_conectado": bool(conexion),
        "avisos_pendientes": [
            {"id": pago.id, "correo": usuario.correo_google, "estado": pago.notificacion_estado}
            for pago, usuario in avisos
        ],
        "solicitudes": [
            {
                "id": pago.id,
                "nombre": usuario.nombre_google or "Aprendiz",
                "correo": usuario.correo_google,
                "importe_cop": pago.importe_cop,
                "creado_en": pago.creado_en.isoformat(),
                "notificacion_estado": pago.notificacion_estado,
            }
            for pago, usuario in pagos
        ],
    }


@router.get("/administracion/pagos/{pago_id}/comprobante")
def ver_comprobante(
    pago_id: str,
    request: Request,
    _: Usuario = Depends(obtener_administrador),
    sesion: Session = Depends(obtener_sesion),
) -> Response:
    pago = sesion.get(PagoPremium, pago_id)
    if pago is None or pago.estado != EstadoPago.PENDIENTE or not pago.comprobante_cifrado:
        raise HTTPException(404, "El comprobante ya no está disponible.")
    try:
        contenido = obtener_cifrador(request.app.state.configuracion.clave_cifrado).decrypt(
            pago.comprobante_cifrado
        )
    except (ClaveCifradoInvalida, InvalidToken) as error:
        raise HTTPException(503, "No se pudo abrir el comprobante cifrado.") from error
    return Response(
        contenido,
        media_type=pago.comprobante_tipo,
        headers={"Cache-Control": "no-store", "Content-Disposition": "inline"},
    )


@router.post("/administracion/pagos/{pago_id}/decision")
async def decidir_pago(
    pago_id: str,
    decision: DecisionPago,
    request: Request,
    _: None = Depends(verificar_csrf),
    administrador: Usuario = Depends(obtener_administrador),
    sesion: Session = Depends(obtener_sesion),
) -> dict[str, str]:
    pago = sesion.scalar(select(PagoPremium).where(PagoPremium.id == pago_id).with_for_update())
    if pago is None:
        raise HTTPException(404, "Solicitud no encontrada.")
    if pago.estado != EstadoPago.PENDIENTE:
        raise HTTPException(409, "La solicitud ya fue revisada.")
    verificar_pago(sesion, pago, administrador, decision.aprobar)
    sesion.commit()
    await notificar_decision(request.app.state.configuracion, sesion, pago)
    return {"estado": pago.estado, "notificacion_estado": pago.notificacion_estado}


@router.post("/administracion/pagos/{pago_id}/notificar")
async def reintentar_aviso(
    pago_id: str,
    request: Request,
    _: None = Depends(verificar_csrf),
    __: Usuario = Depends(obtener_administrador),
    sesion: Session = Depends(obtener_sesion),
) -> dict[str, str]:
    pago = sesion.scalar(select(PagoPremium).where(PagoPremium.id == pago_id).with_for_update())
    if pago is None or pago.estado == EstadoPago.PENDIENTE:
        raise HTTPException(404, "Decisión no encontrada.")
    if pago.notificacion_estado != "pendiente":
        raise HTTPException(409, "Comprueba Enviados de DEBUPA antes de intentar otro aviso.")
    await notificar_decision(request.app.state.configuracion, sesion, pago)
    return {"notificacion_estado": pago.notificacion_estado}


@router.post("/administracion/correo/prueba")
async def probar_correo_servicio(
    request: Request,
    _: None = Depends(verificar_csrf),
    __: Usuario = Depends(obtener_administrador),
    sesion: Session = Depends(obtener_sesion),
) -> dict[str, str]:
    conexion = obtener_conexion_resumen(sesion)
    if conexion is None:
        raise HTTPException(409, "Conecta primero la cuenta de DEBUPA con Google.")
    try:
        await enviar_gmail(
            request.app.state.configuracion,
            conexion.token_renovacion_cifrado,
            CORREO_DEBUPA,
            CORREO_DEBUPA,
            "DEBUPA · Prueba del correo de servicio",
            "El correo de servicio puede enviar los resúmenes y avisos Premium.",
            (),
            aviso_html(
                "Correo de servicio conectado",
                "El correo de servicio puede enviar los resúmenes y avisos Premium.",
            ),
        )
    except (
        EnvioGmailNoConfirmado,
        PermisoGmailInvalido,
        GmailNoDisponible,
        ClaveCifradoInvalida,
    ) as error:
        raise HTTPException(
            503, "Gmail no confirmó la prueba. Revisa Enviados de DEBUPA."
        ) from error
    return {"estado": "confirmado"}
