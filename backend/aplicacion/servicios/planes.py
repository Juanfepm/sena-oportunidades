"""Privilegios de campaña de la cuenta de servicio verificada."""

from ..dominio.estados import Plan
from ..modelos import Usuario
from .resumen_correo import CORREO_DEBUPA


def plan_disponible(usuario: Usuario) -> Plan:
    if usuario.es_administrador and usuario.correo_google == CORREO_DEBUPA:
        return Plan.PREMIUM
    return Plan(usuario.plan)
