"""Filtros objetivos anteriores a la evaluación por IA."""

from ..integraciones.contratos import OfertaSGVA


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
