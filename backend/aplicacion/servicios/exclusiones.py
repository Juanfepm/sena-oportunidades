"""Lista persistente de empresas que el aprendiz no quiere contactar."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..modelos import CorreoExcluido, Usuario


def listar_exclusiones(sesion: Session, usuario: Usuario) -> list[str]:
    consulta = (
        select(CorreoExcluido.correo)
        .where(CorreoExcluido.usuario_id == usuario.id)
        .order_by(CorreoExcluido.correo)
    )
    return list(sesion.scalars(consulta))


def quitar_exclusion(sesion: Session, usuario: Usuario, correo: str) -> bool:
    sentencia = delete(CorreoExcluido).where(
        CorreoExcluido.usuario_id == usuario.id,
        CorreoExcluido.correo == correo.strip().lower(),
    )
    resultado = sesion.execute(sentencia)
    sesion.commit()
    return bool(resultado.rowcount)
