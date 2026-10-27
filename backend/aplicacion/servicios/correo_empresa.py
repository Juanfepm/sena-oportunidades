"""Firma discreta para los correos autorizados por el aprendiz."""

from html import escape

FIRMA = "Correo enviado con apoyo de DEBUPA"


def preparar_correo_empresa(cuerpo: str) -> tuple[str, str]:
    """Conserva el mensaje original y separa visualmente la firma del servicio."""
    texto = f"{cuerpo}\n\n{FIRMA}"
    html = (
        '<!doctype html><html lang="es"><meta charset="utf-8">'
        '<body style="margin:0;color:#24413b;font-family:Arial,sans-serif">'
        '<div style="white-space:pre-wrap;line-height:1.5">'
        f"{escape(cuerpo)}"
        "</div>"
        '<p style="border-top:1px solid #e7eeea;color:#8a9e96;'
        'font-size:11px;margin:28px 0 0;padding-top:10px">'
        f"{FIRMA}</p></body></html>"
    )
    return texto, html
