"""Contratos públicos con validación independiente del navegador."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .dominio.ubicaciones import MUNICIPIOS_POR_DEPARTAMENTO


PATRON_CORREO = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PATRON_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class SolicitudBorrador(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    modalidad: Literal["remoto", "hibrido", "presencial"]
    departamento: str = Field(min_length=1, max_length=80)
    ciudad: str = Field(default="todas", min_length=1, max_length=80)
    antiguedad_dias: Literal[0, 7, 14, 30]
    permitir_recontacto: bool = False
    correos_excluidos: list[str] = Field(default_factory=list, max_length=5)
    mayor_de_edad: Literal[True]
    acepta_tratamiento: Literal[True]

    @field_validator("departamento", "ciudad")
    @classmethod
    def limpiar_ubicacion(cls, valor: str) -> str:
        if PATRON_CONTROL.search(valor):
            raise ValueError("La ubicación contiene caracteres de control.")
        return valor

    @field_validator("correos_excluidos")
    @classmethod
    def validar_correos(cls, correos: list[str]) -> list[str]:
        normalizados = [correo.strip().lower() for correo in correos]
        if any(len(correo) > 254 or not PATRON_CORREO.fullmatch(correo) for correo in normalizados):
            raise ValueError("Todos los correos excluidos deben ser válidos.")
        return list(dict.fromkeys(normalizados))

    @model_validator(mode="after")
    def validar_ubicacion(self) -> "SolicitudBorrador":
        if self.modalidad == "remoto" and (self.departamento != "todos" or self.ciudad != "todas"):
            raise ValueError("La modalidad remota requiere todos los departamentos y ciudades.")
        if self.departamento == "todos" and self.ciudad != "todas":
            raise ValueError("Para seleccionar una ciudad debes elegir un departamento.")
        if self.departamento != "todos":
            if self.departamento not in MUNICIPIOS_POR_DEPARTAMENTO:
                raise ValueError("El departamento no está disponible.")
            if self.ciudad != "todas" and self.ciudad not in MUNICIPIOS_POR_DEPARTAMENTO[self.departamento]:
                raise ValueError("El municipio no pertenece al departamento seleccionado.")
        return self


class ResumenCampana(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    estado: str
    etapa: str
    progreso: int
    plan_aplicado: str
    limite_contactos: int
    modalidad: str
    departamento: str
    ciudad: str
    antiguedad_dias: int
    permitir_recontacto: bool
    creado_en: datetime


class ResumenHistorial(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    correo: str
    enviado_en: datetime
    campana_id: str
