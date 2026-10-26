"""El resumen de DEBUPA muestra datos de terceros sin interpretarlos como HTML."""

from base64 import urlsafe_b64decode
from email.parser import BytesParser
from email.policy import default

from backend.aplicacion.servicios.envio_gmail import preparar_mensaje
from backend.aplicacion.servicios.resumen_correo import CORREO_DEBUPA, crear_resumen


def test_resumen_html_y_texto_seguro():
    texto, html = crear_resumen([("Empresa <script>alert(1)</script>", "+57 300 123 4567")])
    assert "Empresa <script>alert(1)</script>" in texto
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "DEBUPA" in html

    correo = BytesParser(policy=default).parsebytes(urlsafe_b64decode(preparar_mensaje(
        CORREO_DEBUPA, "aprendiz@ejemplo.com", "Contactos", texto, cuerpo_html=html,
    )))
    assert correo["From"] == CORREO_DEBUPA
    assert correo["To"] == "aprendiz@ejemplo.com"
    assert correo.get_body(preferencelist=("plain",)).get_content().replace("\r\n", "\n").strip() == texto
    assert "&lt;script&gt;" in correo.get_body(preferencelist=("html",)).get_content()
