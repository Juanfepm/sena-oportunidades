"""Trabajador de Gmail: registra resultados y evita reintentos inciertos."""

import asyncio
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from ..configuracion import Configuracion
from ..dominio.archivos import TIPOS_PERMITIDOS
from ..dominio.estados import EstadoCampana
from ..integraciones.gmail import (
    AdjuntoGmail,
    EnvioGmailNoConfirmado,
    GmailNoDisponible,
    PermisoGmailInvalido,
    enviar_gmail,
)
from ..modelos import Campana, ConexionGmail, Destinatario, HistorialEnvio
from .campanas_envio import interrumpir_envios
from .conexiones_gmail import obtener_conexion_resumen
from .correo_empresa import preparar_correo_empresa
from .resumen_correo import CORREO_DEBUPA, crear_resumen
from .temporales import eliminar_contenido, recuperar_contenido


def _adjuntos(archivos) -> tuple[AdjuntoGmail, ...]:
    resultado = []
    for archivo in archivos:
        extension = PurePosixPath(archivo.nombre).suffix.lower()
        if archivo.tipo_declarado not in TIPOS_PERMITIDOS.get(extension, set()):
            raise ValueError("El formato de un adjunto ya no es válido.")
        tipo, subtipo = archivo.tipo_declarado.split("/", 1)
        resultado.append(AdjuntoGmail(archivo.nombre, archivo.contenido, tipo, subtipo))
    return tuple(resultado)


async def procesar_envio(
    fabrica: sessionmaker, configuracion: Configuracion, campana_id: str
) -> None:
    with fabrica() as sesion:
        campana = sesion.get(Campana, campana_id)
        if campana is None or campana.estado != EstadoCampana.ENVIANDO:
            return
        contenido = recuperar_contenido(sesion, campana, configuracion.clave_cifrado)
        conexion = sesion.scalar(
            select(ConexionGmail).where(ConexionGmail.usuario_id == campana.usuario_id)
        )
        if contenido is None or conexion is None:
            _finalizar(
                sesion,
                campana,
                EstadoCampana.ERROR,
                "El mensaje o permiso de Gmail ya no está disponible.",
            )
            return
        token, remitente = conexion.token_renovacion_cifrado, conexion.correo_google
        asunto, cuerpo, adjuntos = (
            contenido.mensaje.asunto,
            contenido.mensaje.cuerpo,
            _adjuntos(contenido.archivos),
        )
        envios = list(
            sesion.scalars(
                select(HistorialEnvio)
                .where(
                    HistorialEnvio.campana_id == campana_id,
                    HistorialEnvio.estado == "reservado",
                )
                .order_by(HistorialEnvio.id)
            )
        )
        ids = [envio.id for envio in envios]
    for posicion, envio_id in enumerate(ids, start=1):
        with fabrica() as sesion:
            envio = sesion.get(HistorialEnvio, envio_id)
            campana = sesion.get(Campana, campana_id)
            if (
                envio is None
                or campana is None
                or envio.estado != "reservado"
                or campana.estado != EstadoCampana.ENVIANDO
            ):
                return
            envio.estado = "en_proceso"
            campana.etapa = f"Enviando mensaje {posicion} de {len(ids)}"
            campana.progreso = max(
                campana.progreso, min(95, int(10 + 85 * (posicion - 1) / len(ids)))
            )
            sesion.commit()
            correo = envio.correo
        try:
            cuerpo_con_firma, cuerpo_html = preparar_correo_empresa(cuerpo)
            mensaje_id = await enviar_gmail(
                configuracion,
                token,
                remitente,
                correo,
                asunto,
                cuerpo_con_firma,
                adjuntos,
                cuerpo_html,
            )
        except (EnvioGmailNoConfirmado, PermisoGmailInvalido, GmailNoDisponible) as error:
            with fabrica() as sesion:
                envio = sesion.get(HistorialEnvio, envio_id)
                campana = sesion.get(Campana, campana_id)
                incierto = isinstance(error, (EnvioGmailNoConfirmado, PermisoGmailInvalido))
                envio.estado = "incierto" if incierto else "fallido"
                mensaje = (
                    "Gmail no confirmó un envío. Revisa Enviados antes de volver a contactar."
                    if incierto
                    else str(error)
                )
                if campana.estado == EstadoCampana.CANCELADA:
                    sesion.commit()
                else:
                    _finalizar(
                        sesion,
                        campana,
                        EstadoCampana.INTERRUMPIDA if incierto else EstadoCampana.ERROR,
                        mensaje,
                    )
            return
        except Exception:
            with fabrica() as sesion:
                sesion.get(HistorialEnvio, envio_id).estado = "incierto"
                campana = sesion.get(Campana, campana_id)
                if campana.estado == EstadoCampana.CANCELADA:
                    sesion.commit()
                else:
                    _finalizar(
                        sesion,
                        campana,
                        EstadoCampana.INTERRUMPIDA,
                        "No se confirmó un envío. Revisa Gmail Enviados antes de "
                        "volver a contactar.",
                    )
            return
        with fabrica() as sesion:
            envio = sesion.get(HistorialEnvio, envio_id)
            campana = sesion.get(Campana, campana_id)
            envio.estado = "enviado"
            envio.mensaje_gmail_id = mensaje_id
            envio.enviado_en = datetime.now(timezone.utc)
            if campana.estado == EstadoCampana.ENVIANDO:
                campana.progreso = min(99, int(10 + 89 * posicion / len(ids)))
            sesion.commit()
            if campana.estado == EstadoCampana.CANCELADA:
                return
        if posicion < len(ids):
            await asyncio.sleep(1)
    with fabrica() as sesion:
        campana = sesion.get(Campana, campana_id)
        if campana is None or campana.estado != EstadoCampana.ENVIANDO:
            return
        consulta = (
            select(Destinatario)
            .join(HistorialEnvio, HistorialEnvio.destinatario_id == Destinatario.id)
            .where(
                HistorialEnvio.campana_id == campana_id,
                HistorialEnvio.estado == "enviado",
            )
            .order_by(Destinatario.nombre_empresa)
        )
        contactos: list[tuple[str, str]] = []
        for destino in sesion.scalars(consulta):
            telefono = destino.telefono_original or ""
            if 7 <= len(re.sub(r"\D", "", telefono)) <= 13 and re.fullmatch(
                r"[\d+()\s.\-]+", telefono
            ):
                contactos.append((destino.nombre_empresa, telefono))
        campana.etapa = "Preparando el resumen de DEBUPA"
        campana.progreso = 99
        eliminar_contenido(sesion, campana)
        conexion_resumen = obtener_conexion_resumen(sesion)
        token_resumen = conexion_resumen.token_renovacion_cifrado if conexion_resumen else None
        destinatario_resumen = remitente
    cuerpo_resumen, cuerpo_html = crear_resumen(contactos)
    try:
        if token_resumen is None:
            raise GmailNoDisponible("El correo de DEBUPA ya no está conectado.")
        await enviar_gmail(
            configuracion,
            token_resumen,
            CORREO_DEBUPA,
            destinatario_resumen,
            "DEBUPA · Contactos de tu campaña",
            cuerpo_resumen,
            (),
            cuerpo_html,
        )
        etapa = "Mensajes enviados y resumen de DEBUPA entregado a tu Gmail"
    except (EnvioGmailNoConfirmado, PermisoGmailInvalido, GmailNoDisponible):
        etapa = "Mensajes a empresas confirmados. El resumen de DEBUPA no pudo confirmarse."
    with fabrica() as sesion:
        campana = sesion.get(Campana, campana_id)
        if campana is not None and campana.estado == EstadoCampana.ENVIANDO:
            _finalizar(sesion, campana, EstadoCampana.COMPLETADA, etapa)


def _finalizar(sesion: Session, campana: Campana, estado: EstadoCampana, etapa: str) -> None:
    sesion.execute(
        update(HistorialEnvio)
        .where(HistorialEnvio.campana_id == campana.id, HistorialEnvio.estado == "reservado")
        .values(estado="cancelado")
    )
    campana.estado = estado
    campana.etapa = etapa
    if estado == EstadoCampana.COMPLETADA:
        campana.progreso = 100
    eliminar_contenido(sesion, campana)
    sesion.commit()


async def vigilar_envios(
    fabrica: sessionmaker, configuracion: Configuracion, cola: asyncio.Queue
) -> None:
    while True:
        campana_id = await cola.get()
        try:
            await procesar_envio(fabrica, configuracion, campana_id)
        except Exception:
            with fabrica() as sesion:
                interrumpir_envios(sesion)
        finally:
            cola.task_done()
