"""API preparada para integraciones futuras, sin simulaciones engañosas."""

from datetime import datetime, timezone
from hmac import compare_digest
from pathlib import Path
from secrets import token_urlsafe
from time import time
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import httpx
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from .base_datos import crear_motor, obtener_sesion
from .configuracion import Configuracion
from .dominio.estados import LIMITES_ARCHIVOS, LIMITES_CONTACTO, TARJETAS_RESUMEN, Plan
from .esquemas import ResumenCampana, ResumenHistorial, SolicitudBorrador
from .modelos import HistorialEnvio, Usuario
from .seguridad import obtener_token_csrf, obtener_usuario_actual, verificar_csrf
from .servicios.campanas import EsperaPlanGratis, consultar_campana, consultar_disponibilidad, crear_borrador, listar_borradores
from .servicios.exclusiones import listar_exclusiones, quitar_exclusion


def crear_aplicacion(configuracion: Configuracion | None = None, motor: Engine | None = None) -> FastAPI:
    configuracion = configuracion or Configuracion.desde_entorno()
    if configuracion.entorno == "produccion" and not configuracion.secreto_sesion:
        raise ValueError("Producción requiere DEBUPA_SECRETO_SESION para firmar las sesiones.")
    if configuracion.google_cliente_id and configuracion.google_cliente_secreto and not configuracion.secreto_sesion:
        raise ValueError("Google OAuth requiere DEBUPA_SECRETO_SESION.")
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

    @api.get("/api/v1/autenticacion/google/iniciar", name="google_iniciar")
    async def google_iniciar(request: Request):
        if not configuracion.google_cliente_id or not configuracion.google_cliente_secreto:
            raise HTTPException(503, "Google OAuth no está configurado.")
        estado = token_urlsafe(32)
        request.session["google_oauth_estado"] = estado
        request.session["google_oauth_iniciado"] = int(time())
        parametros = urlencode({
            "client_id": configuracion.google_cliente_id,
            "redirect_uri": configuracion.google_uri_redireccion,
            "response_type": "code",
            "scope": "openid email profile",
            "state": estado,
        })
        return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{parametros}", status_code=307)

    @api.get("/api/v1/autenticacion/google/callback", name="google_callback")
    async def google_callback(request: Request, sesion: Session = Depends(obtener_sesion)):
        if not configuracion.google_cliente_id or not configuracion.google_cliente_secreto:
            raise HTTPException(503, "Google OAuth no está configurado.")
        estado_guardado = request.session.pop("google_oauth_estado", None)
        estado_recibido = request.query_params.get("state", "")
        iniciado = request.session.pop("google_oauth_iniciado", 0)
        if not estado_guardado or not compare_digest(estado_guardado, estado_recibido) or time() - iniciado > 600:
            raise HTTPException(401, "El estado de autenticación de Google no es válido o expiró.")
        codigo = request.query_params.get("code")
        if not codigo:
            raise HTTPException(401, "Google no devolvió un código de autorización.")
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
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(401, "No fue posible validar la identidad de Google.") from error

        sujeto = str(identidad.get("sub", "")).strip()
        correo = str(identidad.get("email", "")).strip().lower()
        correo_verificado = identidad.get("email_verified") is True
        if not sujeto or not correo or not correo_verificado:
            raise HTTPException(401, "Google no entregó una identidad verificable.")

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
        sesion.commit()
        sesion.refresh(usuario)
        request.session.clear()
        request.session["usuario_id"] = usuario.id
        request.session["token_csrf"] = token_urlsafe(32)
        return RedirectResponse(configuracion.google_url_inicio, status_code=303)

    @api.post("/api/v1/autenticacion/cerrar-sesion", status_code=204)
    async def cerrar_sesion(request: Request, _: None = Depends(verificar_csrf)) -> None:
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

    @api.middleware("http")
    async def proteger_respuestas(peticion: Request, siguiente) -> Response:
        respuesta = await siguiente(peticion)
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
        return {
            "borradores": True,
            "historial_local": True,
            "cola_persistente": True,
            "trabajador_activo": False,
            "google_oauth": bool(configuracion.google_cliente_id and configuracion.google_cliente_secreto),
            "sgva": False,
            "gmail": False,
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
        raise HTTPException(503, "El inicio requiere Google, SGVA, Gmail y almacenamiento temporal cifrado.")

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
