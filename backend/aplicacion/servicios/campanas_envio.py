"""Confirma campañas y registra cada intento antes de enviarlo por Gmail."""

import json
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..dominio.contactos import hace_seis_meses
from ..dominio.estados import LIMITES_CONTACTO, EstadoCampana, Plan
from ..esquemas import PATRON_CORREO
from ..integraciones.oauth_google import PERMISO_ENVIO_GMAIL
from ..modelos import Campana, ConexionGmail, CorreoExcluido, Destinatario, HistorialEnvio, Usuario
from .campanas import consultar_disponibilidad
from .conexiones_gmail import obtener_conexion_resumen
from .temporales import eliminar_contenido, recuperar_contenido


class EnvioNoPermitido(ValueError):
    """La campaña no está lista para una autorización de envío."""


def huella_preparacion(vista: dict) -> str:
    datos = [
        vista["asunto"],
        vista["cuerpo"],
        vista["archivos"],
        [empresa["id"] for empresa in vista["aptos"]],
    ]
    return sha256(json.dumps(datos, ensure_ascii=False).encode("utf-8")).hexdigest()


def _fecha_utc(fecha: datetime) -> datetime:
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def _seleccionados(sesion: Session, campana: Campana, usuario: Usuario) -> list[Destinatario]:
    if campana.estado != EstadoCampana.ESPERANDO_CONFIRMACION or not campana.seleccion_guardada:
        raise EnvioNoPermitido("Guarda tu selección antes de confirmar el envío.")
    if campana.modo_consulta != "sgva":
        raise EnvioNoPermitido("Los ejemplos no permiten envíos reales.")
    destinos = list(
        sesion.scalars(
            select(Destinatario)
            .where(
                Destinatario.campana_id == campana.id,
                Destinatario.seleccionado.is_(True),
            )
            .order_by(Destinatario.puntuacion.desc().nulls_last(), Destinatario.id)
        )
    )
    limite = min(campana.limite_contactos, LIMITES_CONTACTO[Plan(usuario.plan)])
    if not destinos or len(destinos) > limite:
        raise EnvioNoPermitido("La selección está vacía o excede el límite del plan.")
    if any(
        not destino.correo or not PATRON_CORREO.fullmatch(destino.correo) for destino in destinos
    ):
        raise EnvioNoPermitido("Una empresa seleccionada no tiene un correo válido.")
    if Plan(usuario.plan) == Plan.GRATIS:
        visibles = set(
            sesion.scalars(
                select(Destinatario.id)
                .where(Destinatario.campana_id == campana.id)
                .order_by(Destinatario.puntuacion.desc().nulls_last(), Destinatario.id)
                .limit(9)
            )
        )
        if any(destino.id not in visibles for destino in destinos):
            raise EnvioNoPermitido("La selección contiene una oferta que tu plan no muestra.")
    return destinos


def preparar_envio(sesion: Session, campana: Campana, usuario: Usuario, clave: str | None) -> dict:
    destinos = _seleccionados(sesion, campana, usuario)
    conexion = sesion.scalar(select(ConexionGmail).where(ConexionGmail.usuario_id == usuario.id))
    if conexion is None or PERMISO_ENVIO_GMAIL not in conexion.permisos.split():
        raise EnvioNoPermitido("Conecta Gmail de nuevo para autorizar el envío.")
    conexion_resumen = obtener_conexion_resumen(sesion)
    if conexion_resumen is None or PERMISO_ENVIO_GMAIL not in conexion_resumen.permisos.split():
        raise EnvioNoPermitido(
            "El correo de DEBUPA aún no está conectado para entregar tu resumen. "
            "Inténtalo más tarde."
        )
    contenido = recuperar_contenido(sesion, campana, clave)
    if contenido is None:
        raise EnvioNoPermitido(
            "El mensaje cifrado venció. Crea otra búsqueda para redactarlo de nuevo."
        )

    ahora = datetime.now(timezone.utc)
    limite_antiguo = hace_seis_meses(ahora)
    excluidos = set(
        sesion.scalars(
            select(CorreoExcluido.correo).where(CorreoExcluido.usuario_id == usuario.id)
        )
    )
    aptos, omitidos = [], []
    for destino in destinos:
        correo = destino.correo.lower()
        motivo = None
        if correo in excluidos:
            motivo = "Está en tu lista de exclusión."
        else:
            anterior = sesion.scalar(
                select(HistorialEnvio)
                .where(
                    HistorialEnvio.usuario_id == usuario.id,
                    HistorialEnvio.correo == correo,
                    HistorialEnvio.estado.in_(("enviado", "reservado", "en_proceso", "incierto")),
                )
                .order_by(HistorialEnvio.enviado_en.desc())
                .limit(1)
            )
            if anterior is not None:
                if anterior.estado != "enviado":
                    motivo = "Hay otro envío pendiente o sin confirmar; revisa Gmail Enviados."
                elif _fecha_utc(anterior.enviado_en) > limite_antiguo:
                    motivo = "Se contactó durante los últimos seis meses."
                elif not campana.permitir_recontacto:
                    motivo = "Se contactó antes y no autorizaste recontactarlo."
        ubicacion = " · ".join(parte for parte in (destino.departamento, destino.ciudad) if parte)
        empresa = {
            "id": destino.id,
            "nombre_empresa": destino.nombre_empresa,
            "correo": correo,
            "ubicacion": ubicacion or "Ubicación no informada",
            "telefono_original": destino.telefono_original,
            "motivo": motivo,
        }
        (omitidos if motivo else aptos).append(empresa)
    return {
        "remitente": conexion.correo_google,
        "asunto": contenido.mensaje.asunto,
        "cuerpo": contenido.mensaje.cuerpo,
        "archivos": [archivo.nombre for archivo in contenido.archivos],
        "aptos": aptos,
        "omitidos": omitidos,
    }


def autorizar_envio(
    sesion: Session,
    campana: Campana,
    usuario: Usuario,
    clave: str | None,
    destinatarios_confirmados: list[str],
    huella_confirmada: str,
) -> int:
    sesion.execute(select(Usuario.id).where(Usuario.id == usuario.id).with_for_update())
    activa = sesion.scalar(
        select(Campana.id)
        .where(
            Campana.usuario_id == usuario.id,
            Campana.id != campana.id,
            Campana.estado == EstadoCampana.ENVIANDO,
        )
        .limit(1)
    )
    if activa or consultar_disponibilidad(sesion, usuario) is not None:
        raise EnvioNoPermitido(
            "Ya hay un envío activo o tu plan debe esperar antes de otro envío."
        )
    vista = preparar_envio(sesion, campana, usuario, clave)
    if huella_preparacion(vista) != huella_confirmada:
        raise EnvioNoPermitido("Cambió el mensaje o la lista. Revísalos otra vez antes de enviar.")
    ids = [empresa["id"] for empresa in vista["aptos"]]
    if (
        not ids
        or len(ids) != len(destinatarios_confirmados)
        or set(ids) != set(destinatarios_confirmados)
    ):
        raise EnvioNoPermitido(
            "La lista cambió o no hay destinatarios aptos. Revísala antes de confirmar."
        )
    ahora = datetime.now(timezone.utc)
    sesion.add_all(
        HistorialEnvio(
            usuario_id=usuario.id,
            campana_id=campana.id,
            destinatario_id=empresa["id"],
            correo=empresa["correo"],
            estado="reservado",
            enviado_en=ahora,
        )
        for empresa in vista["aptos"]
    )
    campana.estado = EstadoCampana.ENVIANDO
    campana.etapa = "Preparando mensajes autorizados"
    campana.progreso = 5
    sesion.commit()
    return len(ids)


def interrumpir_envios(sesion: Session) -> None:
    """Tras reiniciar, nunca reintenta una solicitud que pudo llegar a Gmail."""
    campanas = list(
        sesion.scalars(select(Campana).where(Campana.estado == EstadoCampana.ENVIANDO))
    )
    for campana in campanas:
        sesion.execute(
            update(HistorialEnvio)
            .where(HistorialEnvio.campana_id == campana.id, HistorialEnvio.estado == "en_proceso")
            .values(estado="incierto")
        )
        sesion.execute(
            update(HistorialEnvio)
            .where(HistorialEnvio.campana_id == campana.id, HistorialEnvio.estado == "reservado")
            .values(estado="cancelado")
        )
        campana.estado = EstadoCampana.INTERRUMPIDA
        campana.etapa = "El servidor se reinició. Revisa Gmail Enviados antes de otra búsqueda."
        eliminar_contenido(sesion, campana)
    sesion.commit()


def cancelar_envio(sesion: Session, campana: Campana) -> None:
    """Detiene los pendientes; un mensaje en tránsito queda incierto hasta confirmarse."""
    if campana.estado != EstadoCampana.ENVIANDO:
        raise EnvioNoPermitido("Esta campaña ya no está enviando mensajes.")
    sesion.execute(
        update(HistorialEnvio)
        .where(HistorialEnvio.campana_id == campana.id, HistorialEnvio.estado == "reservado")
        .values(estado="cancelado")
    )
    sesion.execute(
        update(HistorialEnvio)
        .where(HistorialEnvio.campana_id == campana.id, HistorialEnvio.estado == "en_proceso")
        .values(estado="incierto")
    )
    campana.estado = EstadoCampana.CANCELADA
    campana.etapa = "Envío cancelado; los mensajes confirmados permanecen en Gmail"
    eliminar_contenido(sesion, campana)
    sesion.commit()
