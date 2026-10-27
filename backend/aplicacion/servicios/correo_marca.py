"""Presentación mínima para avisos enviados desde la aplicación."""

from html import escape


def aviso_html(titulo: str, contenido: str) -> str:
    return (
        '<!doctype html><html lang="es"><meta charset="utf-8">'
        '<body style="margin:0;padding:24px;background:#f1f8f3;'
        'font-family:Arial,sans-serif;color:#24413b">'
        '<table role="presentation" align="center" width="100%" '
        'style="max-width:560px;background:#fff;border:1px solid #d7e8dd">'
        '<tr><td style="padding:18px;background:#24815c;color:#fff;'
        'font-size:22px;font-weight:700">'
        '<img src="cid:debupa-icono" alt="" width="28" height="28" '
        'style="vertical-align:middle;margin-right:8px;border:0">DEBUPA'
        '</td></tr><tr><td style="padding:24px">'
        f'<h1 style="font-size:21px">{escape(titulo)}</h1>'
        f'<p style="line-height:1.5">{escape(contenido)}</p>'
        "</td></tr></table></body></html>"
    )
