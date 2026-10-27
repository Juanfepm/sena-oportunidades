"""Contratos públicos con validación independiente del navegador."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from .dominio.texto import limpiar_texto
from .dominio.ubicaciones import MUNICIPIOS_POR_DEPARTAMENTO

PATRON_CORREO = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


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
        return limpiar_texto(valor)

    @field_validator("correos_excluidos")
    @classmethod
    def validar_correos(cls, correos: list[str]) -> list[str]:
        normalizados = [correo.strip().lower() for correo in correos]
        if any(
            len(correo) > 254 or not PATRON_CORREO.fullmatch(correo) for correo in normalizados
        ):
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
            if (
                self.ciudad != "todas"
                and self.ciudad not in MUNICIPIOS_POR_DEPARTAMENTO[self.departamento]
            ):
                raise ValueError("El municipio no pertenece al departamento seleccionado.")
        return self


class ResumenCampana(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    estado: str
    modo_consulta: str
    etapa: str
    progreso: int
    seleccion_guardada: bool
    plan_aplicado: str
    limite_contactos: int
    modalidad: str
    departamento: str
    ciudad: str
    antiguedad_dias: int
    permitir_recontacto: bool
    creado_en: datetime


class ResumenDestinatario(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre_empresa: str
    correo: str | None
    telefono_original: str | None
    descripcion: str | None
    departamento: str | None
    ciudad: str | None
    dias_publicada: int | None
    motivo: str
    puntuacion: int | None
    estado: str
    seleccionado: bool


class SolicitudSeleccion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destinatarios: list[str] = Field(max_length=70)

    @field_validator("destinatarios")
    @classmethod
    def validar_destinatarios(cls, identificadores: list[str]) -> list[str]:
        if len(set(identificadores)) != len(identificadores):
            raise ValueError("No repitas empresas en la selección.")
        if any(not 1 <= len(identificador) <= 36 for identificador in identificadores):
            raise ValueError("La selección contiene un identificador inválido.")
        return identificadores


class SolicitudConfirmacionEnvio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destinatarios: list[str] = Field(min_length=1, max_length=70)
    confirmado: Literal[True]
    confirmacion: str = Field(min_length=20, max_length=500)

    @field_validator("destinatarios")
    @classmethod
    def sin_repetidos(cls, identificadores: list[str]) -> list[str]:
        if len(set(identificadores)) != len(identificadores):
            raise ValueError("Hay destinatarios repetidos.")
        return identificadores


class PerfilTemporalIA(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    habilidades: str = Field(min_length=20, max_length=500)
    actividades_deseadas: str = Field(min_length=10, max_length=300)
    actividades_no_deseadas: str = Field(default="", max_length=240)

    @field_validator("habilidades", "actividades_deseadas", "actividades_no_deseadas")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return limpiar_texto(valor, multilinea=True)


class SolicitudAccesoSGVA(BaseModel):
    """Solo existe durante la petición y en la cola de memoria del proceso."""

    model_config = ConfigDict(extra="forbid")
    numero_documento: str = Field(pattern=r"^[0-9]{5,15}$")
    clave_sgva: SecretStr = Field(min_length=1, max_length=128)
    acepta_ia: bool = False
    perfil_ia: PerfilTemporalIA | None = None


class SolicitudContenidoTemporal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    habilidades: str = Field(min_length=20, max_length=500)
    actividades_deseadas: str = Field(min_length=10, max_length=300)
    actividades_no_deseadas: str = Field(default="", max_length=240)
    asunto: str = Field(min_length=3, max_length=100)
    cuerpo: str = Field(min_length=40, max_length=5000)

    @field_validator("habilidades", "actividades_deseadas", "actividades_no_deseadas", "cuerpo")
    @classmethod
    def validar_texto(cls, valor: str) -> str:
        return limpiar_texto(valor, multilinea=True)

    @field_validator("asunto")
    @classmethod
    def validar_asunto(cls, valor: str) -> str:
        return limpiar_texto(valor)


class ResumenContenidoTemporal(BaseModel):
    campana_id: str
    vence_en: datetime
    archivos: list[str]


class ResumenHistorial(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    correo: str
    enviado_en: datetime
    campana_id: str
