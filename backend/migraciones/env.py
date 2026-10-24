"""Ejecuta migraciones sin guardar la dirección de conexión en el repositorio."""

from logging.config import fileConfig
from os import getenv

from alembic import context
from sqlalchemy.engine import Connection

from backend.aplicacion.base_datos import Base, crear_motor
from backend.aplicacion.configuracion import Configuracion
from backend.aplicacion import modelos  # noqa: F401; registra las tablas en Base.


configuracion_alembic = context.config
if configuracion_alembic.config_file_name:
    fileConfig(configuracion_alembic.config_file_name)


def direccion_configurada() -> str:
    if not getenv("DEBUPA_BASE_DATOS"):
        raise RuntimeError("Configura DEBUPA_BASE_DATOS antes de ejecutar migraciones.")
    return Configuracion.desde_entorno().base_datos


def ejecutar_con_conexion(conexion: Connection) -> None:
    context.configure(connection=conexion, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def ejecutar_sin_conexion() -> None:
    context.configure(url=direccion_configurada(), target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def ejecutar_en_linea() -> None:
    conexion_compartida = configuracion_alembic.attributes.get("connection")
    if conexion_compartida is not None:
        ejecutar_con_conexion(conexion_compartida)
        return

    direccion_configurada()
    motor = crear_motor(Configuracion.desde_entorno())
    try:
        with motor.connect() as conexion:
            ejecutar_con_conexion(conexion)
    finally:
        motor.dispose()


if context.is_offline_mode():
    ejecutar_sin_conexion()
else:
    ejecutar_en_linea()
