"""Normalización de texto antes de persistirlo o usarlo en mensajes."""

import re
from unicodedata import normalize

PATRON_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
PATRON_CONTROL_TEXTO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PATRON_DIRECCIONAL = re.compile(r"[\u202a-\u202e\u2066-\u2069]")


def limpiar_texto(valor: str, *, multilinea: bool = False) -> str:
    """Rechaza controles ocultos y conserva el contenido visible original."""
    limpio = normalize("NFC", valor)
    patron = PATRON_CONTROL_TEXTO if multilinea else PATRON_CONTROL
    if patron.search(limpio) or PATRON_DIRECCIONAL.search(limpio):
        raise ValueError("El texto contiene caracteres de control o direccionales.")
    return limpio


def limpiar_texto_externo(valor: str, *, multilinea: bool = False) -> str:
    """Quita controles de fuentes externas sin impedir que se muestre la oferta."""
    limpio = normalize("NFC", valor)
    patron = PATRON_CONTROL_TEXTO if multilinea else PATRON_CONTROL
    return PATRON_DIRECCIONAL.sub("", patron.sub(" ", limpio)).strip()
