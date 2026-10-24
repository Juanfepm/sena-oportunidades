"""Reserva persistente para un único navegador SGVA."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dominio.estados import EstadoCampana
from ..modelos import Campana, NavegadorSGVA


def _con_zona(fecha: datetime) -> datetime:
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def encolar(sesion: Session, campana: Campana) -> None:
    if campana.estado != EstadoCampana.BORRADOR:
        raise ValueError("Solo un borrador puede entrar en la cola.")
    campana.estado = EstadoCampana.EN_COLA
    campana.etapa = "En espera del navegador SGVA"
    sesion.flush()


def reservar_siguiente(sesion: Session, fecha_actual: datetime) -> Campana | None:
    navegador = sesion.get(NavegadorSGVA, 1, with_for_update=True)
    if navegador is None:
        raise RuntimeError("Inicializa la reserva del navegador antes de iniciar el trabajador.")
    if navegador.campana_id and navegador.reserva_hasta and _con_zona(navegador.reserva_hasta) > _con_zona(fecha_actual):
        return None
    if navegador.campana_id:
        anterior = sesion.get(Campana, navegador.campana_id)
        if anterior and anterior.estado == EstadoCampana.CONSULTANDO:
            anterior.estado = EstadoCampana.INTERRUMPIDA
            anterior.etapa = "Reserva vencida; requiere revisión"

    consulta = (
        select(Campana)
        .where(Campana.estado == EstadoCampana.EN_COLA)
        .order_by(Campana.creado_en, Campana.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    siguiente = sesion.scalar(consulta)
    navegador.campana_id = siguiente.id if siguiente else None
    navegador.reserva_hasta = fecha_actual + timedelta(minutes=15) if siguiente else None
    if siguiente:
        siguiente.estado = EstadoCampana.CONSULTANDO
        siguiente.etapa = "Consultando SGVA"
        siguiente.progreso = 5
    sesion.flush()
    return siguiente


def renovar_reserva(sesion: Session, campana: Campana, fecha_actual: datetime) -> None:
    navegador = sesion.get(NavegadorSGVA, 1, with_for_update=True)
    if (
        navegador is None
        or navegador.campana_id != campana.id
        or navegador.reserva_hasta is None
        or _con_zona(navegador.reserva_hasta) <= _con_zona(fecha_actual)
    ):
        raise ValueError("La reserva ya no pertenece a esta campaña o ha vencido.")
    navegador.reserva_hasta = fecha_actual + timedelta(minutes=15)
    sesion.flush()


def liberar(sesion: Session, campana: Campana, nuevo_estado: EstadoCampana) -> None:
    navegador = sesion.get(NavegadorSGVA, 1, with_for_update=True)
    if navegador is None or navegador.campana_id != campana.id:
        raise ValueError("La campaña no posee la reserva del navegador.")
    campana.estado = nuevo_estado
    navegador.campana_id = None
    navegador.reserva_hasta = None
    sesion.flush()
