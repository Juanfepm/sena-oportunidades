"""Avisos de revisión Premium enviados desde la cuenta de servicio."""

from datetime import datetime
from html import escape

from sqlalchemy.orm import Session

from ..configuracion import Configuracion
from ..dominio.estados import EstadoPago
from ..integraciones.cifrado import ClaveCifradoInvalida
from ..integraciones.gmail import (
    EnvioGmailNoConfirmado,
    GmailNoDisponible,
    PermisoGmailInvalido,
    enviar_gmail,
)
from ..modelos import PagoPremium, Usuario
from .conexiones_gmail import obtener_conexion_resumen
from .resumen_correo import CORREO_DEBUPA


def _tarjeta_decision(aprobado: bool, vence: datetime | None) -> tuple[str, str, str]:
    titulo = "Tu plan Premium está activo" if aprobado else "Revisamos tu solicitud Premium"
    detalle = (
        f"Tu acceso Premium estará disponible hasta el {vence:%d/%m/%Y}."
        if aprobado and vence
        else (
            "No pudimos confirmar el pago con el comprobante recibido. "
            "Si realizaste el pago, puedes solicitar un reembolso a "
            "debupawebapp@gmail.com dentro de los 7 días siguientes a este aviso. "
            "Este plazo adicional no limita tus derechos legales."
        )
    )
    texto = f"{titulo}\n\n{detalle}\n\nGracias por usar DEBUPA."
    html = (
        '<!doctype html><html lang="es"><meta charset="utf-8">'
        '<body style="margin:0;padding:28px 12px;'
        'background:#f1f8f3;font-family:Arial,sans-serif;color:#24413b">'
        '<table role="presentation" align="center" width="100%" '
        'style="max-width:560px;background:#fff;'
        'border:1px solid #d7e8dd;border-radius:18px"><tr><td '
        'style="padding:24px;background:#24815c;'
        'color:#fff;font-size:25px;font-weight:800">'
        '<img src="cid:debupa-icono" alt="" width="30" height="30" '
        'style="vertical-align:middle;margin-right:10px;border:0">DEBUPA'
        '</td></tr><tr><td style="padding:26px">'
        '<p style="color:#24815c;font-size:12px;font-weight:700">ACTIVACIÓN PREMIUM</p>'
        f'<h1 style="font-size:24px">{escape(titulo)}</h1>'
        f'<p style="line-height:1.5">{escape(detalle)}</p>'
        '<p style="color:#5b706a;font-size:13px">Gracias por usar DEBUPA.</p>'
        "</td></tr></table></body></html>"
    )
    return f"DEBUPA · {titulo}", texto, html


async def notificar_decision(
    configuracion: Configuracion, sesion: Session, pago: PagoPremium
) -> None:
    aprendiz = sesion.get(Usuario, pago.usuario_id)
    conexion = obtener_conexion_resumen(sesion)
    if conexion is None or not aprendiz or not aprendiz.correo_google:
        pago.notificacion_estado = "pendiente"
        sesion.commit()
        return
    asunto, texto, html = _tarjeta_decision(
        pago.estado == EstadoPago.APROBADO, aprendiz.premium_hasta
    )
    pago.notificacion_estado = "en_proceso"
    sesion.commit()
    try:
        await enviar_gmail(
            configuracion,
            conexion.token_renovacion_cifrado,
            CORREO_DEBUPA,
            aprendiz.correo_google,
            asunto,
            texto,
            (),
            html,
        )
    except (EnvioGmailNoConfirmado, PermisoGmailInvalido):
        pago.notificacion_estado = "incierto"
    except (GmailNoDisponible, ClaveCifradoInvalida):
        pago.notificacion_estado = "pendiente"
    except Exception:
        pago.notificacion_estado = "incierto"
    else:
        pago.notificacion_estado = "enviado"
    sesion.commit()
