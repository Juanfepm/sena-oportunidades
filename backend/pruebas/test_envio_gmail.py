"""La prueba de Gmail nunca acepta destinatarios externos ni consume campañas."""

import json
from base64 import urlsafe_b64decode
from email.parser import BytesParser
from email.policy import default
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base
from backend.aplicacion.configuracion import Configuracion
from backend.aplicacion.integraciones import gmail
from backend.aplicacion.modelos import HistorialEnvio
from backend.aplicacion.principal import crear_aplicacion


def test_icono_solo_se_incrusta_en_avisos_de_debupa() -> None:
    con_icono = gmail.preparar_mensaje(
        "debupawebapp@gmail.com",
        "aprendiz@ejemplo.com",
        "Resumen",
        "Resumen de contacto",
        cuerpo_html='<img src="cid:debupa-icono" alt="">',
    )
    sin_icono = gmail.preparar_mensaje(
        "aprendiz@ejemplo.com", "empresa@ejemplo.com", "Práctica", "Hola"
    )
    aviso = BytesParser(policy=default).parsebytes(urlsafe_b64decode(con_icono))
    empresa = BytesParser(policy=default).parsebytes(urlsafe_b64decode(sin_icono))
    assert any(parte.get_content_type() == "image/png" for parte in aviso.walk())
    assert not any(parte.get_content_type() == "image/png" for parte in empresa.walk())


@pytest.mark.parametrize("gmail_confirma", [True, False])
def test_prueba_gmail_solo_escribe_al_usuario_y_no_se_repite(
    monkeypatch: pytest.MonkeyPatch,
    gmail_confirma: bool,
) -> None:
    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    configuracion = Configuracion(
        entorno="desarrollo",
        base_datos="sqlite://",
        google_cliente_id="cliente-prueba.apps.googleusercontent.com",
        google_cliente_secreto="secreto-ficticio",
        secreto_sesion="clave-firmada-para-prueba-de-envio-gmail-2026",
        clave_cifrado=Fernet.generate_key().decode(),
    )
    mensajes = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        if peticion.url.path == "/token":
            datos = parse_qs(peticion.content.decode())
            if datos["grant_type"] == ["authorization_code"]:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "acceso-inicial",
                        "refresh_token": "permiso-cifrado-en-base",
                        "scope": "openid email profile https://www.googleapis.com/auth/gmail.send",
                    },
                )
            assert datos["grant_type"] == ["refresh_token"]
            assert datos["refresh_token"] == ["permiso-cifrado-en-base"]
            return httpx.Response(200, json={"access_token": "acceso-para-enviar"})
        if peticion.url.path == "/v1/userinfo":
            return httpx.Response(
                200,
                json={
                    "sub": "identificador-estable",
                    "email": "aprendiz@ejemplo.com",
                    "email_verified": True,
                },
            )
        if peticion.url.path == "/gmail/v1/users/me/messages/send":
            assert peticion.headers["Authorization"] == "Bearer acceso-para-enviar"
            mensaje = BytesParser(policy=default).parsebytes(
                urlsafe_b64decode(json.loads(peticion.content)["raw"])
            )
            mensajes.append(mensaje)
            return (
                httpx.Response(200, json={"id": "mensaje-confirmado"})
                if gmail_confirma
                else httpx.Response(503)
            )
        if peticion.url.path == "/revoke":
            return httpx.Response(200)
        return httpx.Response(404)

    cliente_httpx = httpx.AsyncClient
    monkeypatch.setattr(
        gmail.httpx,
        "AsyncClient",
        lambda **opciones: cliente_httpx(transport=httpx.MockTransport(responder), **opciones),
    )
    try:
        with TestClient(crear_aplicacion(configuracion, motor)) as cliente:
            assert cliente.post("/api/v1/gmail/prueba").status_code == 401
            assert cliente.get("/api/v1/capacidades").json()["gmail_prueba"] is True

            inicio = cliente.get("/api/v1/autenticacion/google/iniciar", follow_redirects=False)
            estado = parse_qs(urlsplit(inicio.headers["location"]).query)["state"][0]
            regreso = cliente.get(
                f"/api/v1/autenticacion/google/callback?code=identidad&state={estado}",
                follow_redirects=False,
            )
            assert regreso.status_code == 303
            assert cliente.post("/api/v1/gmail/prueba").status_code == 403

            csrf = cliente.get("/api/v1/autenticacion/csrf").json()["token"]
            destino_externo = cliente.post(
                "/api/v1/gmail/prueba",
                json={"destinatario": "empresa@ejemplo.com"},
                headers={"X-CSRF-Token": csrf},
            )
            assert destino_externo.status_code == 400
            respuesta = cliente.post("/api/v1/gmail/prueba", headers={"X-CSRF-Token": csrf})
            assert respuesta.status_code == (200 if gmail_confirma else 503)
            if gmail_confirma:
                assert respuesta.json() == {
                    "correo": "aprendiz@ejemplo.com",
                    "mensaje_id": "mensaje-confirmado",
                }
            else:
                assert "Revisa Enviados" in respuesta.json()["detail"]
            assert cliente.get("/api/v1/gmail/estado").json()["prueba_solicitada"] is True
            assert (
                cliente.post("/api/v1/gmail/prueba", headers={"X-CSRF-Token": csrf}).status_code
                == 429
            )
            assert len(mensajes) == 1
            assert mensajes[0]["From"] == "aprendiz@ejemplo.com"
            assert mensajes[0]["To"] == "aprendiz@ejemplo.com"
            adjunto = next(mensajes[0].iter_attachments())
            assert adjunto.get_filename() == "prueba-debupa.txt"
            assert adjunto.get_payload(decode=True) == b"Prueba de adjunto de DEBUPA.\n"
            with cliente.app.state.fabrica_sesiones() as sesion:
                assert sesion.scalar(select(HistorialEnvio)) is None
    finally:
        motor.dispose()
