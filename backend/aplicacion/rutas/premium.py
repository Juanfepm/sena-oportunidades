"""Solicitud Premium y carga privada del comprobante."""

from datetime import datetime, timezone
from hashlib import sha256

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..base_datos import obtener_sesion
from ..dominio.estados import EstadoPago
from ..dominio.precios import FIN_PROMOCION, PRECIO_REGULAR_COP, precio_premium
from ..integraciones.cifrado import ClaveCifradoInvalida, obtener_cifrador
from ..modelos import PagoPremium, Usuario
from ..seguridad import obtener_usuario_actual, verificar_csrf

router = APIRouter(prefix="/api/v1")
MAXIMO_COMPROBANTE = 2 * 1024 * 1024


def _tipo_comprobante(contenido: bytes) -> str | None:
    if contenido.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in contenido[-24:]:
        return "image/png"
    if contenido.startswith(b"\xff\xd8\xff") and contenido.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if contenido.startswith(b"%PDF-") and b"%%EOF" in contenido[-1024:]:
        return "application/pdf"
    return None


@router.get("/pagos-premium/precio")
def consultar_precio() -> dict[str, int | str | None]:
    importe = precio_premium(datetime.now(timezone.utc))
    return {
        "importe_cop": importe,
        "precio_regular_cop": PRECIO_REGULAR_COP,
        "promocion_hasta": FIN_PROMOCION.isoformat() if importe != PRECIO_REGULAR_COP else None,
    }


@router.get("/pagos-premium/estado")
def estado_pago(
    usuario: Usuario = Depends(obtener_usuario_actual), sesion: Session = Depends(obtener_sesion)
) -> dict:
    pago = sesion.scalar(
        select(PagoPremium)
        .where(PagoPremium.usuario_id == usuario.id)
        .order_by(PagoPremium.creado_en.desc(), PagoPremium.id.desc())
        .limit(1)
    )
    hasta = usuario.premium_hasta
    if hasta is not None and hasta.tzinfo is None:
        hasta = hasta.replace(tzinfo=timezone.utc)
    return {
        "estado": pago.estado if pago else None,
        "plan": usuario.plan,
        "premium_hasta": hasta.isoformat() if hasta else None,
    }


@router.post("/pagos-premium", status_code=201)
async def solicitar_premium(
    request: Request,
    comprobante: UploadFile = File(...),
    acepta_condiciones: bool = Form(...),
    _: None = Depends(verificar_csrf),
    usuario: Usuario = Depends(obtener_usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> dict[str, str]:
    if not usuario.correo_google or not usuario.identificador_externo.startswith("google:"):
        raise HTTPException(401, "Inicia sesión con tu cuenta de Google.")
    if not acepta_condiciones:
        raise HTTPException(422, "Debes aceptar los términos y la política de datos.")
    if sesion.scalar(
        select(PagoPremium.id)
        .where(PagoPremium.usuario_id == usuario.id, PagoPremium.estado == EstadoPago.PENDIENTE)
        .limit(1)
    ):
        raise HTTPException(409, "Ya tienes un comprobante pendiente de revisión.")
    if comprobante.content_type not in {"image/png", "image/jpeg", "application/pdf"}:
        raise HTTPException(422, "Adjunta un comprobante PNG, JPG o PDF.")
    contenido = await comprobante.read(MAXIMO_COMPROBANTE + 1)
    if not contenido or len(contenido) > MAXIMO_COMPROBANTE:
        raise HTTPException(413, "El comprobante debe pesar como máximo 2 MB.")
    tipo = _tipo_comprobante(contenido)
    if tipo != comprobante.content_type:
        raise HTTPException(422, "El archivo no parece un PNG, JPG o PDF válido.")
    try:
        cifrado = obtener_cifrador(request.app.state.configuracion.clave_cifrado).encrypt(
            contenido
        )
    except ClaveCifradoInvalida as error:
        raise HTTPException(503, "El almacenamiento privado no está configurado.") from error
    huella = sha256(contenido).hexdigest()
    if sesion.scalar(
        select(PagoPremium.id).where(PagoPremium.referencia_comprobante == huella).limit(1)
    ):
        raise HTTPException(409, "Este comprobante ya fue recibido.")
    pago = PagoPremium(
        usuario_id=usuario.id,
        importe_cop=precio_premium(datetime.now(timezone.utc)),
        estado=EstadoPago.PENDIENTE,
        referencia_comprobante=huella,
        comprobante_cifrado=cifrado,
        comprobante_tipo=tipo,
    )
    sesion.add(pago)
    try:
        sesion.commit()
    except IntegrityError as error:
        sesion.rollback()
        raise HTTPException(409, "Ya tienes un comprobante pendiente de revisión.") from error
    return {"id": pago.id, "estado": pago.estado}
