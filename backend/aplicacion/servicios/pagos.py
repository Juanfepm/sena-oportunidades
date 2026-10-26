"""Aprobación humana: jamás se confía en una captura por sí sola."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..dominio.estados import EstadoPago, Plan
from ..dominio.fechas import desplazar_meses
from ..modelos import PagoPremium, Usuario, ahora_utc


def sumar_tres_meses(fecha: datetime) -> datetime:
    return desplazar_meses(fecha, 3)


def verificar_pago(
    sesion: Session, pago: PagoPremium, administrador: Usuario, aprobar: bool
) -> None:
    if not administrador.es_administrador:
        raise PermissionError("Solo un administrador puede verificar pagos.")
    if pago.estado != EstadoPago.PENDIENTE:
        raise ValueError("La solicitud de pago ya fue revisada.")
    aprendiz = sesion.get(Usuario, pago.usuario_id)
    if aprendiz is None:
        raise ValueError("No existe el aprendiz de la solicitud.")
    pago.estado = EstadoPago.APROBADO if aprobar else EstadoPago.RECHAZADO
    pago.verificado_por = administrador.id
    pago.verificado_en = ahora_utc()
    pago.comprobante_cifrado = None
    if aprobar:
        aprendiz.plan = Plan.PREMIUM
        actual = aprendiz.premium_hasta
        if actual is not None and actual.tzinfo is None:
            actual = actual.replace(tzinfo=timezone.utc)
        aprendiz.premium_hasta = sumar_tres_meses(
            max(actual or pago.verificado_en, pago.verificado_en)
        )
    sesion.flush()
