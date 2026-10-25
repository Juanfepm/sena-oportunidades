"""Contratos de los servicios externos sin almacenar credenciales en modelos."""

from dataclasses import dataclass
from typing import Protocol


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
    modalidad_confirmada: bool


class ConsultorSGVA(Protocol):
    def buscar(self, numero_documento: str, clave_temporal: str, departamento: str, ciudad: str) -> list[OfertaSGVA]: ...


class ClasificadorIA(Protocol):
    def evaluar(self, perfil_temporal: str, oferta: OfertaSGVA) -> EvaluacionIA: ...


class EmisorGmail(Protocol):
    def enviar(self, correo_destino: str, asunto: str, cuerpo: str, adjuntos_temporales: list[bytes]) -> str: ...


class IntegracionNoDisponible(RuntimeError):
    pass


class AccesoSGVARestringido(RuntimeError):
    """SGVA rechazó la consulta; la causa concreta aún debe confirmarse allí."""


class SGVANoDisponible(IntegracionNoDisponible):
    """La plataforma SGVA no respondió a la consulta."""
