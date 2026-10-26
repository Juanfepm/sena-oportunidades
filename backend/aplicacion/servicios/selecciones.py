"""Guarda destinatarios revisados sin permitir saltar límites ni ofertas ocultas."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dominio.estados import LIMITES_CONTACTO, Plan
from ..esquemas import PATRON_CORREO
from ..modelos import Campana, Destinatario


class SeleccionInvalida(ValueError):
    """Se intentó guardar un destinatario fuera de las ofertas permitidas."""


def guardar_seleccion(
    sesion: Session, campana: Campana, plan: Plan, identificadores: list[str]
) -> int:
    if len(identificadores) > LIMITES_CONTACTO[plan]:
        raise SeleccionInvalida(
            f"El plan {plan.value} permite hasta {LIMITES_CONTACTO[plan]} empresas."
        )

    destinatarios = list(
        sesion.scalars(
            select(Destinatario)
            .where(Destinatario.campana_id == campana.id)
            .order_by(
                Destinatario.puntuacion.desc().nulls_last(),
                Destinatario.id,
            )
        )
    )
    visibles = destinatarios[:9] if plan == Plan.GRATIS else destinatarios
    permitidos = {
        destino.id
        for destino in visibles
        if destino.correo and PATRON_CORREO.fullmatch(destino.correo)
    }
    elegidos = set(identificadores)
    if not elegidos.issubset(permitidos):
        raise SeleccionInvalida(
            "La selección contiene empresas ocultas, sin correo o de otra campaña."
        )

    for destino in destinatarios:
        destino.seleccionado = destino.id in elegidos
    campana.seleccion_guardada = True
    sesion.commit()
    return len(elegidos)
