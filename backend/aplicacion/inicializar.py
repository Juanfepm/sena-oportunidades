"""Crea el esquema local de desarrollo. Producción requerirá migraciones."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from .base_datos import Base, crear_motor
from .configuracion import Configuracion
from .modelos import NavegadorSGVA  # Importa también las demás tablas del módulo.


def inicializar() -> None:
    configuracion = Configuracion.desde_entorno()
    if configuracion.entorno != "desarrollo":
        raise RuntimeError("La inicialización automática solo está permitida en desarrollo.")
    direccion = make_url(configuracion.base_datos)
    if direccion.get_backend_name() == "sqlite" and direccion.database != ":memory:":
        Path(direccion.database).parent.mkdir(parents=True, exist_ok=True)
    motor = crear_motor(configuracion)
    Base.metadata.create_all(motor)
    with Session(motor) as sesion:
        if sesion.scalar(select(NavegadorSGVA).where(NavegadorSGVA.id == 1)) is None:
            sesion.add(NavegadorSGVA(id=1))
            sesion.commit()
    motor.dispose()


if __name__ == "__main__":
    inicializar()
