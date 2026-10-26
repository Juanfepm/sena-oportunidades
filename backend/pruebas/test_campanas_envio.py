"""Prueba el envío autorizado con Gmail sustituido: nunca contacta empresas reales."""

import asyncio
from datetime import datetime, timedelta, timezone
from time import monotonic, sleep

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base
from backend.aplicacion.configuracion import Configuracion
from backend.aplicacion.dominio.estados import EstadoCampana
from backend.aplicacion.esquemas import SolicitudContenidoTemporal
from backend.aplicacion.integraciones.gmail import EnvioGmailNoConfirmado
from backend.aplicacion.modelos import (
    Campana,
    ConexionGmail,
    Destinatario,
    HistorialEnvio,
    Usuario,
)
from backend.aplicacion.principal import crear_aplicacion
from backend.aplicacion.seguridad import obtener_usuario_actual, verificar_csrf
from backend.aplicacion.servicios import campanas_envio, trabajador_envio
from backend.aplicacion.servicios.temporales import (
    ArchivoTemporal,
    guardar_contenido,
    recuperar_contenido,
)


@pytest.fixture
def contexto():
    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    fabrica = sessionmaker(motor, expire_on_commit=False)
    clave = Fernet.generate_key().decode()
    configuracion = Configuracion(
        google_cliente_id="cliente-ficticio",
        google_cliente_secreto="secreto-ficticio",
        secreto_sesion="secreto-de-pruebas-para-campanas-2026",
        clave_cifrado=clave,
        sgva_activo=True,
    )
    with fabrica() as sesion:
        usuario = Usuario(
            identificador_externo="pruebas:aprendiz",
            correo_google="aprendiz@ejemplo.com",
            plan="premium",
        )
        sesion.add(usuario)
        sesion.flush()
        campana = Campana(
            usuario_id=usuario.id,
            plan_aplicado="premium",
            limite_contactos=70,
            modalidad="remoto",
            departamento="todos",
            ciudad="todas",
            antiguedad_dias=7,
            modo_consulta="sgva",
            permitir_recontacto=False,
        )
        sesion.add(campana)
        sesion.add(
            ConexionGmail(
                usuario_id=usuario.id,
                correo_google="aprendiz@ejemplo.com",
                token_renovacion_cifrado="token-cifrado-ficticio",
                permisos="https://www.googleapis.com/auth/gmail.send",
            )
        )
        usuario_debupa = Usuario(
            identificador_externo="pruebas:debupa", correo_google="debupawebapp@gmail.com"
        )
        sesion.add(usuario_debupa)
        sesion.flush()
        sesion.add(
            ConexionGmail(
                usuario_id=usuario_debupa.id,
                correo_google="debupawebapp@gmail.com",
                token_renovacion_cifrado="token-debupa-cifrado-ficticio",
                permisos="https://www.googleapis.com/auth/gmail.send",
            )
        )
        sesion.flush()
        guardar_contenido(
            sesion,
            campana,
            SolicitudContenidoTemporal(
                habilidades="Desarrollo aplicaciones y pruebo software.",
                actividades_deseadas="Programar y documentar.",
                asunto="Práctica en desarrollo",
                cuerpo=(
                    "Hola, me interesa conocer su vacante de práctica. "
                    "Adjunto mi hoja de vida. Muchas gracias."
                ),
            ),
            (),
            clave,
        )
        destinos = [
            Destinatario(
                campana_id=campana.id,
                nombre_empresa=f"Empresa {indice}",
                correo=f"empresa{indice}@ejemplo.com",
                motivo="Coincide con desarrollo.",
                departamento="BOGOTÁ D.C.",
                ciudad="BOGOTÁ D.C.",
                telefono_original="3001234567",
                puntuacion=90 - indice,
                estado="coincidencia_alta",
                seleccionado=True,
            )
            for indice in (1, 2)
        ]
        sesion.add_all(destinos)
        campana.estado = EstadoCampana.ESPERANDO_CONFIRMACION
        campana.seleccion_guardada = True
        sesion.commit()
        usuario_id, campana_id, ids = usuario.id, campana.id, [destino.id for destino in destinos]
    yield fabrica, configuracion, usuario_id, campana_id, ids
    motor.dispose()


def test_envia_una_vez_y_borra_contenido(contexto, monkeypatch):
    fabrica, configuracion, usuario_id, campana_id, ids = contexto
    mensajes = []

    async def enviar_ficticio(
        _config, token, remitente, destinatario, asunto, cuerpo, adjuntos, cuerpo_html=None
    ):
        mensajes.append((token, remitente, destinatario, asunto, cuerpo, adjuntos, cuerpo_html))
        return f"gmail-{len(mensajes)}"

    monkeypatch.setattr(trabajador_envio, "enviar_gmail", enviar_ficticio)
    with fabrica() as sesion:
        campana, usuario = sesion.get(Campana, campana_id), sesion.get(Usuario, usuario_id)
        vista = campanas_envio.preparar_envio(
            sesion, campana, usuario, configuracion.clave_cifrado
        )
        assert len(vista["aptos"]) == 2
        assert vista["remitente"] == "aprendiz@ejemplo.com"
        assert vista["aptos"][0]["ubicacion"] == "BOGOTÁ D.C. · BOGOTÁ D.C."
        huella = campanas_envio.huella_preparacion(vista)
        assert (
            campanas_envio.autorizar_envio(
                sesion, campana, usuario, configuracion.clave_cifrado, ids, huella
            )
            == 2
        )
        with pytest.raises(campanas_envio.EnvioNoPermitido):
            campanas_envio.autorizar_envio(
                sesion, campana, usuario, configuracion.clave_cifrado, ids, huella
            )
    asyncio.run(trabajador_envio.procesar_envio(fabrica, configuracion, campana_id))
    asyncio.run(trabajador_envio.procesar_envio(fabrica, configuracion, campana_id))
    assert len(mensajes) == 3
    assert {mensaje[2] for mensaje in mensajes[:2]} == {
        "empresa1@ejemplo.com",
        "empresa2@ejemplo.com",
    }
    assert all(mensaje[1] == "aprendiz@ejemplo.com" for mensaje in mensajes[:2])
    assert mensajes[2][0] == "token-debupa-cifrado-ficticio"
    assert mensajes[2][1:3] == ("debupawebapp@gmail.com", "aprendiz@ejemplo.com")
    assert "3001234567" in mensajes[2][6]
    with fabrica() as sesion:
        assert sesion.get(Campana, campana_id).estado == EstadoCampana.COMPLETADA
        assert all(
            envio.estado == "enviado" and envio.mensaje_gmail_id
            for envio in sesion.scalars(
                select(HistorialEnvio).where(HistorialEnvio.campana_id == campana_id)
            )
        )
        from backend.aplicacion.modelos import ContenidoTemporal

        assert sesion.get(ContenidoTemporal, campana_id) is None


def test_recontacto_y_error_incierto(contexto, monkeypatch):
    fabrica, configuracion, usuario_id, campana_id, ids = contexto
    with fabrica() as sesion:
        campana, usuario = sesion.get(Campana, campana_id), sesion.get(Usuario, usuario_id)
        sesion.add(
            HistorialEnvio(
                usuario_id=usuario_id,
                campana_id=campana_id,
                correo="empresa1@ejemplo.com",
                estado="enviado",
                enviado_en=datetime.now(timezone.utc) - timedelta(days=20),
            )
        )
        sesion.commit()
        vista = campanas_envio.preparar_envio(
            sesion, campana, usuario, configuracion.clave_cifrado
        )
        assert [empresa["id"] for empresa in vista["aptos"]] == [ids[1]]
        assert "seis meses" in vista["omitidos"][0]["motivo"]
        anterior = sesion.scalar(
            select(HistorialEnvio).where(HistorialEnvio.correo == "empresa1@ejemplo.com")
        )
        anterior.enviado_en = datetime.now(timezone.utc) - timedelta(days=220)
        sesion.commit()
        vista = campanas_envio.preparar_envio(
            sesion, campana, usuario, configuracion.clave_cifrado
        )
        assert "no autorizaste" in vista["omitidos"][0]["motivo"]
        campana.permitir_recontacto = True
        sesion.commit()
        vista = campanas_envio.preparar_envio(
            sesion, campana, usuario, configuracion.clave_cifrado
        )
        assert len(vista["aptos"]) == 2
        campana.permitir_recontacto = False
        sesion.commit()
        vista = campanas_envio.preparar_envio(
            sesion, campana, usuario, configuracion.clave_cifrado
        )
        campanas_envio.autorizar_envio(
            sesion,
            campana,
            usuario,
            configuracion.clave_cifrado,
            [ids[1]],
            campanas_envio.huella_preparacion(vista),
        )

    async def envio_incierto(*_args):
        raise EnvioGmailNoConfirmado("Gmail no confirmó.")

    monkeypatch.setattr(trabajador_envio, "enviar_gmail", envio_incierto)
    asyncio.run(trabajador_envio.procesar_envio(fabrica, configuracion, campana_id))
    with fabrica() as sesion:
        assert sesion.get(Campana, campana_id).estado == EstadoCampana.INTERRUMPIDA
        intento = sesion.scalar(
            select(HistorialEnvio).where(HistorialEnvio.destinatario_id == ids[1])
        )
        assert intento.estado == "incierto"
        campanas_envio.interrumpir_envios(sesion)
        assert sesion.get(HistorialEnvio, intento.id).estado == "incierto"


def test_api_exige_confirmacion_y_muestra_resultado(contexto, monkeypatch):
    fabrica, configuracion, usuario_id, campana_id, ids = contexto
    motor = fabrica.kw["bind"]
    app = crear_aplicacion(configuracion, motor)
    app.dependency_overrides[obtener_usuario_actual] = lambda: Usuario(
        id=usuario_id, plan="premium"
    )
    app.dependency_overrides[verificar_csrf] = lambda: None
    mensajes = []

    async def enviar_ficticio(
        _config, _token, _remitente, destino, _asunto, _cuerpo, _adjuntos, _html=None
    ):
        mensajes.append(destino)
        return f"mensaje-{len(mensajes)}"

    monkeypatch.setattr(trabajador_envio, "enviar_gmail", enviar_ficticio)
    with TestClient(app) as cliente:
        ruta = f"/api/v1/campanas/{campana_id}"
        edicion = cliente.get(f"{ruta}/contenido/edicion")
        assert edicion.status_code == 200
        assert edicion.headers["Cache-Control"] == "no-store"
        assert edicion.json()["asunto"] == "Práctica en desarrollo"
        assert (
            cliente.post(
                f"{ruta}/enviar", json={"destinatarios": ids, "confirmado": True}
            ).status_code
            == 422
        )
        preparacion = cliente.get(f"{ruta}/preparacion-envio")
        assert preparacion.status_code == 200
        assert preparacion.headers["Cache-Control"] == "no-store"
        assert len(preparacion.json()["aptos"]) == 2
        datos = {
            "destinatarios": ids,
            "confirmado": True,
            "confirmacion": preparacion.json()["confirmacion"],
        }
        assert (
            cliente.post(f"{ruta}/enviar", json={**datos, "confirmado": False}).status_code == 422
        )
        assert (
            cliente.post(f"{ruta}/enviar", json={**datos, "destinatarios": ids[:1]}).status_code
            == 409
        )
        assert cliente.post(f"{ruta}/enviar", json=datos).status_code == 202
        assert cliente.post(f"{ruta}/enviar", json=datos).status_code == 409
        plazo = monotonic() + 5
        while monotonic() < plazo:
            with fabrica() as sesion:
                terminado = sesion.get(Campana, campana_id).estado == "completada"
            if terminado:
                break
            sleep(0.05)
        # No hay consultas del navegador durante el trabajo; se abre otra sesión al terminar.
        cliente_nuevo = TestClient(app)
        assert cliente_nuevo.get(ruta).json()["estado"] == "completada"
        resultado = cliente_nuevo.get(f"{ruta}/resultado-envio")
        assert len(resultado.json()) == 2
        assert all(item["estado"] == "enviado" for item in resultado.json())
        assert len(mensajes) == 3
        assert cliente.get(f"{ruta}/contenido/edicion").status_code == 409


def test_sin_correo_de_debupa_no_autoriza_envios(contexto):
    fabrica, configuracion, usuario_id, campana_id, _ids = contexto
    with fabrica() as sesion:
        conexion = sesion.scalar(
            select(ConexionGmail).where(ConexionGmail.correo_google == "debupawebapp@gmail.com")
        )
        sesion.delete(conexion)
        sesion.commit()
        with pytest.raises(campanas_envio.EnvioNoPermitido, match="DEBUPA aún no está conectado"):
            campanas_envio.preparar_envio(
                sesion,
                sesion.get(Campana, campana_id),
                sesion.get(Usuario, usuario_id),
                configuracion.clave_cifrado,
            )
        assert (
            sesion.scalar(select(HistorialEnvio.id).where(HistorialEnvio.campana_id == campana_id))
            is None
        )


def test_editar_mensaje_sin_adjunto_elimina_el_anterior(contexto):
    fabrica, configuracion, _usuario_id, campana_id, _ids = contexto
    mensaje = SolicitudContenidoTemporal(
        habilidades="Desarrollo aplicaciones y pruebo software.",
        actividades_deseadas="Programar y documentar.",
        asunto="Mi práctica profesional",
        cuerpo=(
            "Hola, deseo conocer la práctica disponible. "
            "Adjunto mi hoja de vida. Gracias por su tiempo."
        ),
    )
    with fabrica() as sesion:
        campana = sesion.get(Campana, campana_id)
        guardar_contenido(
            sesion,
            campana,
            mensaje,
            (ArchivoTemporal("hoja.txt", "text/plain", b"Mi experiencia profesional"),),
            configuracion.clave_cifrado,
        )
        mensaje.asunto = "Asunto corregido"
        resumen = guardar_contenido(sesion, campana, mensaje, (), configuracion.clave_cifrado)
        assert resumen.archivos == []
        recuperado = recuperar_contenido(sesion, campana, configuracion.clave_cifrado)
        assert recuperado.mensaje.asunto == "Asunto corregido"
        assert recuperado.archivos == ()


def test_reinicio_no_repite_intentos_en_curso(contexto):
    fabrica, configuracion, usuario_id, campana_id, ids = contexto
    with fabrica() as sesion:
        campana, usuario = sesion.get(Campana, campana_id), sesion.get(Usuario, usuario_id)
        vista = campanas_envio.preparar_envio(
            sesion, campana, usuario, configuracion.clave_cifrado
        )
        campanas_envio.autorizar_envio(
            sesion,
            campana,
            usuario,
            configuracion.clave_cifrado,
            ids,
            campanas_envio.huella_preparacion(vista),
        )
        sesion.scalar(
            select(HistorialEnvio).where(HistorialEnvio.destinatario_id == ids[0])
        ).estado = "en_proceso"
        sesion.commit()
        campanas_envio.interrumpir_envios(sesion)
        assert campana.estado == EstadoCampana.INTERRUMPIDA
        estados = {
            envio.destinatario_id: envio.estado
            for envio in sesion.scalars(
                select(HistorialEnvio).where(HistorialEnvio.campana_id == campana_id)
            )
        }
        assert estados == {ids[0]: "incierto", ids[1]: "cancelado"}
        assert recuperar_contenido(sesion, campana, configuracion.clave_cifrado) is None


def test_cancelar_envio_detiene_pendientes_y_registra_el_que_gmail_confirmo(contexto, monkeypatch):
    fabrica, configuracion, usuario_id, campana_id, ids = contexto
    with fabrica() as sesion:
        campana, usuario = sesion.get(Campana, campana_id), sesion.get(Usuario, usuario_id)
        vista = campanas_envio.preparar_envio(
            sesion, campana, usuario, configuracion.clave_cifrado
        )
        campanas_envio.autorizar_envio(
            sesion,
            campana,
            usuario,
            configuracion.clave_cifrado,
            ids,
            campanas_envio.huella_preparacion(vista),
        )

    enviados = []

    async def enviar_ficticio(
        _config, _token, _remitente, destino, _asunto, _cuerpo, _adjuntos, _html=None
    ):
        enviados.append(destino)
        with fabrica() as sesion:
            campanas_envio.cancelar_envio(sesion, sesion.get(Campana, campana_id))
        return "confirmado-por-gmail"

    monkeypatch.setattr(trabajador_envio, "enviar_gmail", enviar_ficticio)
    asyncio.run(trabajador_envio.procesar_envio(fabrica, configuracion, campana_id))
    assert len(enviados) == 1
    assert enviados[0] in {"empresa1@ejemplo.com", "empresa2@ejemplo.com"}
    with fabrica() as sesion:
        campana = sesion.get(Campana, campana_id)
        assert campana.estado == EstadoCampana.CANCELADA
        estados = {
            envio.correo: envio.estado
            for envio in sesion.scalars(
                select(HistorialEnvio).where(HistorialEnvio.campana_id == campana_id)
            )
        }
        assert estados[enviados[0]] == "enviado"
        assert list(estados.values()).count("cancelado") == 1
        assert recuperar_contenido(sesion, campana, configuracion.clave_cifrado) is None
