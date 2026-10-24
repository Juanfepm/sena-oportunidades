"""Límites previos; el almacenamiento futuro también deberá inspeccionar contenido."""

from dataclasses import dataclass
from pathlib import PurePath


TIPOS_PERMITIDOS = {
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".txt": {"text/plain"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
}
MAXIMO_ARCHIVOS = 2
MAXIMO_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class ArchivoAdjunto:
    nombre: str
    tipo_declarado: str
    tamano_bytes: int


def validar_adjuntos(archivos: list[ArchivoAdjunto]) -> None:
    if len(archivos) > MAXIMO_ARCHIVOS:
        raise ValueError("Solo se permiten dos adjuntos.")
    for archivo in archivos:
        nombre = PurePath(archivo.nombre).name
        extension = PurePath(nombre).suffix.lower()
        if nombre != archivo.nombre or extension not in TIPOS_PERMITIDOS:
            raise ValueError("Nombre o extensión de adjunto no permitido.")
        if archivo.tipo_declarado not in TIPOS_PERMITIDOS[extension]:
            raise ValueError("El tipo declarado no coincide con la extensión.")
        if not 0 < archivo.tamano_bytes <= MAXIMO_BYTES:
            raise ValueError("El adjunto debe medir entre 1 byte y 5 MB.")
