"""Conexión y sesiones de base de datos."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .configuracion import Configuracion


class Base(DeclarativeBase):
    pass


def crear_motor(configuracion: Configuracion) -> Engine:
    opciones = (
        {"check_same_thread": False} if configuracion.base_datos.startswith("sqlite:") else {}
    )
    return create_engine(configuracion.base_datos, connect_args=opciones, pool_pre_ping=True)


def obtener_sesion(peticion: Request) -> Iterator[Session]:
    fabrica: sessionmaker[Session] = peticion.app.state.fabrica_sesiones
    with fabrica() as sesion:
        yield sesion
