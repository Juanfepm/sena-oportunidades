"""Catálogo DIVIPOLA compartido con el selector del frontend."""

import json
from pathlib import Path


RUTA_CATALOGO = Path(__file__).with_name("municipios.json")
MUNICIPIOS_POR_DEPARTAMENTO: dict[str, list[str]] = json.loads(
    RUTA_CATALOGO.read_text(encoding="utf-8")
)["departamentos"]
