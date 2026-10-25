"""Un navegador por proceso; credenciales solo en la cola volátil."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from ..dominio.estados import EstadoCampana
from ..esquemas import PATRON_CORREO
from ..integraciones.contratos import AccesoSGVARestringido, SGVANoDisponible
from ..integraciones.sgva import consultar_sgva, normalizar
from ..modelos import Campana, CorreoExcluido, Destinatario, NavegadorSGVA
from .cola import liberar, renovar_reserva, reservar_siguiente


AccesoEnCola = tuple[str, str, str]
REGISTRO = logging.getLogger(__name__)


def interrumpir_sin_credenciales(sesion: Session) -> None:
    """Tras reiniciar no puede retomarse una consulta cuyo secreto se descartó."""
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


def guardar_ofertas(sesion: Session, campana: Campana, ofertas) -> int:
    excluidos = set(sesion.scalars(select(CorreoExcluido.correo).where(CorreoExcluido.usuario_id == campana.usuario_id)))
    sesion.execute(delete(Destinatario).where(Destinatario.campana_id == campana.id))
    correos_vistos: set[str] = set()
    cantidad = 0
    for oferta in ofertas:
        correo = (oferta.correo or "").strip().lower() or None
        if correo and not PATRON_CORREO.fullmatch(correo):
            correo = None
        if correo and (correo in excluidos or correo in correos_vistos):
            continue
        if correo:
            correos_vistos.add(correo)
        if campana.departamento != "todos" and normalizar(oferta.departamento) != normalizar(campana.departamento):
            continue
        if campana.ciudad != "todas" and normalizar(oferta.ciudad) != normalizar(campana.ciudad):
            continue
        sesion.add(Destinatario(
            campana_id=campana.id,
            nombre_empresa=oferta.nombre_empresa[:180],
            correo=correo,
            telefono_original=(oferta.telefono_original or "")[:80] or None,
            descripcion=oferta.descripcion,
            departamento=oferta.departamento[:80],
            ciudad=oferta.ciudad[:80],
            dias_publicada=oferta.dias_publicada,
            motivo="Oferta encontrada en SGVA. Análisis de coincidencia pendiente.",
            puntuacion=None,
            estado="pendiente_ia",
        ))
        cantidad += 1
    return cantidad


async def procesar_acceso(fabrica: sessionmaker[Session], acceso: AccesoEnCola) -> None:
    campana_id, documento, clave = acceso
    with fabrica() as sesion:
        campana = reservar_siguiente(sesion, datetime.now(timezone.utc), campana_id)
        if campana is None:
            return
        filtros = (campana.departamento, campana.ciudad, campana.antiguedad_dias)
        sesion.commit()
    try:
        async def avance(porcentaje: int, etapa: str) -> None:
            with fabrica() as sesion:
                actual = sesion.get(Campana, campana_id)
                if actual is None or actual.estado != EstadoCampana.CONSULTANDO:
                    raise RuntimeError("La consulta ya no está activa.")
                renovar_reserva(sesion, actual, datetime.now(timezone.utc))
                actual.progreso = porcentaje
                actual.etapa = etapa[:80]
                sesion.commit()

        ofertas = await consultar_sgva(documento, clave, *filtros, avance=avance)
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana is None or campana.estado != EstadoCampana.CONSULTANDO:
                return
            renovar_reserva(sesion, campana, datetime.now(timezone.utc))
            cantidad = guardar_ofertas(sesion, campana, ofertas)
            campana.progreso = 100
            campana.etapa = f"{cantidad} ofertas de SGVA para revisar; análisis de IA pendiente"
            liberar(sesion, campana, EstadoCampana.ESPERANDO_CONFIRMACION)
            sesion.commit()
    except (AccesoSGVARestringido, SGVANoDisponible) as error:
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana and campana.estado == EstadoCampana.CONSULTANDO:
                campana.etapa = "SGVA rechazó la consulta" if isinstance(error, AccesoSGVARestringido) else "SGVA no respondió"
                liberar(sesion, campana, EstadoCampana.ERROR)
                sesion.commit()
    except asyncio.CancelledError:
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana and campana.estado == EstadoCampana.CONSULTANDO:
                campana.etapa = "Consulta interrumpida; crea otra búsqueda"
                liberar(sesion, campana, EstadoCampana.INTERRUMPIDA)
                sesion.commit()
        raise
    except Exception:
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana and campana.estado == EstadoCampana.CONSULTANDO:
                campana.etapa = "No fue posible completar la consulta"
                liberar(sesion, campana, EstadoCampana.ERROR)
                sesion.commit()


async def vigilar_consultas(fabrica: sessionmaker[Session], cola: asyncio.Queue[AccesoEnCola]) -> None:
    while True:
        acceso = await cola.get()
        try:
            await procesar_acceso(fabrica, acceso)
        except asyncio.CancelledError:
            raise
        except Exception:
            REGISTRO.exception("La consulta SGVA no pudo continuar para la campaña %s", acceso[0])
            try:
                with fabrica() as sesion:
                    campana = sesion.get(Campana, acceso[0])
                    if campana and campana.estado == EstadoCampana.EN_COLA:
                        campana.estado = EstadoCampana.ERROR
                        campana.etapa = "No fue posible iniciar la consulta SGVA"
                        sesion.commit()
            except Exception:
                REGISTRO.exception("No se pudo marcar como fallida la consulta SGVA %s", acceso[0])
        finally:
            cola.task_done()
            del acceso
