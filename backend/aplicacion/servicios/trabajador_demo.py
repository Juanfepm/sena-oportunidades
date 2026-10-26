"""Consulta periódica de la cola con ofertas ficticias para probar el flujo."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ..dominio.estados import EstadoCampana
from ..dominio.ofertas import OfertaSGVA, cumple_filtros
from ..modelos import Campana, CorreoExcluido, Destinatario, NavegadorSGVA
from .cola import liberar, renovar_reserva, reservar_siguiente

REGISTRO = logging.getLogger(__name__)
INTERVALO_COLA = 10

OFERTAS_EJEMPLO = (
    (
        OfertaSGVA(
            "Nexo Digital",
            "ejemplo@nexo.invalid",
            "300 000 0000",
            "Contenido y organización digital",
            "Bogotá D. C.",
            "Bogotá",
            0,
        ),
        "remoto",
        88,
        "Funciones digitales afines; modalidad remota por confirmar.",
    ),
    (
        OfertaSGVA(
            "Álamo Creativo",
            "ejemplo@alamo.invalid",
            "(604) 000 0000",
            "Diseño y apoyo a proyectos",
            "Antioquia",
            "Medellín",
            4,
        ),
        "hibrido",
        82,
        "Diseño y proyectos afines; jornada híbrida por confirmar.",
    ),
    (
        OfertaSGVA(
            "Brisa Estudio",
            "ejemplo@brisa.invalid",
            "310 000 0000",
            "Apoyo en tareas de oficina",
            "Valle del Cauca",
            "Cali",
            13,
        ),
        "presencial",
        76,
        "Algunas funciones pueden coincidir; requiere revisión.",
    ),
    (
        OfertaSGVA(
            "Savia Lab",
            "ejemplo@savia.invalid",
            "601 000 0000",
            "Trabajo de contenidos digitales",
            "Bogotá D. C.",
            "Bogotá",
            25,
        ),
        "remoto",
        71,
        "Funciones y ubicación por confirmar con la empresa.",
    ),
)


def preparar_ofertas(sesion: Session, campana: Campana) -> int:
    """Guarda resultados de prueba, filtrados con las preferencias persistidas."""
    excluidos = set(
        sesion.scalars(
            select(CorreoExcluido.correo).where(CorreoExcluido.usuario_id == campana.usuario_id)
        )
    )
    sesion.execute(delete(Destinatario).where(Destinatario.campana_id == campana.id))
    cantidad = 0
    for oferta, modalidad, puntuacion, motivo in OFERTAS_EJEMPLO:
        if modalidad != campana.modalidad or oferta.correo in excluidos:
            continue
        if not cumple_filtros(
            oferta,
            campana.modalidad,
            campana.departamento,
            campana.ciudad,
            campana.antiguedad_dias,
        ):
            continue
        sesion.add(
            Destinatario(
                campana_id=campana.id,
                nombre_empresa=oferta.nombre_empresa,
                correo=oferta.correo,
                telefono_original=oferta.telefono_original,
                puntuacion=puntuacion,
                motivo=motivo,
                estado="ejemplo_no_enviado",
            )
        )
        cantidad += 1
    return cantidad


def recuperar_reserva_vencida(sesion: Session, ahora: datetime) -> None:
    """Reencola solo el trabajo ficticio; repetirlo no produce efectos externos."""
    navegador = sesion.get(NavegadorSGVA, 1, with_for_update=True)
    if navegador is None or not navegador.campana_id:
        return
    vencimiento = navegador.reserva_hasta
    if (
        vencimiento is not None
        and (vencimiento if vencimiento.tzinfo else vencimiento.replace(tzinfo=timezone.utc))
        > ahora
    ):
        return
    campana = sesion.get(Campana, navegador.campana_id)
    if campana is not None and campana.estado == EstadoCampana.CONSULTANDO:
        campana.estado = EstadoCampana.EN_COLA
        campana.etapa = "Reanudando demostración tras una interrupción"
        campana.progreso = 0
    navegador.campana_id = None
    navegador.reserva_hasta = None
    sesion.flush()


async def procesar_siguiente(fabrica: sessionmaker[Session]) -> bool:
    """Procesa una campaña por reserva, dejando el avance visible en PostgreSQL."""
    with fabrica() as sesion:
        ahora = datetime.now(timezone.utc)
        if sesion.get(NavegadorSGVA, 1) is None:
            return False
        recuperar_reserva_vencida(sesion, ahora)
        campana = reservar_siguiente(sesion, ahora)
        campana_id = campana.id if campana else None
        sesion.commit()
    if campana_id is None:
        return False

    try:
        for progreso, etapa in (
            (20, "Validando filtros de ejemplo"),
            (40, "Preparando ofertas ficticias"),
        ):
            await asyncio.sleep(1)
            with fabrica() as sesion:
                campana = sesion.get(Campana, campana_id)
                renovar_reserva(sesion, campana, datetime.now(timezone.utc))
                campana.progreso = progreso
                campana.etapa = etapa
                sesion.commit()
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            renovar_reserva(sesion, campana, datetime.now(timezone.utc))
            cantidad = preparar_ofertas(sesion, campana)
            campana.progreso = 100
            campana.etapa = (
                "Ofertas de ejemplo para revisar"
                if cantidad
                else "Sin ofertas de ejemplo para estos filtros"
            )
            liberar(sesion, campana, EstadoCampana.ESPERANDO_CONFIRMACION)
            sesion.commit()
    except asyncio.CancelledError:
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana and campana.estado == EstadoCampana.CONSULTANDO:
                campana.etapa = "Reanudando demostración"
                liberar(sesion, campana, EstadoCampana.EN_COLA)
                sesion.commit()
        raise
    except Exception:
        REGISTRO.exception("Falló la campaña de demostración %s", campana_id)
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana and campana.estado == EstadoCampana.CONSULTANDO:
                campana.etapa = "No se pudo preparar la demostración"
                liberar(sesion, campana, EstadoCampana.ERROR)
                sesion.commit()
    return True


async def vigilar_cola(fabrica: sessionmaker[Session], aviso: asyncio.Event) -> None:
    while True:
        try:
            procesada = await procesar_siguiente(fabrica)
            if procesada:
                continue
            try:
                await asyncio.wait_for(aviso.wait(), timeout=INTERVALO_COLA)
            except TimeoutError:
                pass
            aviso.clear()
        except asyncio.CancelledError:
            raise
        except Exception:
            REGISTRO.exception("No se pudo consultar la cola de demostración")
            await asyncio.sleep(INTERVALO_COLA)
