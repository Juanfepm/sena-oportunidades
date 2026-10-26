"""Reglas de exclusión y recontacto para mensajes enviados por DEBUPA."""

from dataclasses import dataclass
from datetime import datetime, timezone

from .fechas import desplazar_meses


@dataclass(frozen=True)
class DecisionContacto:
    permitido: bool
    motivo: str


def hace_seis_meses(fecha: datetime) -> datetime:
    return desplazar_meses(fecha, -6)


def _con_zona(fecha: datetime) -> datetime:
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def evaluar_contacto(
    correo: str,
    exclusiones: set[str],
    ultimo_envio: datetime | None,
    permitir_recontacto: bool,
    fecha_actual: datetime,
) -> DecisionContacto:
    destino = correo.strip().lower()
    if destino in {excluido.strip().lower() for excluido in exclusiones}:
        return DecisionContacto(False, "excluido_por_aprendiz")
    if ultimo_envio is None:
        return DecisionContacto(True, "contacto_nuevo")
    if _con_zona(ultimo_envio) > hace_seis_meses(_con_zona(fecha_actual)):
        return DecisionContacto(False, "contacto_reciente")
    if not permitir_recontacto:
        return DecisionContacto(False, "recontacto_no_autorizado")
    return DecisionContacto(True, "recontacto_autorizado")
