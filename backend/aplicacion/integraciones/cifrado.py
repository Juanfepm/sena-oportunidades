"""Protección local del permiso de Gmail antes de persistirlo."""

from cryptography.fernet import Fernet, InvalidToken


class ClaveCifradoInvalida(ValueError):
    """La clave del entorno falta o no permite proteger secretos."""


def obtener_cifrador(clave: str | None) -> Fernet:
    if not clave:
        raise ClaveCifradoInvalida("Gmail requiere DEBUPA_CLAVE_CIFRADO.")
    try:
        return Fernet(clave.encode("utf-8"))
    except (ValueError, TypeError) as error:
        raise ClaveCifradoInvalida("DEBUPA_CLAVE_CIFRADO no tiene un formato válido.") from error


def cifrar_token(token: str, clave: str | None) -> str:
    return obtener_cifrador(clave).encrypt(token.encode("utf-8")).decode("utf-8")


def descifrar_token(token_cifrado: str, clave: str | None) -> str:
    try:
        return obtener_cifrador(clave).decrypt(token_cifrado.encode("utf-8")).decode("utf-8")
    except InvalidToken as error:
        raise ClaveCifradoInvalida("No fue posible abrir el permiso cifrado de Gmail.") from error
