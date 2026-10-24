"""La clasificación futura aporta puntuación y motivo; aquí se aplican límites."""

from dataclasses import dataclass

from .estados import LIMITES_CONTACTO, Plan


@dataclass(frozen=True)
class Coincidencia:
    correo: str
    puntuacion: int
    motivo: str
    modalidad_confirmada: bool


@dataclass(frozen=True)
class Seleccion:
    alta: tuple[Coincidencia, ...]
    por_revisar: tuple[Coincidencia, ...]


def separar_coincidencias(coincidencias: list[Coincidencia], plan: Plan) -> Seleccion:
    unicas: dict[str, Coincidencia] = {}
    for coincidencia in coincidencias:
        if not 0 <= coincidencia.puntuacion <= 100:
            raise ValueError("La puntuación debe estar entre 0 y 100.")
        correo = coincidencia.correo.strip().lower()
        if correo not in unicas or coincidencia.puntuacion > unicas[correo].puntuacion:
            unicas[correo] = coincidencia

    ordenadas = sorted(unicas.values(), key=lambda oferta: oferta.puntuacion, reverse=True)
    altas = [oferta for oferta in ordenadas if oferta.puntuacion >= 80 and oferta.modalidad_confirmada]
    dudosas = [oferta for oferta in ordenadas if oferta.puntuacion >= 60 and oferta not in altas]
    return Seleccion(tuple(altas[: LIMITES_CONTACTO[plan]]), tuple(dudosas))
