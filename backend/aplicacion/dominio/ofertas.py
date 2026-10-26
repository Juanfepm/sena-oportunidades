"""Datos y reglas de ofertas, independientes de proveedores externos."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OfertaSGVA:
    nombre_empresa: str
    correo: str | None
    telefono_original: str | None
    descripcion: str
    departamento: str
    ciudad: str
    dias_publicada: int | None


@dataclass(frozen=True)
class EvaluacionIA:
    puntuacion: int
    motivo: str
    modalidad: str


def cumple_filtros(
    oferta: OfertaSGVA,
    modalidad: str,
    departamento: str,
    ciudad: str,
    antiguedad_dias: int,
) -> bool:
    if not oferta.correo or oferta.dias_publicada is None:
        return False
    if not 0 <= oferta.dias_publicada <= antiguedad_dias:
        return False
    if modalidad == "remoto":
        return True  # Posibilidad, no confirmación de trabajo remoto.
    if departamento != "todos" and oferta.departamento != departamento:
        return False
    return ciudad == "todas" or oferta.ciudad == ciudad
