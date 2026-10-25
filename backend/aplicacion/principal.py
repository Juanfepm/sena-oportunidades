"""API preparada para integraciones futuras, sin simulaciones engañosas."""

from datetime import datetime, timezone
from hmac import compare_digest
from pathlib import Path
from secrets import token_urlsafe
from time import time
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import httpx
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .base_datos import crear_motor, obtener_sesion
from .configuracion import Configuracion
from .dominio.estados import LIMITES_ARCHIVOS, LIMITES_CONTACTO, TARJETAS_RESUMEN, Plan
from .esquemas import ResumenCampana, ResumenHistorial, SolicitudBorrador
from .integraciones.contratos import AccesoSGVARestringido, IntegracionNoDisponible, SGVANoDisponible
from .modelos import ConexionGmail, HistorialEnvio, Usuario
from .seguridad import obtener_token_csrf, obtener_usuario_actual, verificar_csrf
from .servicios.campanas import EsperaPlanGratis, consultar_campana, consultar_disponibilidad, crear_borrador, listar_borradores
from .servicios.exclusiones import listar_exclusiones, quitar_exclusion
from .servicios.envio_gmail import (
    AdjuntoGmail,
    EnvioGmailNoConfirmado,
    GmailNoDisponible,
    PermisoGmailInvalido,
    enviar_gmail,
)
from .servicios.gmail import ClaveCifradoInvalida, cifrar_token, descifrar_token, obtener_cifrador


PERMISO_ENVIO_GMAIL = "https://www.googleapis.com/auth/gmail.send"


def pagina_error(tipo: str) -> RedirectResponse:
    """Muestra un problema conocido sin trasladar secretos a la URL."""
    return RedirectResponse(f"/error.html?tipo={tipo}", status_code=303)


def crear_aplicacion(configuracion: Configuracion | None = None, motor: Engine | None = None) -> FastAPI:
    configuracion = configuracion or Configuracion.desde_entorno()
    if configuracion.entorno == "produccion" and not configuracion.secreto_sesion:
        raise ValueError("Producción requiere DEBUPA_SECRETO_SESION para firmar las sesiones.")
    if configuracion.google_cliente_id and configuracion.google_cliente_secreto and not configuracion.secreto_sesion:
        raise ValueError("Google OAuth requiere DEBUPA_SECRETO_SESION.")
    try:
        obtener_cifrador(configuracion.clave_cifrado)
        cifrado_disponible = True
    except ClaveCifradoInvalida:
        cifrado_disponible = False
    motor = motor or crear_motor(configuracion)
    api = FastAPI(title="API de DEBUPA", version="0.1.0")
    api.state.configuracion = configuracion
    api.state.fabrica_sesiones = sessionmaker(motor, expire_on_commit=False)
    api.add_middleware(
        SessionMiddleware,
        secret_key=configuracion.secreto_sesion or configuracion.clave_pruebas or "clave-sesion-pruebas-locales",
        https_only=configuracion.entorno == "produccion",
        same_site="lax",
        max_age=7 * 24 * 60 * 60,
    )

    @api.exception_handler(AccesoSGVARestringido)
    async def acceso_sgva_restringido(_: Request, __: AccesoSGVARestringido) -> JSONResponse:
        return JSONResponse(
            {"codigo": "sgva_restringido", "detail": "SGVA no permitió consultar empresas para esta cuenta."},
            status_code=409,
        )

    @api.exception_handler(SGVANoDisponible)
    async def sgva_no_disponible(_: Request, __: SGVANoDisponible) -> JSONResponse:
        return JSONResponse(
            {"codigo": "sgva_no_disponible", "detail": "El servicio SGVA no respondió. Inténtalo más tarde."},
            status_code=503,
        )

    @api.exception_handler(IntegracionNoDisponible)
    async def integracion_no_disponible(_: Request, __: IntegracionNoDisponible) -> JSONResponse:
        return JSONResponse(
            {"codigo": "servicio_no_disponible", "detail": "Un servicio necesario no respondió. Inténtalo más tarde."},
            status_code=503,
        )

    @api.get("/api/v1/autenticacion/google/iniciar", name="google_iniciar")
    async def google_iniciar(request: Request):
        if not configuracion.google_cliente_id or not configuracion.google_cliente_secreto or not cifrado_disponible:
            return pagina_error("servicio")
        estado = token_urlsafe(32)
        request.session.clear()
        request.session["google_oauth_estado"] = estado
        request.session["google_oauth_iniciado"] = int(time())
        parametros = urlencode({
            "client_id": configuracion.google_cliente_id,
            "redirect_uri": configuracion.google_uri_redireccion,
            "response_type": "code",
            "scope": f"openid email profile {PERMISO_ENVIO_GMAIL}",
            "state": estado,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        })
        return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{parametros}", status_code=307)

    @api.get("/api/v1/autenticacion/google/callback", name="google_callback")
    async def google_callback(request: Request, sesion: Session = Depends(obtener_sesion)):
        if not configuracion.google_cliente_id or not configuracion.google_cliente_secreto:
            raise HTTPException(503, "Google OAuth no está configurado.")
        estado_guardado = request.session.pop("google_oauth_estado", None)
        estado_recibido = request.query_params.get("state", "")
        iniciado = request.session.pop("google_oauth_iniciado", 0)
        if not isinstance(estado_guardado, str) or not compare_digest(estado_guardado, estado_recibido) or time() - iniciado > 600:
            return pagina_error("google")
        codigo = request.query_params.get("code")
        if not codigo:
            return pagina_error("google")
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
                access_token = token.get("access_token")
                if not access_token:
                    raise ValueError("Google no devolvió un token de acceso.")
                respuesta_identidad = await cliente.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                respuesta_identidad.raise_for_status()
                identidad = respuesta_identidad.json()
        except (httpx.HTTPError, ValueError):
            return pagina_error("google")

        sujeto = str(identidad.get("sub", "")).strip()
        correo = str(identidad.get("email", "")).strip().lower()
        correo_verificado = identidad.get("email_verified") is True
        if not sujeto or not correo or not correo_verificado:
            return pagina_error("google")

        permisos_recibidos = token.get("scope")
        if not isinstance(permisos_recibidos, str) or PERMISO_ENVIO_GMAIL not in permisos_recibidos.split():
            return pagina_error("gmail")

        usuario = sesion.scalar(select(Usuario).where(Usuario.identificador_externo == f"google:{sujeto}"))
        if usuario is None:
            usuario = Usuario(
                identificador_externo=f"google:{sujeto}",
                correo_google=correo,
                nombre_google=str(identidad.get("name", "")).strip() or None,
            )
            sesion.add(usuario)
        else:
            usuario.correo_google = correo
            usuario.nombre_google = str(identidad.get("name", "")).strip() or usuario.nombre_google
            usuario.ultimo_acceso_en = datetime.now(timezone.utc)
        sesion.flush()
        conexion = sesion.scalar(select(ConexionGmail).where(ConexionGmail.usuario_id == usuario.id))
        token_renovacion = token.get("refresh_token")
        if token_renovacion:
            try:
                token_cifrado = cifrar_token(str(token_renovacion), configuracion.clave_cifrado)
            except ClaveCifradoInvalida:
                sesion.rollback()
                return pagina_error("gmail")
            if conexion is None:
                conexion = ConexionGmail(
                    usuario_id=usuario.id,
                    correo_google=correo,
                    token_renovacion_cifrado=token_cifrado,
                    permisos=PERMISO_ENVIO_GMAIL,
                )
                sesion.add(conexion)
            else:
                conexion.correo_google = correo
                conexion.token_renovacion_cifrado = token_cifrado
                conexion.permisos = PERMISO_ENVIO_GMAIL
        elif conexion is None or conexion.correo_google != correo or conexion.permisos != PERMISO_ENVIO_GMAIL:
            sesion.rollback()
            return pagina_error("gmail")
        else:
            try:
                descifrar_token(conexion.token_renovacion_cifrado, configuracion.clave_cifrado)
            except ClaveCifradoInvalida:
                sesion.rollback()
                return pagina_error("gmail")
        sesion.commit()
        request.session.clear()
        request.session["usuario_id"] = usuario.id
        request.session["token_csrf"] = token_urlsafe(32)
        return RedirectResponse(configuracion.google_url_inicio, status_code=303)

    @api.post("/api/v1/autenticacion/cerrar-sesion", status_code=204)
    async def cerrar_sesion(
        request: Request,
        _: None = Depends(verificar_csrf),
        sesion: Session = Depends(obtener_sesion),
    ) -> None:
        usuario_id = request.session.get("usuario_id")
        if usuario_id is not None:
            conexion = sesion.scalar(select(ConexionGmail).where(ConexionGmail.usuario_id == usuario_id))
            if conexion is not None:
                try:
                    token = descifrar_token(conexion.token_renovacion_cifrado, configuracion.clave_cifrado)
                    async with httpx.AsyncClient(timeout=5) as cliente:
                        respuesta = await cliente.post("https://oauth2.googleapis.com/revoke", data={"token": token})
                        respuesta.raise_for_status()
                except (ClaveCifradoInvalida, httpx.HTTPError):
                    pass  # El permiso local se elimina aunque Google no responda.
                sesion.delete(conexion)
                sesion.commit()
        request.session.clear()

    @api.get("/api/v1/autenticacion/yo")
    def cuenta_actual(usuario: Usuario = Depends(obtener_usuario_actual)) -> dict[str, str | bool]:
        return {
            "correo": usuario.correo_google or "",
            "nombre": usuario.nombre_google or "",
            "plan": usuario.plan,
            "es_administrador": usuario.es_administrador,
        }

    @api.get("/api/v1/autenticacion/csrf")
    def token_csrf(
        request: Request,
        _: Usuario = Depends(obtener_usuario_actual),
    ) -> dict[str, str]:
        return {"token": obtener_token_csrf(request)}

    @api.get("/api/v1/gmail/estado")
    def estado_gmail(
        request: Request,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, bool | str | None]:
        conexion = sesion.scalar(select(ConexionGmail).where(ConexionGmail.usuario_id == usuario.id))
        return {
            "conectado": conexion is not None,
            "correo": conexion.correo_google if conexion else None,
            "prueba_solicitada": bool(request.session.get("gmail_prueba_solicitada")),
        }

    @api.post("/api/v1/gmail/prueba")
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
            raise HTTPException(400, "La prueba no acepta destinatarios ni contenido del navegador.")
        if request.session.get("gmail_prueba_solicitada"):
            raise HTTPException(429, "Ya solicitaste una prueba en esta sesión.")
        conexion = sesion.scalar(select(ConexionGmail).where(ConexionGmail.usuario_id == usuario.id))
        if conexion is None or conexion.correo_google != usuario.correo_google or conexion.permisos != PERMISO_ENVIO_GMAIL:
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
                (AdjuntoGmail("prueba-debupa.txt", b"Prueba de adjunto de DEBUPA.\n", "text", "plain"),),
            )
        except (PermisoGmailInvalido, ClaveCifradoInvalida) as error:
            raise HTTPException(409, "El permiso de Gmail expiró. Cierra sesión y vuelve a entrar con Google.") from error
        except EnvioGmailNoConfirmado as error:
            raise HTTPException(503, "Gmail no confirmó el resultado. Revisa Enviados antes de repetir la prueba.") from error
        except GmailNoDisponible as error:
            raise HTTPException(503, "Google no respondió. Inténtalo en una nueva sesión más tarde.") from error
        return {"correo": usuario.correo_google, "mensaje_id": mensaje_id}

    @api.get("/api/v1/gmail/conectar")
    def conectar_gmail_anterior() -> RedirectResponse:
        """Los enlaces previos inician ahora el flujo único de Google."""
        return RedirectResponse("/api/v1/autenticacion/google/iniciar", status_code=303)

    @api.middleware("http")
    async def proteger_respuestas(peticion: Request, siguiente) -> Response:
        try:
            respuesta = await siguiente(peticion)
        except SQLAlchemyError:
            if peticion.method == "GET" and peticion.url.path == "/api/v1/autenticacion/google/callback":
                respuesta = pagina_error("base-datos")
            else:
                respuesta = JSONResponse({"detail": "La base de datos no está disponible.", "codigo": "base_datos"}, status_code=503)
        respuesta.headers["Cache-Control"] = "no-store"
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        return respuesta

    @api.get("/api/v1/salud")
    def salud(sesion: Session = Depends(obtener_sesion)) -> dict[str, str]:
        sesion.execute(select(1))
        return {"estado": "activo"}

    @api.get("/api/v1/capacidades")
    def capacidades() -> dict[str, bool]:
        gmail_configurado = bool(
            configuracion.google_cliente_id and configuracion.google_cliente_secreto and cifrado_disponible
        )
        return {
            "borradores": True,
            "historial_local": True,
            "cola_persistente": True,
            "trabajador_activo": False,
            "google_oauth": bool(configuracion.google_cliente_id and configuracion.google_cliente_secreto and cifrado_disponible),
            "sgva": False,
            "gmail": gmail_configurado,
            "gmail_prueba": configuracion.entorno == "desarrollo" and gmail_configurado,
            "clasificacion_ia": False,
            "comprobantes_nequi": False,
        }

    @api.get("/api/v1/planes")
    def planes() -> dict[str, dict[str, int]]:
        return {
            plan: {"maximo_contactos": LIMITES_CONTACTO[plan], "maximo_archivos": LIMITES_ARCHIVOS[plan],
                   "tarjetas_detalladas": TARJETAS_RESUMEN[plan]}
            for plan in Plan
        }

    @api.get("/api/v1/disponibilidad")
    def disponibilidad(
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, bool | str | None]:
        proxima_fecha = consultar_disponibilidad(sesion, usuario)
        return {"puede_buscar": proxima_fecha is None, "proxima_fecha": proxima_fecha.isoformat() if proxima_fecha else None}

    @api.post("/api/v1/campanas", response_model=ResumenCampana, status_code=201)
    def nueva_campana(
        solicitud: SolicitudBorrador,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> ResumenCampana:
        try:
            return ResumenCampana.model_validate(crear_borrador(sesion, usuario, solicitud))
        except EsperaPlanGratis as espera:
            raise HTTPException(429, {"mensaje": "El plan gratis debe esperar un mes después del último envío.",
                                      "proxima_fecha": espera.fecha.isoformat()}) from espera

    @api.get("/api/v1/campanas", response_model=list[ResumenCampana])
    def campanas(
        limite: int = Query(default=50, ge=1, le=100),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[ResumenCampana]:
        return [ResumenCampana.model_validate(campana) for campana in listar_borradores(sesion, usuario, limite)]

    @api.get("/api/v1/campanas/{campana_id}", response_model=ResumenCampana)
    def campana(
        campana_id: str,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> ResumenCampana:
        encontrada = consultar_campana(sesion, usuario, campana_id)
        if encontrada is None:
            raise HTTPException(404, "Campaña no encontrada.")
        return ResumenCampana.model_validate(encontrada)

    @api.post("/api/v1/campanas/{campana_id}/iniciar")
    def iniciar_campana(
        campana_id: str,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> None:
        if consultar_campana(sesion, usuario, campana_id) is None:
            raise HTTPException(404, "Campaña no encontrada.")
        raise HTTPException(503, {"codigo": "integracion_pendiente", "mensaje": "La búsqueda SGVA aún no está habilitada."})

    @api.get("/api/v1/correos-excluidos", response_model=list[str])
    def correos_excluidos(
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[str]:
        return listar_exclusiones(sesion, usuario)

    @api.delete("/api/v1/correos-excluidos/{correo}", status_code=204)
    def retirar_exclusion(
        correo: str,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> None:
        if not quitar_exclusion(sesion, usuario, correo):
            raise HTTPException(404, "Correo excluido no encontrado.")

    @api.get("/api/v1/historial", response_model=list[ResumenHistorial])
    def historial(
        limite: int = Query(default=100, ge=1, le=100),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[ResumenHistorial]:
        consulta = (
            select(HistorialEnvio)
            .where(HistorialEnvio.usuario_id == usuario.id)
            .order_by(HistorialEnvio.enviado_en.desc())
            .limit(limite)
        )
        return [ResumenHistorial.model_validate(envio) for envio in sesion.scalars(consulta)]

    ruta_frontend = Path(__file__).resolve().parents[2] / "frontend"
    api.mount("/", StaticFiles(directory=ruta_frontend, html=True), name="frontend")
    return api


aplicacion = crear_aplicacion()
