"""Conserva el contenido cifrado por campaña durante un máximo de 24 horas."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.fernet import InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..dominio.archivos import ArchivoAdjunto, validar_adjuntos, validar_contenido
from ..dominio.estados import EstadoCampana, Plan
from ..esquemas import ResumenContenidoTemporal, SolicitudContenidoTemporal
from ..integraciones.cifrado import ClaveCifradoInvalida, obtener_cifrador
from ..modelos import AdjuntoTemporal, Campana, ContenidoTemporal, Usuario

DURACION_TEMPORAL = timedelta(hours=24)
SEGUNDOS_TEMPORAL = int(DURACION_TEMPORAL.total_seconds())


@dataclass(frozen=True)
class ArchivoTemporal:
    nombre: str
    tipo_declarado: str
    contenido: bytes


@dataclass(frozen=True)
class DatosRecuperados:
    mensaje: SolicitudContenidoTemporal
    archivos: tuple[ArchivoTemporal, ...]


def _zona(fecha: datetime) -> datetime:
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def _abrir(token: bytes, clave: str | None) -> bytes:
    try:
        return obtener_cifrador(clave).decrypt(token, ttl=SEGUNDOS_TEMPORAL)
    except InvalidToken as error:
        raise ClaveCifradoInvalida(
            "El contenido temporal expiró o no pudo descifrarse."
        ) from error


def limpiar_expirados(sesion: Session, ahora: datetime | None = None) -> int:
    """Borra físicamente adjuntos y mensajes vencidos."""
    fecha = ahora or datetime.now(timezone.utc)
    vencidos = select(ContenidoTemporal.campana_id).where(ContenidoTemporal.vence_en <= fecha)
    sesion.execute(delete(AdjuntoTemporal).where(AdjuntoTemporal.campana_id.in_(vencidos)))
    resultado = sesion.execute(
        delete(ContenidoTemporal).where(ContenidoTemporal.vence_en <= fecha)
    )
    sesion.commit()
    return resultado.rowcount or 0


def guardar_contenido(
    sesion: Session,
    campana: Campana,
    mensaje: SolicitudContenidoTemporal,
    archivos: tuple[ArchivoTemporal, ...],
    clave: str | None,
) -> ResumenContenidoTemporal:
    if campana.estado not in {EstadoCampana.BORRADOR, EstadoCampana.ESPERANDO_CONFIRMACION}:
        raise ValueError("Solo se puede cambiar el contenido antes de confirmar el envío.")
    ahora = datetime.now(timezone.utc)
    temporal = obtener_temporal(sesion, campana)
    validar_adjuntos(
        [
            ArchivoAdjunto(archivo.nombre, archivo.tipo_declarado, len(archivo.contenido))
            for archivo in archivos
        ],
        Plan(campana.plan_aplicado),
    )
    for archivo in archivos:
        validar_contenido(archivo.nombre, archivo.contenido)

    cifrador = obtener_cifrador(clave)
    contenido_cifrado = cifrador.encrypt(mensaje.model_dump_json().encode("utf-8"))
    adjuntos_cifrados = [
        (
            cifrador.encrypt(
                json.dumps({"nombre": archivo.nombre, "tipo": archivo.tipo_declarado}).encode(
                    "utf-8"
                )
            ),
            cifrador.encrypt(archivo.contenido),
            len(archivo.contenido),
        )
        for archivo in archivos
    ]
    if temporal is None:
        temporal = ContenidoTemporal(
            campana_id=campana.id,
            contenido_cifrado=contenido_cifrado,
            vence_en=ahora + DURACION_TEMPORAL,
            actualizado_en=ahora,
        )
        sesion.add(temporal)
        sesion.flush()
    else:
        sesion.execute(delete(AdjuntoTemporal).where(AdjuntoTemporal.campana_id == campana.id))
        temporal.contenido_cifrado = contenido_cifrado
        temporal.vence_en = ahora + DURACION_TEMPORAL
        temporal.actualizado_en = ahora
    sesion.add_all(
        AdjuntoTemporal(
            campana_id=campana.id,
            metadatos_cifrados=metadatos,
            contenido_cifrado=contenido,
            tamano_bytes=tamano,
        )
        for metadatos, contenido, tamano in adjuntos_cifrados
    )
    sesion.commit()
    return ResumenContenidoTemporal(
        campana_id=campana.id,
        vence_en=_zona(temporal.vence_en),
        archivos=[archivo.nombre for archivo in archivos],
    )


def obtener_temporal(sesion: Session, campana: Campana) -> ContenidoTemporal | None:
    temporal = sesion.get(ContenidoTemporal, campana.id)
    if temporal is not None and _zona(temporal.vence_en) <= datetime.now(timezone.utc):
        eliminar_contenido(sesion, campana)
        return None
    return temporal


def resumir_contenido(
    sesion: Session, campana: Campana, clave: str | None
) -> ResumenContenidoTemporal | None:
    temporal = obtener_temporal(sesion, campana)
    if temporal is None:
        return None
    adjuntos = sesion.scalars(
        select(AdjuntoTemporal).where(AdjuntoTemporal.campana_id == campana.id)
    )
    nombres = [
        json.loads(_abrir(adjunto.metadatos_cifrados, clave))["nombre"] for adjunto in adjuntos
    ]
    return ResumenContenidoTemporal(
        campana_id=campana.id, vence_en=_zona(temporal.vence_en), archivos=nombres
    )


def listar_contenidos(
    sesion: Session, usuario: Usuario, clave: str | None
) -> list[ResumenContenidoTemporal]:
    consulta = (
        select(Campana)
        .join(ContenidoTemporal, ContenidoTemporal.campana_id == Campana.id)
        .where(
            Campana.usuario_id == usuario.id,
            ContenidoTemporal.vence_en > datetime.now(timezone.utc),
        )
        .order_by(ContenidoTemporal.actualizado_en.desc())
        .limit(100)
    )
    resultados = []
    for campana in list(sesion.scalars(consulta)):
        resumen = resumir_contenido(sesion, campana, clave)
        if resumen is not None:
            resultados.append(resumen)
    return resultados


def recuperar_contenido(
    sesion: Session, campana: Campana, clave: str | None
) -> DatosRecuperados | None:
    """Uso interno del futuro trabajador: nunca entrega archivos al navegador."""
    temporal = obtener_temporal(sesion, campana)
    if temporal is None:
        return None
    mensaje = SolicitudContenidoTemporal.model_validate_json(
        _abrir(temporal.contenido_cifrado, clave)
    )
    adjuntos = sesion.scalars(
        select(AdjuntoTemporal).where(AdjuntoTemporal.campana_id == campana.id)
    )
    archivos = []
    for adjunto in adjuntos:
        metadatos = json.loads(_abrir(adjunto.metadatos_cifrados, clave))
        archivos.append(
            ArchivoTemporal(
                metadatos["nombre"], metadatos["tipo"], _abrir(adjunto.contenido_cifrado, clave)
            )
        )
    return DatosRecuperados(mensaje, tuple(archivos))


def eliminar_contenido(sesion: Session, campana: Campana) -> bool:
    temporal = sesion.get(ContenidoTemporal, campana.id)
    if temporal is None:
        return False
    sesion.execute(delete(AdjuntoTemporal).where(AdjuntoTemporal.campana_id == campana.id))
    sesion.delete(temporal)
    sesion.commit()
    return True
