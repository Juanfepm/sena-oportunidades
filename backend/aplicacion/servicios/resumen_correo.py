"""Resumen accesible de contactos, con el estilo visual de DEBUPA."""

from html import escape

CORREO_DEBUPA = "debupawebapp@gmail.com"


def crear_resumen(contactos: list[tuple[str, str]]) -> tuple[str, str]:
    """Devuelve texto y HTML; los datos publicados por terceros se escapan."""
    encabezado = "Estos son los contactos publicados por las empresas a las que escribiste:"
    lineas = [f"{nombre}: {telefono}" for nombre, telefono in contactos]
    texto = "\n\n".join(
        (
            encabezado,
            "\n".join(lineas) if lineas else "No se encontraron números con un formato válido.",
            "Gracias por usar DEBUPA. Verifica cada dato directamente con la empresa.",
        )
    )

    tarjetas = (
        "".join(
            '<tr><td style="padding:0 24px 12px">'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            'style="border:1px solid #d7e8dd;border-radius:14px;background:#ffffff">'
            '<tr><td style="padding:15px 18px">'
            f'<div style="color:#24413b;font-size:16px;font-weight:700">{escape(nombre)}</div>'
            '<div style="color:#24815c;font-size:18px;font-weight:700;'
            f'margin-top:5px">{escape(telefono)}</div>'
            "</td></tr></table></td></tr>"
            for nombre, telefono in contactos
        )
        if contactos
        else (
            '<tr><td style="padding:0 24px 16px;color:#5b706a">'
            "No se encontraron números con un formato válido."
            "</td></tr>"
        )
    )

    html = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
        '<body style="margin:0;padding:28px 12px;background:#f1f8f3;'
        'font-family:Arial,Helvetica,sans-serif;color:#24413b">'
        '<table role="presentation" align="center" width="100%" cellspacing="0" cellpadding="0" '
        'style="max-width:600px;background:#ffffff;border:1px solid #d7e8dd;border-radius:20px">'
        '<tr><td style="padding:25px 24px;background:#24815c;border-radius:20px 20px 0 0;'
        'color:#ffffff;font-size:24px;font-weight:800;letter-spacing:.4px">DEBUPA</td></tr>'
        '<tr><td style="padding:26px 24px 12px">'
        '<div style="color:#24815c;font-size:12px;font-weight:700;'
        'text-transform:uppercase;letter-spacing:1px">Tu campaña terminó</div>'
        '<h1 style="margin:9px 0 11px;font-size:26px;line-height:1.2">'
        "Contactos para seguir adelante</h1>"
        '<p style="margin:0;color:#5b706a;font-size:15px;line-height:1.5">'
        "Estos son los teléfonos publicados por las empresas a las que escribiste. "
        "Puedes copiar cada número por separado."
        "</p></td></tr>"
        f"{tarjetas}"
        '<tr><td style="padding:12px 24px 28px;color:#5b706a;font-size:13px;line-height:1.5">'
        "Verifica cada dato directamente con la empresa.<br>Gracias por usar DEBUPA."
        "</td></tr></table></body></html>"
    )
    return texto, html
