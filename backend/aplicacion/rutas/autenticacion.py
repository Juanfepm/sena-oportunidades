"""Autenticación de Google y consentimiento de Gmail."""

from hmac import compare_digest
from secrets import token_urlsafe
from time import time
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..base_datos import obtener_sesion
from ..configuracion import Configuracion
from ..integraciones.cifrado import ClaveCifradoInvalida, descifrar_token
from ..integraciones.gmail import (
    AdjuntoGmail,
    EnvioGmailNoConfirmado,
    GmailNoDisponible,
    PermisoGmailInvalido,
    enviar_gmail,
)
from ..integraciones.oauth_google import (
    PERMISO_ENVIO_GMAIL,
    GoogleNoDisponible,
    intercambiar_codigo,
    revocar_token,
)
from ..modelos import ConexionGmail, Usuario
from ..seguridad import obtener_token_csrf, obtener_usuario_actual, verificar_csrf
from ..servicios.identidad_google import (
    IdentidadGoogleInvalida,
    PermisoGmailAusente,
    registrar_cuenta,
)


def pagina_error(tipo: str) -> RedirectResponse:
    """Muestra un problema conocido sin trasladar secretos a la URL."""
    return RedirectResponse(f"/error.html?tipo={tipo}", status_code=303)


def crear_router(configuracion: Configuracion, cifrado_disponible: bool) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/autenticacion/google/iniciar", name="google_iniciar")
    async def google_iniciar(request: Request):
        if (
            not configuracion.google_cliente_id
            or not configuracion.google_cliente_secreto
            or not cifrado_disponible
        ):
            return pagina_error("servicio")
        estado = token_urlsafe(32)
        request.session.clear()
        request.session["google_oauth_estado"] = estado
        request.session["google_oauth_iniciado"] = int(time())
        parametros = urlencode(
            {
                "client_id": configuracion.google_cliente_id,
                "redirect_uri": configuracion.google_uri_redireccion,
                "response_type": "code",
                "scope": f"openid email profile {PERMISO_ENVIO_GMAIL}",
                "state": estado,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
            }
        )
        return RedirectResponse(
            f"https://accounts.google.com/o/oauth2/v2/auth?{parametros}",
            status_code=307,
        )

    @router.get("/api/v1/autenticacion/google/callback", name="google_callback")
    async def google_callback(request: Request, sesion: Session = Depends(obtener_sesion)):
        if not configuracion.google_cliente_id or not configuracion.google_cliente_secreto:
            raise HTTPException(503, "Google OAuth no está configurado.")
        estado_guardado = request.session.pop("google_oauth_estado", None)
        estado_recibido = request.query_params.get("state", "")
        iniciado = request.session.pop("google_oauth_iniciado", 0)
        if (
            not isinstance(estado_guardado, str)
            or not compare_digest(estado_guardado, estado_recibido)
            or time() - iniciado > 600
        ):
            return pagina_error("google")
        codigo = request.query_params.get("code")
        if not codigo:
            return pagina_error("google")
        try:
            credenciales = await intercambiar_codigo(configuracion, codigo)
        except GoogleNoDisponible:
            return pagina_error("google")
        try:
            usuario = registrar_cuenta(sesion, configuracion, credenciales)
        except IdentidadGoogleInvalida:
            return pagina_error("google")
        except (PermisoGmailAusente, ClaveCifradoInvalida):
            return pagina_error("gmail")

        request.session.clear()
        request.session["usuario_id"] = usuario.id
        request.session["token_csrf"] = token_urlsafe(32)
        return RedirectResponse(configuracion.google_url_inicio, status_code=303)

    @router.post("/api/v1/autenticacion/cerrar-sesion", status_code=204)
    async def cerrar_sesion(
        request: Request,
        _: None = Depends(verificar_csrf),
        sesion: Session = Depends(obtener_sesion),
    ) -> None:
        usuario_id = request.session.get("usuario_id")
        if usuario_id is not None:
            conexion = sesion.scalar(
                select(ConexionGmail).where(ConexionGmail.usuario_id == usuario_id)
            )
            cuenta = sesion.get(Usuario, usuario_id)
            correo_servicio = (
                cuenta is not None and cuenta.correo_google == "debupawebapp@gmail.com"
            )
            administrador = (
                correo_servicio
                and cuenta.es_administrador
                and (
                    cuenta.correo_google
                    == (configuracion.correo_administrador or "").strip().lower()
                )
            )
            if conexion is not None and not administrador:
                try:
                    token = descifrar_token(
                        conexion.token_renovacion_cifrado, configuracion.clave_cifrado
                    )
                    await revocar_token(token)
                except (ClaveCifradoInvalida, GoogleNoDisponible):
                    pass  # El permiso local se elimina aunque Google no responda.
                sesion.delete(conexion)
                sesion.commit()
        request.session.clear()

    @router.get("/api/v1/autenticacion/yo")
    def cuenta_actual(
        usuario: Usuario = Depends(obtener_usuario_actual),
    ) -> dict[str, str | bool]:
        return {
            "correo": usuario.correo_google or "",
            "nombre": usuario.nombre_google or "",
            "plan": usuario.plan,
            "premium_hasta": usuario.premium_hasta.isoformat() if usuario.premium_hasta else "",
            "es_administrador": bool(
                usuario.es_administrador
                and usuario.correo_google
                == (configuracion.correo_administrador or "").strip().lower()
            ),
        }

    @router.get("/api/v1/autenticacion/csrf")
    def token_csrf(
        request: Request,
        _: Usuario = Depends(obtener_usuario_actual),
    ) -> dict[str, str]:
        return {"token": obtener_token_csrf(request)}

    @router.get("/api/v1/gmail/estado")
    def estado_gmail(
        request: Request,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, bool | str | None]:
        conexion = sesion.scalar(
            select(ConexionGmail).where(ConexionGmail.usuario_id == usuario.id)
        )
        return {
            "conectado": conexion is not None,
            "correo": conexion.correo_google if conexion else None,
            "prueba_solicitada": bool(request.session.get("gmail_prueba_solicitada")),
        }

    @router.post("/api/v1/gmail/prueba")
    async def prueba_gmail(
        request: Request,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, str]:
        """Prueba local de un solo intento por sesión, dirigida a la propia cuenta."""
        if (
            configuracion.entorno != "desarrollo"
            or request.client is None
            or request.client.host not in {"127.0.0.1", "::1", "testclient"}
        ):
            raise HTTPException(404, "La prueba solo está disponible en desarrollo.")
        if request.session.get("usuario_id") != usuario.id or not usuario.correo_google:
            raise HTTPException(401, "Inicia sesión con Google para hacer la prueba.")
        if await request.body():
            raise HTTPException(
                400, "La prueba no acepta destinatarios ni contenido del navegador."
            )
        if request.session.get("gmail_prueba_solicitada"):
            raise HTTPException(429, "Ya solicitaste una prueba en esta sesión.")
        conexion = sesion.scalar(
            select(ConexionGmail).where(ConexionGmail.usuario_id == usuario.id)
        )
        if (
            conexion is None
            or conexion.correo_google != usuario.correo_google
            or conexion.permisos != PERMISO_ENVIO_GMAIL
        ):
            raise HTTPException(409, "Vuelve a entrar con Google para vincular Gmail.")

        request.session["gmail_prueba_solicitada"] = True
        try:
            mensaje_id = await enviar_gmail(
                configuracion,
                conexion.token_renovacion_cifrado,
                usuario.correo_google,
                usuario.correo_google,
                "Prueba de conexión de DEBUPA",
                "Este mensaje confirma que DEBUPA puede enviar desde tu cuenta de Gmail. "
                "No se contactó a ninguna empresa.\n",
                (
                    AdjuntoGmail(
                        "prueba-debupa.txt",
                        b"Prueba de adjunto de DEBUPA.\n",
                        "text",
                        "plain",
                    ),
                ),
            )
        except (PermisoGmailInvalido, ClaveCifradoInvalida) as error:
            raise HTTPException(
                409,
                "El permiso de Gmail expiró. Cierra sesión y vuelve a entrar con Google.",
            ) from error
        except EnvioGmailNoConfirmado as error:
            raise HTTPException(
                503,
                "Gmail no confirmó el resultado. Revisa Enviados antes de repetir la prueba.",
            ) from error
        except GmailNoDisponible as error:
            raise HTTPException(
                503, "Google no respondió. Inténtalo en una nueva sesión más tarde."
            ) from error
        return {"correo": usuario.correo_google, "mensaje_id": mensaje_id}

    @router.get("/api/v1/gmail/conectar")
    def conectar_gmail_anterior() -> RedirectResponse:
        """Los enlaces previos inician ahora el flujo único de Google."""
        return RedirectResponse("/api/v1/autenticacion/google/iniciar", status_code=303)

    return router
