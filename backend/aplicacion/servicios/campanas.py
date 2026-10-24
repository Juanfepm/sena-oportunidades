"""Borradores: conservan filtros, no credenciales ni contenido del correo."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dominio.estados import LIMITES_CONTACTO, Plan
from ..esquemas import SolicitudBorrador
from ..modelos import Campana, CorreoExcluido, Usuario


def crear_borrador(sesion: Session, usuario: Usuario, solicitud: SolicitudBorrador) -> Campana:
    plan = Plan(usuario.plan)
    existentes = set(sesion.scalars(select(CorreoExcluido.correo).where(CorreoExcluido.usuario_id == usuario.id)))
    sesion.add_all(
        CorreoExcluido(usuario_id=usuario.id, correo=correo)
        for correo in solicitud.correos_excluidos
        if correo not in existentes
    )
    campana = Campana(
        usuario_id=usuario.id,
        plan_aplicado=plan,
        limite_contactos=LIMITES_CONTACTO[plan],
        modalidad=solicitud.modalidad,
        departamento=solicitud.departamento,
        ciudad=solicitud.ciudad,
        antiguedad_dias=solicitud.antiguedad_dias,
        permitir_recontacto=solicitud.permitir_recontacto,
    )
    sesion.add(campana)
    sesion.commit()
    sesion.refresh(campana)
    return campana


def listar_borradores(sesion: Session, usuario: Usuario, limite: int = 50) -> list[Campana]:
    consulta = select(Campana).where(Campana.usuario_id == usuario.id).order_by(Campana.creado_en.desc()).limit(limite)
    return list(sesion.scalars(consulta))


def consultar_campana(sesion: Session, usuario: Usuario, campana_id: str) -> Campana | None:
    consulta = select(Campana).where(Campana.id == campana_id, Campana.usuario_id == usuario.id)
    return sesion.scalar(consulta)
