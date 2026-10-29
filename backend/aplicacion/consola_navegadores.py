"""Activa, desactiva o consulta el segundo navegador SGVA desde la consola."""

import argparse

from sqlalchemy.orm import Session

from .base_datos import crear_motor
from .configuracion import Configuracion
from .modelos import NavegadorSGVA


def main() -> None:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("accion", choices=("activar", "desactivar", "estado"))
    argumentos = analizador.parse_args()

    motor = crear_motor(Configuracion.desde_entorno())
    try:
        with Session(motor) as sesion:
            navegador = sesion.get(NavegadorSGVA, 2, with_for_update=True)
            if navegador is None:
                raise SystemExit("Aplica primero las migraciones: alembic upgrade head")
            if argumentos.accion != "estado":
                navegador.habilitado = argumentos.accion == "activar"
                sesion.commit()
            estado = "activo" if navegador.habilitado else "apagado"
            ocupacion = " (terminando una consulta)" if navegador.campana_id else ""
            print(f"Segundo navegador SGVA: {estado}{ocupacion}.")
    finally:
        motor.dispose()


if __name__ == "__main__":
    main()
