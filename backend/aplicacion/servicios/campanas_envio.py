"""Confirma campañas y registra cada intento antes de enviarlo por Gmail."""

import asyncio
import calendar
from hashlib import sha256
import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from ..configuracion import Configuracion
from ..dominio.archivos import TIPOS_PERMITIDOS
from ..dominio.estados import EstadoCampana, LIMITES_CONTACTO, Plan
from ..esquemas import PATRON_CORREO
from ..modelos import Campana, ConexionGmail, CorreoExcluido, Destinatario, HistorialEnvio, Usuario
from .envio_gmail import AdjuntoGmail, EnvioGmailNoConfirmado, GmailNoDisponible, PermisoGmailInvalido, enviar_gmail
from .campanas import consultar_disponibilidad
from .resumen_correo import CORREO_DEBUPA, crear_resumen
from .temporales import eliminar_contenido, recuperar_contenido


class EnvioNoPermitido(ValueError):
    """La campaña no está lista para una autorización de envío."""


def _conexion_resumen(sesion: Session) -> ConexionGmail | None:
    """Solo acepta el permiso Gmail otorgado por la cuenta verificada de DEBUPA."""
    return sesion.scalar(select(ConexionGmail).join(Usuario, Usuario.id == ConexionGmail.usuario_id).where(
        Usuario.correo_google == CORREO_DEBUPA,
        ConexionGmail.correo_google == CORREO_DEBUPA,
    ))


def huella_preparacion(vista: dict) -> str:
    datos = [vista["asunto"], vista["cuerpo"], vista["archivos"],
             [empresa["id"] for empresa in vista["aptos"]]]
    return sha256(json.dumps(datos, ensure_ascii=False).encode("utf-8")).hexdigest()


def _fecha_utc(fecha: datetime) -> datetime:
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def _restar_seis_meses(fecha: datetime) -> datetime:
    mes = fecha.month - 6
    anio = fecha.year
    if mes <= 0:
        mes += 12
        anio -= 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)


def _seleccionados(sesion: Session, campana: Campana, usuario: Usuario) -> list[Destinatario]:
    if campana.estado != EstadoCampana.ESPERANDO_CONFIRMACION or not campana.seleccion_guardada:
        raise EnvioNoPermitido("Guarda tu selección antes de confirmar el envío.")
    if campana.modo_consulta != "sgva":
        raise EnvioNoPermitido("Los ejemplos no permiten envíos reales.")
    destinos = list(sesion.scalars(select(Destinatario).where(
        Destinatario.campana_id == campana.id, Destinatario.seleccionado.is_(True),
    ).order_by(Destinatario.puntuacion.desc().nulls_last(), Destinatario.id)))
    limite = min(campana.limite_contactos, LIMITES_CONTACTO[Plan(usuario.plan)])
    if not destinos or len(destinos) > limite:
        raise EnvioNoPermitido("La selección está vacía o excede el límite del plan.")
    if any(not destino.correo or not PATRON_CORREO.fullmatch(destino.correo) for destino in destinos):
        raise EnvioNoPermitido("Una empresa seleccionada no tiene un correo válido.")
    if Plan(usuario.plan) == Plan.GRATIS:
        visibles = set(sesion.scalars(select(Destinatario.id).where(Destinatario.campana_id == campana.id)
                                     .order_by(Destinatario.puntuacion.desc().nulls_last(), Destinatario.id).limit(9)))
        if any(destino.id not in visibles for destino in destinos):
            raise EnvioNoPermitido("La selección contiene una oferta que tu plan no muestra.")
    return destinos


def preparar_envio(sesion: Session, campana: Campana, usuario: Usuario, clave: str | None) -> dict:
    destinos = _seleccionados(sesion, campana, usuario)
    conexion = sesion.scalar(select(ConexionGmail).where(ConexionGmail.usuario_id == usuario.id))
    if conexion is None or "https://www.googleapis.com/auth/gmail.send" not in conexion.permisos.split():
        raise EnvioNoPermitido("Conecta Gmail de nuevo para autorizar el envío.")
    conexion_resumen = _conexion_resumen(sesion)
    if conexion_resumen is None or "https://www.googleapis.com/auth/gmail.send" not in conexion_resumen.permisos.split():
        raise EnvioNoPermitido("El correo de DEBUPA aún no está conectado para entregar tu resumen. Inténtalo más tarde.")
    contenido = recuperar_contenido(sesion, campana, clave)
    if contenido is None:
        raise EnvioNoPermitido("El mensaje cifrado venció. Crea otra búsqueda para redactarlo de nuevo.")

    ahora = datetime.now(timezone.utc)
    limite_antiguo = _restar_seis_meses(ahora)
    excluidos = set(sesion.scalars(select(CorreoExcluido.correo).where(CorreoExcluido.usuario_id == usuario.id)))
    aptos, omitidos = [], []
    for destino in destinos:
        correo = destino.correo.lower()
        motivo = None
        if correo in excluidos:
            motivo = "Está en tu lista de exclusión."
        else:
            anterior = sesion.scalar(select(HistorialEnvio).where(
                HistorialEnvio.usuario_id == usuario.id,
                HistorialEnvio.correo == correo,
                HistorialEnvio.estado.in_(("enviado", "reservado", "en_proceso", "incierto")),
            ).order_by(HistorialEnvio.enviado_en.desc()).limit(1))
            if anterior is not None:
                if anterior.estado != "enviado":
                    motivo = "Hay otro envío pendiente o sin confirmar; revisa Gmail Enviados."
                elif _fecha_utc(anterior.enviado_en) > limite_antiguo:
                    motivo = "Se contactó durante los últimos seis meses."
                elif not campana.permitir_recontacto:
                    motivo = "Se contactó antes y no autorizaste recontactarlo."
        ubicacion = " · ".join(parte for parte in (destino.departamento, destino.ciudad) if parte)
        empresa = {"id": destino.id, "nombre_empresa": destino.nombre_empresa, "correo": correo,
                   "ubicacion": ubicacion or "Ubicación no informada",
                   "telefono_original": destino.telefono_original, "motivo": motivo}
        (omitidos if motivo else aptos).append(empresa)
    return {"remitente": conexion.correo_google, "asunto": contenido.mensaje.asunto,
            "cuerpo": contenido.mensaje.cuerpo, "archivos": [archivo.nombre for archivo in contenido.archivos],
            "aptos": aptos, "omitidos": omitidos}


def autorizar_envio(sesion: Session, campana: Campana, usuario: Usuario, clave: str | None,
                   destinatarios_confirmados: list[str], huella_confirmada: str) -> int:
    sesion.execute(select(Usuario.id).where(Usuario.id == usuario.id).with_for_update())
    activa = sesion.scalar(select(Campana.id).where(
        Campana.usuario_id == usuario.id, Campana.id != campana.id,
        Campana.estado == EstadoCampana.ENVIANDO,
    ).limit(1))
    if activa or consultar_disponibilidad(sesion, usuario) is not None:
        raise EnvioNoPermitido("Ya hay un envío activo o tu plan debe esperar antes de otro envío.")
    vista = preparar_envio(sesion, campana, usuario, clave)
    if huella_preparacion(vista) != huella_confirmada:
        raise EnvioNoPermitido("Cambió el mensaje o la lista. Revísalos otra vez antes de enviar.")
    ids = [empresa["id"] for empresa in vista["aptos"]]
    if not ids or len(ids) != len(destinatarios_confirmados) or set(ids) != set(destinatarios_confirmados):
        raise EnvioNoPermitido("La lista cambió o no hay destinatarios aptos. Revísala antes de confirmar.")
    ahora = datetime.now(timezone.utc)
    sesion.add_all(HistorialEnvio(usuario_id=usuario.id, campana_id=campana.id,
                                 destinatario_id=empresa["id"], correo=empresa["correo"],
                                 estado="reservado", enviado_en=ahora) for empresa in vista["aptos"])
    campana.estado = EstadoCampana.ENVIANDO
    campana.etapa = "Preparando mensajes autorizados"
    campana.progreso = 5
    sesion.commit()
    return len(ids)


def interrumpir_envios(sesion: Session) -> None:
    """Tras reiniciar, nunca reintenta una solicitud que pudo llegar a Gmail."""
    campanas = list(sesion.scalars(select(Campana).where(Campana.estado == EstadoCampana.ENVIANDO)))
    for campana in campanas:
        sesion.execute(update(HistorialEnvio).where(HistorialEnvio.campana_id == campana.id,
                     HistorialEnvio.estado == "en_proceso").values(estado="incierto"))
        sesion.execute(update(HistorialEnvio).where(HistorialEnvio.campana_id == campana.id,
                     HistorialEnvio.estado == "reservado").values(estado="cancelado"))
        campana.estado = EstadoCampana.INTERRUMPIDA
        campana.etapa = "El servidor se reinició. Revisa Gmail Enviados antes de otra búsqueda."
        eliminar_contenido(sesion, campana)
    sesion.commit()


def _adjuntos(archivos) -> tuple[AdjuntoGmail, ...]:
    resultado = []
    for archivo in archivos:
        extension = PurePosixPath(archivo.nombre).suffix.lower()
        if archivo.tipo_declarado not in TIPOS_PERMITIDOS.get(extension, set()):
            raise ValueError("El formato de un adjunto ya no es válido.")
        tipo, subtipo = archivo.tipo_declarado.split("/", 1)
        resultado.append(AdjuntoGmail(archivo.nombre, archivo.contenido, tipo, subtipo))
    return tuple(resultado)


async def procesar_envio(fabrica: sessionmaker, configuracion: Configuracion, campana_id: str) -> None:
    with fabrica() as sesion:
        campana = sesion.get(Campana, campana_id)
        if campana is None or campana.estado != EstadoCampana.ENVIANDO:
            return
        contenido = recuperar_contenido(sesion, campana, configuracion.clave_cifrado)
        conexion = sesion.scalar(select(ConexionGmail).where(ConexionGmail.usuario_id == campana.usuario_id))
        if contenido is None or conexion is None:
            _finalizar(sesion, campana, EstadoCampana.ERROR, "El mensaje o permiso de Gmail ya no está disponible.")
            return
        token, remitente = conexion.token_renovacion_cifrado, conexion.correo_google
        asunto, cuerpo, adjuntos = contenido.mensaje.asunto, contenido.mensaje.cuerpo, _adjuntos(contenido.archivos)
        envios = list(sesion.scalars(select(HistorialEnvio).where(
            HistorialEnvio.campana_id == campana_id, HistorialEnvio.estado == "reservado",
        ).order_by(HistorialEnvio.id)))
        ids = [envio.id for envio in envios]
    for posicion, envio_id in enumerate(ids, start=1):
        with fabrica() as sesion:
            envio = sesion.get(HistorialEnvio, envio_id)
            campana = sesion.get(Campana, campana_id)
            if envio is None or envio.estado != "reservado" or campana.estado != EstadoCampana.ENVIANDO:
                return
            envio.estado = "en_proceso"
            campana.etapa = f"Enviando mensaje {posicion} de {len(ids)}"
            campana.progreso = max(campana.progreso, min(95, int(10 + 85 * (posicion - 1) / len(ids))))
            sesion.commit()
            correo = envio.correo
        try:
            mensaje_id = await enviar_gmail(configuracion, token, remitente, correo, asunto, cuerpo, adjuntos)
        except (EnvioGmailNoConfirmado, PermisoGmailInvalido, GmailNoDisponible) as error:
            with fabrica() as sesion:
                envio = sesion.get(HistorialEnvio, envio_id)
                campana = sesion.get(Campana, campana_id)
                incierto = isinstance(error, (EnvioGmailNoConfirmado, PermisoGmailInvalido))
                envio.estado = "incierto" if incierto else "fallido"
                mensaje = "Gmail no confirmó un envío. Revisa Enviados antes de volver a contactar." if incierto else str(error)
                _finalizar(sesion, campana, EstadoCampana.INTERRUMPIDA if incierto else EstadoCampana.ERROR, mensaje)
            return
        except Exception:
            with fabrica() as sesion:
                sesion.get(HistorialEnvio, envio_id).estado = "incierto"
                _finalizar(sesion, sesion.get(Campana, campana_id), EstadoCampana.INTERRUMPIDA,
                           "No se confirmó un envío. Revisa Gmail Enviados antes de volver a contactar.")
            return
        with fabrica() as sesion:
            envio = sesion.get(HistorialEnvio, envio_id)
            campana = sesion.get(Campana, campana_id)
            envio.estado = "enviado"
            envio.mensaje_gmail_id = mensaje_id
            envio.enviado_en = datetime.now(timezone.utc)
            campana.progreso = min(99, int(10 + 89 * posicion / len(ids)))
            sesion.commit()
        if posicion < len(ids):
            await asyncio.sleep(1)
    with fabrica() as sesion:
        consulta = select(Destinatario).join(HistorialEnvio, HistorialEnvio.destinatario_id == Destinatario.id).where(
            HistorialEnvio.campana_id == campana_id, HistorialEnvio.estado == "enviado",
        ).order_by(Destinatario.nombre_empresa)
        contactos: list[tuple[str, str]] = []
        for destino in sesion.scalars(consulta):
            telefono = destino.telefono_original or ""
            if 7 <= len(re.sub(r"\D", "", telefono)) <= 13 and re.fullmatch(r"[\d+()\s.\-]+", telefono):
                contactos.append((destino.nombre_empresa, telefono))
        campana = sesion.get(Campana, campana_id)
        campana.etapa = "Preparando el resumen de DEBUPA"
        campana.progreso = 99
        eliminar_contenido(sesion, campana)
        conexion_resumen = _conexion_resumen(sesion)
        token_resumen = conexion_resumen.token_renovacion_cifrado if conexion_resumen else None
        destinatario_resumen = remitente
    cuerpo_resumen, cuerpo_html = crear_resumen(contactos)
    try:
        if token_resumen is None:
            raise GmailNoDisponible("El correo de DEBUPA ya no está conectado.")
        await enviar_gmail(configuracion, token_resumen, CORREO_DEBUPA, destinatario_resumen,
                           "DEBUPA · Contactos de tu campaña", cuerpo_resumen, (), cuerpo_html)
        etapa = "Mensajes enviados y resumen de DEBUPA entregado a tu Gmail"
    except (EnvioGmailNoConfirmado, PermisoGmailInvalido, GmailNoDisponible):
        etapa = "Mensajes a empresas confirmados. El resumen de DEBUPA no pudo confirmarse."
    with fabrica() as sesion:
        campana = sesion.get(Campana, campana_id)
        if campana is not None and campana.estado == EstadoCampana.ENVIANDO:
            _finalizar(sesion, campana, EstadoCampana.COMPLETADA, etapa)


def _finalizar(sesion: Session, campana: Campana, estado: EstadoCampana, etapa: str) -> None:
    sesion.execute(update(HistorialEnvio).where(HistorialEnvio.campana_id == campana.id,
                 HistorialEnvio.estado == "reservado").values(estado="cancelado"))
    campana.estado = estado
    campana.etapa = etapa
    if estado == EstadoCampana.COMPLETADA:
        campana.progreso = 100
    eliminar_contenido(sesion, campana)
    sesion.commit()


async def vigilar_envios(fabrica: sessionmaker, configuracion: Configuracion, cola: asyncio.Queue) -> None:
    while True:
        campana_id = await cola.get()
        try:
            await procesar_envio(fabrica, configuracion, campana_id)
        except Exception:
            with fabrica() as sesion:
                interrumpir_envios(sesion)
        finally:
            cola.task_done()
