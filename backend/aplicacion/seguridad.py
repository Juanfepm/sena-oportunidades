"""Acceso local de desarrollo; Google OAuth reemplazará esta dependencia."""

from hmac import compare_digest

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .base_datos import obtener_sesion
from .modelos import Usuario


def obtener_usuario_actual(
    peticion: Request,
    autorizacion: str | None = Header(default=None, alias="Authorization"),
    sesion: Session = Depends(obtener_sesion),
) -> Usuario:
    configuracion = peticion.app.state.configuracion
    if configuracion.entorno != "desarrollo" or not configuracion.clave_pruebas:
        raise HTTPException(503, "La identidad de Google todavía no está conectada.")
    if peticion.client is None or peticion.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "La identidad de desarrollo solo funciona desde este equipo.")
    tipo, separador, clave = (autorizacion or "").partition(" ")
    if tipo.lower() != "bearer" or not separador or not compare_digest(clave, configuracion.clave_pruebas):
        raise HTTPException(401, "Se requiere la clave local de desarrollo.")

    identificador = f"desarrollo:{configuracion.usuario_pruebas}"
    usuario = sesion.scalar(select(Usuario).where(Usuario.identificador_externo == identificador))
    if usuario is None:
        usuario = Usuario(identificador_externo=identificador)
        sesion.add(usuario)
        sesion.commit()
        sesion.refresh(usuario)
    return usuario
