"""Trabajador temporal para probar la cola sin conectarse todavía a SGVA.

El flujo real sustituirá este adaptador por la integración autorizada con SGVA.
No recibe ni almacena credenciales y nunca pulsa «Aplicar».
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from ..dominio.estados import EstadoCampana
from ..modelos import Campana
from .cola import encolar, liberar, renovar_reserva, reservar_siguiente


async def ejecutar_campana_demo(fabrica: sessionmaker[Session], campana_id: str) -> None:
    """Procesa una campaña en modo demostración y deja su avance persistido."""
    with fabrica() as sesion:
        campana = sesion.get(Campana, campana_id)
        if campana is None or campana.estado != EstadoCampana.BORRADOR:
            return
        encolar(sesion, campana)
        sesion.commit()

    with fabrica() as sesion:
        fecha = datetime.now(timezone.utc)
        campana = sesion.get(Campana, campana_id)
        siguiente = reservar_siguiente(sesion, fecha)
        sesion.commit()
        if siguiente is None or siguiente.id != campana_id:
            return

    etapas = (
        (20, "Validando filtros de la campaña"),
        (40, "Preparando la consulta de demostración"),
        (60, "Resultados listos para revisión"),
    )
    for progreso, etapa in etapas:
        await asyncio.sleep(0)
        with fabrica() as sesion:
            campana = sesion.get(Campana, campana_id)
            if campana is None or campana.estado != EstadoCampana.CONSULTANDO:
                return
            renovar_reserva(sesion, campana, datetime.now(timezone.utc))
            campana.progreso = progreso
            campana.etapa = etapa
            sesion.commit()

    with fabrica() as sesion:
        campana = sesion.get(Campana, campana_id)
        if campana is None or campana.estado != EstadoCampana.CONSULTANDO:
            return
        campana.etapa = "Resultados listos para revisión"
        campana.progreso = 60
        liberar(sesion, campana, EstadoCampana.ESPERANDO_CONFIRMACION)
        sesion.commit()

