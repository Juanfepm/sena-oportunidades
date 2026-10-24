"""Configuración explícita: ningún secreto tiene un valor utilizable por defecto."""

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class Configuracion:
    entorno: str = "desarrollo"
    base_datos: str = "sqlite:///./backend/datos/desarrollo.sqlite3"
    clave_pruebas: str | None = None
    usuario_pruebas: str = "aprendiz-local"

    def __post_init__(self) -> None:
        if self.clave_pruebas and len(self.clave_pruebas) < 32:
            raise ValueError("La clave local de desarrollo debe tener al menos 32 caracteres.")

    @classmethod
    def desde_entorno(cls) -> "Configuracion":
        configuracion = cls(
            entorno=getenv("DEBUPA_ENTORNO", "desarrollo"),
            base_datos=getenv("DEBUPA_BASE_DATOS", cls.base_datos),
            clave_pruebas=getenv("DEBUPA_CLAVE_PRUEBAS"),
            usuario_pruebas=getenv("DEBUPA_USUARIO_PRUEBAS", "aprendiz-local"),
        )
        if configuracion.entorno not in {"desarrollo", "pruebas", "produccion"}:
            raise ValueError("DEBUPA_ENTORNO debe ser desarrollo, pruebas o produccion.")
        if configuracion.entorno == "produccion" and not configuracion.base_datos.startswith("postgresql+psycopg://"):
            raise ValueError("Producción requiere PostgreSQL con el controlador psycopg.")
        return configuracion
