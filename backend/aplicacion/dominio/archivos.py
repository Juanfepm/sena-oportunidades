"""Límites y firmas básicas de los archivos que se guardan temporalmente."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath, PureWindowsPath
from unicodedata import category
from zipfile import BadZipFile, ZipFile

from .estados import LIMITES_ARCHIVOS, Plan


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
MAXIMO_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class ArchivoAdjunto:
    nombre: str
    tipo_declarado: str
    tamano_bytes: int


def validar_adjuntos(archivos: list[ArchivoAdjunto], plan: Plan = Plan.GRATIS) -> None:
    limite = LIMITES_ARCHIVOS[plan]
    if len(archivos) > limite:
        raise ValueError(f"El plan {plan} permite hasta {limite} adjuntos.")
    for archivo in archivos:
        nombre = archivo.nombre
        extension = PurePosixPath(nombre).suffix.lower()
        if (
            PurePosixPath(nombre).name != nombre
            or PureWindowsPath(nombre).name != nombre
            or len(nombre) > 180
            or any(ord(caracter) < 32 or category(caracter) == "Cf" for caracter in nombre)
            or extension not in TIPOS_PERMITIDOS
        ):
            raise ValueError("Nombre o extensión de adjunto no permitido.")
        if archivo.tipo_declarado not in TIPOS_PERMITIDOS[extension]:
            raise ValueError("El tipo declarado no coincide con la extensión.")
        if not 0 < archivo.tamano_bytes <= MAXIMO_BYTES:
            raise ValueError("El adjunto debe medir entre 1 byte y 5 MB.")


def validar_contenido(nombre: str, contenido: bytes) -> None:
    """Comprueba firmas, sin descomprimir ni ejecutar el archivo."""
    extension = PurePosixPath(nombre).suffix.lower()
    firmas = {
        ".pdf": contenido.startswith(b"%PDF-"),
        ".doc": contenido.startswith(bytes.fromhex("D0CF11E0A1B11AE1")),
        ".jpg": contenido.startswith(bytes.fromhex("FFD8FF")),
        ".jpeg": contenido.startswith(bytes.fromhex("FFD8FF")),
        ".png": contenido.startswith(bytes.fromhex("89504E470D0A1A0A")),
        ".webp": contenido.startswith(b"RIFF") and contenido[8:12] == b"WEBP",
    }
    if extension == ".txt":
        try:
            texto = contenido.decode("utf-8-sig")
            valido = "\x00" not in texto
        except UnicodeDecodeError:
            valido = False
    elif extension == ".docx":
        try:
            with ZipFile(BytesIO(contenido)) as documento:
                valido = {"[Content_Types].xml", "word/document.xml"}.issubset(documento.namelist())
        except (BadZipFile, ValueError):
            valido = False
    else:
        valido = firmas.get(extension, False)
    if not valido:
        raise ValueError("El contenido del adjunto no corresponde al formato indicado.")
