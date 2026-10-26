"""Registra la identidad verificada y su permiso Gmail en una transacción."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..configuracion import Configuracion
from ..integraciones.cifrado import ClaveCifradoInvalida, cifrar_token, descifrar_token
from ..integraciones.oauth_google import PERMISO_ENVIO_GMAIL, CredencialesGoogle
from ..modelos import ConexionGmail, Usuario


class IdentidadGoogleInvalida(ValueError):
    """La cuenta de Google no entregó una identidad verificada."""


class PermisoGmailAusente(ValueError):
    """No hay un permiso de Gmail válido para esta cuenta."""


def registrar_cuenta(
    sesion: Session, configuracion: Configuracion, credenciales: CredencialesGoogle
) -> Usuario:
    identidad, token = credenciales.identidad, credenciales.token
    sujeto = str(identidad.get("sub", "")).strip()
    correo = str(identidad.get("email", "")).strip().lower()
    if not sujeto or not correo or identidad.get("email_verified") is not True:
        raise IdentidadGoogleInvalida("La identidad de Google no está verificada.")
    permisos = token.get("scope")
    if not isinstance(permisos, str) or PERMISO_ENVIO_GMAIL not in permisos.split():
        raise PermisoGmailAusente("Google no autorizó el envío por Gmail.")

    usuario = sesion.scalar(
        select(Usuario).where(Usuario.identificador_externo == f"google:{sujeto}")
    )
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
    usuario.es_administrador = bool(
        configuracion.correo_administrador
        and correo == configuracion.correo_administrador.strip().lower()
    )

    try:
        sesion.flush()
        conexion = sesion.scalar(
            select(ConexionGmail).where(ConexionGmail.usuario_id == usuario.id)
        )
        token_renovacion = token.get("refresh_token")
        if token_renovacion:
            token_cifrado = cifrar_token(str(token_renovacion), configuracion.clave_cifrado)
            if conexion is None:
                sesion.add(
                    ConexionGmail(
                        usuario_id=usuario.id,
                        correo_google=correo,
                        token_renovacion_cifrado=token_cifrado,
                        permisos=PERMISO_ENVIO_GMAIL,
                    )
                )
            else:
                conexion.correo_google = correo
                conexion.token_renovacion_cifrado = token_cifrado
                conexion.permisos = PERMISO_ENVIO_GMAIL
        elif (
            conexion is None
            or conexion.correo_google != correo
            or conexion.permisos != PERMISO_ENVIO_GMAIL
        ):
            raise PermisoGmailAusente("Vuelve a vincular Gmail con Google.")
        else:
            descifrar_token(conexion.token_renovacion_cifrado, configuracion.clave_cifrado)
        sesion.commit()
    except (ClaveCifradoInvalida, PermisoGmailAusente):
        sesion.rollback()
        raise
    return usuario
