"""Estados y límites controlados por el servidor."""

from enum import StrEnum


class Plan(StrEnum):
    GRATIS = "gratis"
    PREMIUM = "premium"


class EstadoCampana(StrEnum):
    BORRADOR = "borrador"
    EN_COLA = "en_cola"
    CONSULTANDO = "consultando"
    ESPERANDO_CONFIRMACION = "esperando_confirmacion"
    ENVIANDO = "enviando"
    COMPLETADA = "completada"
    CANCELADA = "cancelada"
    ERROR = "error"
    INTERRUMPIDA = "interrumpida"


class EstadoPago(StrEnum):
    PENDIENTE = "pendiente"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"


LIMITES_CONTACTO = {Plan.GRATIS: 8, Plan.PREMIUM: 30}
TARJETAS_RESUMEN = {Plan.GRATIS: 2, Plan.PREMIUM: 30}
