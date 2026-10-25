"""Configuración explícita: ningún secreto tiene un valor utilizable por defecto."""

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class Configuracion:
    entorno: str = "desarrollo"
    base_datos: str = "sqlite:///./backend/datos/desarrollo.sqlite3"
    clave_pruebas: str | None = None
    usuario_pruebas: str = "aprendiz-local"
    google_cliente_id: str | None = None
    google_cliente_secreto: str | None = None
    google_uri_redireccion: str = "http://127.0.0.1:8000/api/v1/autenticacion/google/callback"
    google_url_inicio: str = "/#inicio"
    secreto_sesion: str | None = None
    clave_cifrado: str | None = None

    def __post_init__(self) -> None:
        if self.clave_pruebas and len(self.clave_pruebas) < 32:
            raise ValueError("La clave local de desarrollo debe tener al menos 32 caracteres.")
        if self.secreto_sesion and len(self.secreto_sesion) < 32:
            raise ValueError("El secreto de sesión debe tener al menos 32 caracteres.")

    @classmethod
    def desde_entorno(cls) -> "Configuracion":
        configuracion = cls(
            entorno=getenv("DEBUPA_ENTORNO", "desarrollo"),
            base_datos=getenv("DEBUPA_BASE_DATOS", cls.base_datos),
            clave_pruebas=getenv("DEBUPA_CLAVE_PRUEBAS"),
            usuario_pruebas=getenv("DEBUPA_USUARIO_PRUEBAS", "aprendiz-local"),
            google_cliente_id=getenv("GOOGLE_CLIENTE_ID"),
            google_cliente_secreto=getenv("GOOGLE_CLIENTE_SECRETO"),
            google_uri_redireccion=getenv(
                "GOOGLE_URI_REDIRECCION",
                "http://127.0.0.1:8000/api/v1/autenticacion/google/callback",
            ),
            google_url_inicio=getenv("GOOGLE_URL_INICIO", "/#inicio"),
            secreto_sesion=getenv("DEBUPA_SECRETO_SESION"),
            clave_cifrado=getenv("DEBUPA_CLAVE_CIFRADO"),
        )
        if configuracion.entorno not in {"desarrollo", "pruebas", "produccion"}:
            raise ValueError("DEBUPA_ENTORNO debe ser desarrollo, pruebas o produccion.")
        if configuracion.entorno == "produccion" and not configuracion.base_datos.startswith("postgresql+psycopg://"):
            raise ValueError("Producción requiere PostgreSQL con el controlador psycopg.")
        return configuracion
