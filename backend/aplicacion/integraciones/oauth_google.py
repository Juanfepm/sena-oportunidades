"""Adaptador HTTP para el intercambio y revocación de Google OAuth."""

from dataclasses import dataclass

import httpx

from ..configuracion import Configuracion

PERMISO_ENVIO_GMAIL = "https://www.googleapis.com/auth/gmail.send"


class GoogleNoDisponible(RuntimeError):
    """Google no entregó una respuesta utilizable para iniciar sesión."""


@dataclass(frozen=True)
class CredencialesGoogle:
    token: dict
    identidad: dict


async def intercambiar_codigo(configuracion: Configuracion, codigo: str) -> CredencialesGoogle:
    try:
        async with httpx.AsyncClient(timeout=10) as cliente:
            respuesta_token = await cliente.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": codigo,
                    "client_id": configuracion.google_cliente_id,
                    "client_secret": configuracion.google_cliente_secreto,
                    "redirect_uri": configuracion.google_uri_redireccion,
                    "grant_type": "authorization_code",
                },
            )
            respuesta_token.raise_for_status()
            token = respuesta_token.json()
            if not isinstance(token, dict) or not token.get("access_token"):
                raise ValueError("Google no devolvió un token de acceso.")
            respuesta_identidad = await cliente.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {token['access_token']}"},
            )
            respuesta_identidad.raise_for_status()
            identidad = respuesta_identidad.json()
            if not isinstance(identidad, dict):
                raise ValueError("Google no devolvió una identidad válida.")
            return CredencialesGoogle(token, identidad)
    except (httpx.HTTPError, ValueError) as error:
        raise GoogleNoDisponible("Google no completó el inicio de sesión.") from error


async def revocar_token(token: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as cliente:
            respuesta = await cliente.post(
                "https://oauth2.googleapis.com/revoke", data={"token": token}
            )
            respuesta.raise_for_status()
    except httpx.HTTPError as error:
        raise GoogleNoDisponible("Google no confirmó la revocación del permiso.") from error
