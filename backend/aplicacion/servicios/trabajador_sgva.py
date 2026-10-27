"""Un navegador por proceso; credenciales solo en la cola volátil."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from ..dominio.estados import EstadoCampana
from ..dominio.ofertas import EvaluacionIA
from ..dominio.texto import limpiar_texto_externo
from ..esquemas import PATRON_CORREO
from ..integraciones.contratos import (
    AccesoSGVARestringido,
    IntegracionNoDisponible,
    SGVAEntornoIncompatible,
    SGVANoDisponible,
)
from ..integraciones.ia import clasificar_ofertas
from ..integraciones.sgva import consultar_sgva, normalizar
from ..modelos import (
    AdjuntoTemporal,
    Campana,
    ContenidoTemporal,
    CorreoExcluido,
    Destinatario,
    NavegadorSGVA,
)
from .cola import liberar, renovar_reserva, reservar_siguiente
from .temporales import eliminar_contenido

AccesoEnCola = tuple[str, str, str, dict[str, str] | None]
REGISTRO = logging.getLogger(__name__)


def interrumpir_sin_credenciales(sesion: Session) -> None:
    """Tras reiniciar no puede retomarse una consulta cuyo secreto se descartó."""
    interrumpidas = select(Campana.id).where(
        Campana.estado.in_([EstadoCampana.EN_COLA, EstadoCampana.CONSULTANDO])
    )
    sesion.execute(delete(AdjuntoTemporal).where(AdjuntoTemporal.campana_id.in_(interrumpidas)))
    sesion.execute(
        delete(ContenidoTemporal).where(ContenidoTemporal.campana_id.in_(interrumpidas))
    )
    sesion.execute(
        update(Campana)
        .where(Campana.estado.in_([EstadoCampana.EN_COLA, EstadoCampana.CONSULTANDO]))
        .values(estado=EstadoCampana.INTERRUMPIDA, etapa="Servidor reiniciado; crea otra búsqueda")
    )
    navegador = sesion.get(NavegadorSGVA, 1, with_for_update=True)
    if navegador is not None:
        navegador.campana_id = None
        navegador.reserva_hasta = None
    sesion.commit()


def filtrar_ofertas(sesion: Session, campana: Campana, ofertas: list) -> list:
    """Aplica exclusiones antes de enviar descripciones al clasificador."""
    excluidos = set(
        sesion.scalars(
            select(CorreoExcluido.correo).where(CorreoExcluido.usuario_id == campana.usuario_id)
        )
    )
    correos_vistos: set[str] = set()
    filtradas = []
    for oferta in ofertas:
        correo = (oferta.correo or "").strip().lower() or None
        if correo and not PATRON_CORREO.fullmatch(correo):
            correo = None
        if correo and (correo in excluidos or correo in correos_vistos):
            continue
        if campana.departamento != "todos" and normalizar(oferta.departamento) != normalizar(
            campana.departamento
        ):
            continue
        if campana.ciudad != "todas" and normalizar(oferta.ciudad) != normalizar(campana.ciudad):
            continue
        if correo:
            correos_vistos.add(correo)
        filtradas.append(oferta)
    return filtradas


def guardar_ofertas(
    sesion: Session,
    campana: Campana,
    ofertas,
    evaluaciones: list[EvaluacionIA | None] | None = None,
) -> int:
    sesion.execute(delete(Destinatario).where(Destinatario.campana_id == campana.id))
    for indice, oferta in enumerate(ofertas):
        correo = (oferta.correo or "").strip().lower() or None
        if correo and not PATRON_CORREO.fullmatch(correo):
            correo = None
        evaluacion = evaluaciones[indice] if evaluaciones and indice < len(evaluaciones) else None
        modalidad = evaluacion.modalidad if evaluacion else None
        alta = bool(evaluacion and evaluacion.puntuacion >= 80 and modalidad == "confirmada")
        estado = "alta_coincidencia" if alta else "por_revisar" if evaluacion else "pendiente_ia"
        motivo = (
            f"{evaluacion.motivo} Modalidad {modalidad.replace('_', ' ')}; "
            "confirma con la empresa."
            if evaluacion
            else "Oferta encontrada en SGVA. Análisis de coincidencia pendiente."
        )
        sesion.add(
            Destinatario(
                campana_id=campana.id,
                nombre_empresa=limpiar_texto_externo(oferta.nombre_empresa)[:180],
                correo=correo,
                telefono_original=limpiar_texto_externo(oferta.telefono_original or "")[:80]
                or None,
                descripcion=limpiar_texto_externo(oferta.descripcion, multilinea=True),
                departamento=limpiar_texto_externo(oferta.departamento)[:80],
                ciudad=limpiar_texto_externo(oferta.ciudad)[:80],
                dias_publicada=oferta.dias_publicada,
                motivo=limpiar_texto_externo(motivo),
                puntuacion=evaluacion.puntuacion if evaluacion else None,
                estado=estado,
            )
        )
    return len(ofertas)


async def procesar_acceso(
    fabrica: sessionmaker[Session], acceso: AccesoEnCola, clave_ia: str | None = None
) -> None:
    campana_id, documento, clave, perfil = acceso
    with fabrica() as sesion:
        campana = reservar_siguiente(sesion, datetime.now(timezone.utc), campana_id)
        if campana is None:
            return
        filtros = (campana.departamento, campana.ciudad, campana.antiguedad_dias)
        modalidad = campana.modalidad
        sesion.commit()
    try:

        async def avance(porcentaje: int, etapa: str) -> None:
            with fabrica() as sesion:
                actual = sesion.get(Campana, campana_id)
                if actual is None or actual.estado != EstadoCampana.CONSULTANDO:
                    raise RuntimeError("La consulta ya no está activa.")
                renovar_reserva(sesion, actual, datetime.now(timezone.utc))
                actual.progreso = max(actual.progreso, porcentaje)
                actual.etapa = etapa[:80]
                sesion.commit()

        ofertas = await consultar_sgva(documento, clave, *filtros, avance=avance)
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana is None or campana.estado != EstadoCampana.CONSULTANDO:
                return
            ofertas = filtrar_ofertas(sesion, campana, ofertas)
        evaluaciones = None
        if perfil and clave_ia and ofertas:
            try:
                evaluaciones = await clasificar_ofertas(
                    clave_ia, perfil, modalidad, ofertas, avance
                )
            except IntegracionNoDisponible:
                REGISTRO.warning("La IA no completó el análisis de la campaña %s", campana_id)
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana is None or campana.estado != EstadoCampana.CONSULTANDO:
                return
            renovar_reserva(sesion, campana, datetime.now(timezone.utc))
            cantidad = guardar_ofertas(sesion, campana, ofertas, evaluaciones)
            campana.progreso = 100
            analizadas = sum(evaluacion is not None for evaluacion in evaluaciones or [])
            campana.etapa = (
                f"{analizadas} de {cantidad} ofertas analizadas para revisar"
                if analizadas
                else f"{cantidad} ofertas de SGVA para revisar; análisis de IA pendiente"
            )
            liberar(sesion, campana, EstadoCampana.ESPERANDO_CONFIRMACION)
            sesion.commit()
    except (AccesoSGVARestringido, SGVANoDisponible) as error:
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana and campana.estado == EstadoCampana.CONSULTANDO:
                if isinstance(error, SGVAEntornoIncompatible):
                    campana.etapa = "Reinicia el servidor sin --reload en Windows"
                else:
                    campana.etapa = (
                        f"SGVA rechazó la consulta: {error}"[:80]
                        if isinstance(error, AccesoSGVARestringido)
                        else "SGVA no respondió"
                    )
                liberar(sesion, campana, EstadoCampana.ERROR)
                sesion.commit()
                eliminar_contenido(sesion, campana)
    except asyncio.CancelledError:
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana and campana.estado == EstadoCampana.CONSULTANDO:
                campana.etapa = "Consulta interrumpida; crea otra búsqueda"
                liberar(sesion, campana, EstadoCampana.INTERRUMPIDA)
                sesion.commit()
                eliminar_contenido(sesion, campana)
        raise
    except Exception:
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana and campana.estado == EstadoCampana.CONSULTANDO:
                campana.etapa = "No fue posible completar la consulta"
                liberar(sesion, campana, EstadoCampana.ERROR)
                sesion.commit()
                eliminar_contenido(sesion, campana)


async def vigilar_consultas(
    fabrica: sessionmaker[Session],
    cola: asyncio.Queue[AccesoEnCola],
    clave_ia: str | None = None,
    tareas_activas: dict[str, asyncio.Task] | None = None,
) -> None:
    tareas_activas = tareas_activas if tareas_activas is not None else {}
    while True:
        acceso = await cola.get()
        operacion = asyncio.create_task(procesar_acceso(fabrica, acceso, clave_ia))
        tareas_activas[acceso[0]] = operacion
        try:
            await operacion
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            # La cancelación de una consulta no detiene el navegador para las siguientes.
        except Exception:
            REGISTRO.exception("La consulta SGVA no pudo continuar para la campaña %s", acceso[0])
            try:
                with fabrica() as sesion:
                    campana = sesion.get(Campana, acceso[0])
                    if campana and campana.estado == EstadoCampana.EN_COLA:
                        campana.estado = EstadoCampana.ERROR
                        campana.etapa = "No fue posible iniciar la consulta SGVA"
                        sesion.commit()
                        eliminar_contenido(sesion, campana)
            except Exception:
                REGISTRO.exception("No se pudo marcar como fallida la consulta SGVA %s", acceso[0])
        finally:
            tareas_activas.pop(acceso[0], None)
            cola.task_done()
            del acceso
