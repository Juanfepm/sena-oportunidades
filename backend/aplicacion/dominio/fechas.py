"""Operaciones de calendario independientes de la base de datos y la API."""

import calendar
from datetime import datetime


def desplazar_meses(fecha: datetime, cantidad: int) -> datetime:
    indice = fecha.year * 12 + fecha.month - 1 + cantidad
    anio, mes_indice = divmod(indice, 12)
    mes = mes_indice + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)
