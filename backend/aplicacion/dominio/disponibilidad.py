"""Espera mensual del plan gratis después de un envío real."""

from datetime import datetime, timedelta, timezone

from .estados import Plan
from .fechas import desplazar_meses

ZONA_COLOMBIA = timezone(timedelta(hours=-5))


def siguiente_mes(fecha: datetime) -> datetime:
    return desplazar_meses(fecha, 1)


def proxima_busqueda(
    plan: Plan, ultimo_envio: datetime | None, ahora: datetime
) -> datetime | None:
    if plan == Plan.PREMIUM or ultimo_envio is None:
        return None
    fecha_envio = (
        ultimo_envio if ultimo_envio.tzinfo else ultimo_envio.replace(tzinfo=timezone.utc)
    )
    fecha_actual = ahora if ahora.tzinfo else ahora.replace(tzinfo=timezone.utc)
    siguiente = siguiente_mes(fecha_envio.astimezone(ZONA_COLOMBIA)).astimezone(timezone.utc)
    return siguiente if siguiente > fecha_actual else None
