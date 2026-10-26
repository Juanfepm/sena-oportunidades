"""Identidad de sesión y protección CSRF para rutas que cambian datos."""

from datetime import datetime, timezone
from hmac import compare_digest
from secrets import token_urlsafe

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .base_datos import obtener_sesion
from .dominio.estados import Plan
from .modelos import Usuario


def actualizar_plan_vencido(sesion: Session, usuario: Usuario) -> Usuario:
    hasta = usuario.premium_hasta
    if hasta is not None and hasta.tzinfo is None:
        hasta = hasta.replace(tzinfo=timezone.utc)
    if usuario.plan == Plan.PREMIUM and (hasta is None or hasta <= datetime.now(timezone.utc)):
        usuario.plan = Plan.GRATIS
        sesion.commit()
    return usuario


def obtener_token_csrf(peticion: Request) -> str:
    """Crea un token ligado a la cookie de sesión, nunca a localStorage."""
    token = peticion.session.get("token_csrf")
    if not isinstance(token, str) or len(token) < 32:
        token = token_urlsafe(32)
        peticion.session["token_csrf"] = token
    return token


def verificar_csrf(
    peticion: Request,
    token_csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    """Exige prueba de la sesión para cambios autenticados mediante cookie.

    El acceso Bearer solo existe en desarrollo local y se conserva para las
    pruebas automatizadas; no utiliza la cookie de sesión.
    """
    if not peticion.session.get("usuario_id"):
        return
    token_guardado = peticion.session.get("token_csrf")
    if (
        not isinstance(token_guardado, str)
        or not token_csrf
        or not compare_digest(token_guardado, token_csrf)
    ):
        raise HTTPException(
            403, "La solicitud de seguridad expiró. Actualiza la página e inténtalo de nuevo."
        )


def obtener_usuario_actual(
    peticion: Request,
    autorizacion: str | None = Header(default=None, alias="Authorization"),
    sesion: Session = Depends(obtener_sesion),
) -> Usuario:
    configuracion = peticion.app.state.configuracion
    usuario_id = peticion.session.get("usuario_id")
    if usuario_id:
        usuario = sesion.get(Usuario, usuario_id)
        if usuario is not None:
            return actualizar_plan_vencido(sesion, usuario)
    if configuracion.entorno != "desarrollo" or not configuracion.clave_pruebas:
        raise HTTPException(401, "Se requiere iniciar sesión con Google.")
    if peticion.client is None or peticion.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "La identidad de desarrollo solo funciona desde este equipo.")
    tipo, separador, clave = (autorizacion or "").partition(" ")
    if (
        tipo.lower() != "bearer"
        or not separador
        or not compare_digest(clave, configuracion.clave_pruebas)
    ):
        raise HTTPException(401, "Se requiere la clave local de desarrollo.")

    identificador = f"desarrollo:{configuracion.usuario_pruebas}"
    usuario = sesion.scalar(select(Usuario).where(Usuario.identificador_externo == identificador))
    if usuario is None:
        usuario = Usuario(identificador_externo=identificador)
        sesion.add(usuario)
        sesion.commit()
        sesion.refresh(usuario)
    return actualizar_plan_vencido(sesion, usuario)


def obtener_administrador(
    peticion: Request,
    usuario: Usuario = Depends(obtener_usuario_actual),
) -> Usuario:
    correo_autorizado = (
        (peticion.app.state.configuracion.correo_administrador or "").strip().lower()
    )
    if (
        not correo_autorizado
        or not usuario.es_administrador
        or usuario.correo_google != correo_autorizado
    ):
        raise HTTPException(403, "Solo la cuenta administradora puede acceder a este módulo.")
    return usuario
