"""Borradores: conservan filtros, no credenciales ni contenido del correo."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dominio.disponibilidad import proxima_busqueda
from ..dominio.estados import LIMITES_CONTACTO, Plan
from ..esquemas import SolicitudBorrador
from ..modelos import Campana, CorreoExcluido, HistorialEnvio, Usuario


class EsperaPlanGratis(Exception):
    def __init__(self, fecha: datetime):
        self.fecha = fecha


def consultar_disponibilidad(
    sesion: Session, usuario: Usuario, ahora: datetime | None = None
) -> datetime | None:
    ultimo_envio = sesion.scalar(
        select(HistorialEnvio.enviado_en)
        .where(HistorialEnvio.usuario_id == usuario.id, HistorialEnvio.estado == "enviado")
        .order_by(HistorialEnvio.enviado_en.desc())
        .limit(1)
    )
    return proxima_busqueda(Plan(usuario.plan), ultimo_envio, ahora or datetime.now(timezone.utc))


def crear_borrador(sesion: Session, usuario: Usuario, solicitud: SolicitudBorrador) -> Campana:
    proxima_fecha = consultar_disponibilidad(sesion, usuario)
    if proxima_fecha is not None:
        raise EsperaPlanGratis(proxima_fecha)
    plan = Plan(usuario.plan)
    existentes = set(
        sesion.scalars(
            select(CorreoExcluido.correo).where(CorreoExcluido.usuario_id == usuario.id)
        )
    )
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
    consulta = (
        select(Campana)
        .where(Campana.usuario_id == usuario.id)
        .order_by(Campana.creado_en.desc())
        .limit(limite)
    )
    return list(sesion.scalars(consulta))


def consultar_campana(sesion: Session, usuario: Usuario, campana_id: str) -> Campana | None:
    consulta = select(Campana).where(Campana.id == campana_id, Campana.usuario_id == usuario.id)
    return sesion.scalar(consulta)
