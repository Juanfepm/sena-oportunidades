"""Consultas de permisos Gmail usados por distintos casos de uso."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..modelos import ConexionGmail, Usuario
from .resumen_correo import CORREO_DEBUPA


def obtener_conexion_resumen(sesion: Session) -> ConexionGmail | None:
    """Exige que el permiso pertenezca a la cuenta verificada de DEBUPA."""
    return sesion.scalar(
        select(ConexionGmail)
        .join(Usuario, Usuario.id == ConexionGmail.usuario_id)
        .where(
            Usuario.correo_google == CORREO_DEBUPA,
            ConexionGmail.correo_google == CORREO_DEBUPA,
        )
    )
