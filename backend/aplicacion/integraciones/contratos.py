"""Errores de los proveedores externos.

Las reexportaciones conservan la compatibilidad de módulos anteriores.
"""

from ..dominio.ofertas import EvaluacionIA, OfertaSGVA

__all__ = ["EvaluacionIA", "OfertaSGVA"]


class IntegracionNoDisponible(RuntimeError):
    pass


class AccesoSGVARestringido(RuntimeError):
    """SGVA rechazó la consulta; la causa concreta aún debe confirmarse allí."""


class SGVANoDisponible(IntegracionNoDisponible):
    """La plataforma SGVA no respondió a la consulta."""


class SGVAEntornoIncompatible(SGVANoDisponible):
    """El servidor no puede iniciar Playwright con su bucle actual."""
