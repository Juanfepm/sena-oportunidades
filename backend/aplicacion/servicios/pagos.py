"""Aprobación humana: jamás se confía en una captura por sí sola."""

from sqlalchemy.orm import Session

from ..dominio.estados import EstadoPago, Plan
from ..modelos import PagoPremium, Usuario, ahora_utc


def verificar_pago(sesion: Session, pago: PagoPremium, administrador: Usuario, aprobar: bool) -> None:
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
    if aprobar:
        aprendiz.plan = Plan.PREMIUM
    sesion.flush()
