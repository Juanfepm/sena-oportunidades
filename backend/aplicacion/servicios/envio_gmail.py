"""Envía mensajes mediante el permiso mínimo de Gmail."""

from base64 import urlsafe_b64encode
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP

import httpx

from ..configuracion import Configuracion
from .gmail import descifrar_token


class PermisoGmailInvalido(RuntimeError):
    """Google ya no acepta el permiso guardado."""


class EnvioGmailNoConfirmado(RuntimeError):
    """La solicitud pudo llegar a Gmail, pero no recibimos confirmación."""


class GmailNoDisponible(RuntimeError):
    """No fue posible completar una operación previa al envío."""


@dataclass(frozen=True)
class AdjuntoGmail:
    nombre: str
    contenido: bytes
    tipo: str
    subtipo: str


def preparar_mensaje(
    remitente: str,
    destinatario: str,
    asunto: str,
    cuerpo: str,
    adjuntos: tuple[AdjuntoGmail, ...] = (),
) -> str:
    """Construye el MIME que Gmail espera en el campo `raw`."""
    mensaje = EmailMessage(policy=SMTP)
    mensaje["From"] = remitente
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)
    for adjunto in adjuntos:
        mensaje.add_attachment(
            adjunto.contenido,
            maintype=adjunto.tipo,
            subtype=adjunto.subtipo,
            filename=adjunto.nombre,
        )
    return urlsafe_b64encode(mensaje.as_bytes()).decode("ascii")


async def enviar_gmail(
    configuracion: Configuracion,
    token_cifrado: str,
    remitente: str,
    destinatario: str,
    asunto: str,
    cuerpo: str,
    adjuntos: tuple[AdjuntoGmail, ...] = (),
) -> str:
    """Renueva el acceso y devuelve el ID confirmado por Gmail."""
    token_renovacion = descifrar_token(token_cifrado, configuracion.clave_cifrado)
    if not configuracion.google_cliente_id or not configuracion.google_cliente_secreto:
        raise GmailNoDisponible("Google OAuth no está configurado.")
    async with httpx.AsyncClient(timeout=15) as cliente:
        try:
            respuesta_token = await cliente.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": configuracion.google_cliente_id,
                    "client_secret": configuracion.google_cliente_secreto,
                    "refresh_token": token_renovacion,
                    "grant_type": "refresh_token",
                },
            )
            if respuesta_token.status_code in {400, 401}:
                raise PermisoGmailInvalido("Vuelve a iniciar sesión con Google.")
            respuesta_token.raise_for_status()
            datos_token = respuesta_token.json()
            token_acceso = datos_token.get("access_token") if isinstance(datos_token, dict) else None
            if not isinstance(token_acceso, str) or not token_acceso:
                raise GmailNoDisponible("Google no entregó un token de acceso.")
        except (httpx.HTTPError, ValueError) as error:
            raise GmailNoDisponible("Google no respondió antes de enviar.") from error

        try:
            respuesta_envio = await cliente.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {token_acceso}"},
                json={"raw": preparar_mensaje(remitente, destinatario, asunto, cuerpo, adjuntos)},
            )
            if respuesta_envio.status_code == 401:
                raise PermisoGmailInvalido("Vuelve a iniciar sesión con Google.")
            if not respuesta_envio.is_success:
                raise EnvioGmailNoConfirmado("Gmail no confirmó el envío.")
            datos_envio = respuesta_envio.json()
            mensaje_id = datos_envio.get("id") if isinstance(datos_envio, dict) else None
            if not isinstance(mensaje_id, str) or not mensaje_id:
                raise EnvioGmailNoConfirmado("Gmail no entregó el ID del mensaje.")
            return mensaje_id
        except (httpx.TransportError, ValueError) as error:
            raise EnvioGmailNoConfirmado("Gmail no confirmó el envío.") from error
