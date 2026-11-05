"""Precio de Premium durante el año de lanzamiento y después de él."""

from datetime import datetime
from zoneinfo import ZoneInfo

ZONA_COLOMBIA = ZoneInfo("America/Bogota")
FIN_PROMOCION = datetime(2027, 11, 5, tzinfo=ZONA_COLOMBIA)
PRECIO_LANZAMIENTO_COP = 8000
PRECIO_REGULAR_COP = 10000


def precio_premium(fecha: datetime) -> int:
    """Devuelve el importe anunciado al crear una solicitud."""
    if fecha.tzinfo is None:
        raise ValueError("La fecha del precio debe incluir zona horaria.")
    return (
        PRECIO_LANZAMIENTO_COP
        if fecha.astimezone(ZONA_COLOMBIA) < FIN_PROMOCION
        else PRECIO_REGULAR_COP
    )
