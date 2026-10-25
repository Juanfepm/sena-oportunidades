"""El contenido queda cifrado, vence y pertenece a una sola cuenta."""

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base
from backend.aplicacion.configuracion import Configuracion
from backend.aplicacion.modelos import AdjuntoTemporal, Campana, ContenidoTemporal, Usuario
from backend.aplicacion.principal import crear_aplicacion
from backend.aplicacion.servicios.temporales import limpiar_expirados, recuperar_contenido


@pytest.fixture
def cliente_temporal():
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    configuracion = Configuracion(
        entorno="desarrollo",
        base_datos="sqlite://",
        clave_pruebas="clave-local-para-probar-contenido-2026",
        clave_cifrado=Fernet.generate_key().decode(),
        secreto_sesion="secreto-local-para-contenido-temporal-2026",
    )
    with TestClient(crear_aplicacion(configuracion, motor)) as cliente:
        yield cliente, configuracion
    motor.dispose()


def crear_campana(cliente: TestClient) -> str:
    respuesta = cliente.post("/api/v1/campanas", headers={"Authorization": "Bearer clave-local-para-probar-contenido-2026"}, json={
        "modalidad": "remoto",
        "departamento": "todos",
        "ciudad": "todas",
        "antiguedad_dias": 7,
        "mayor_de_edad": True,
        "acepta_tratamiento": True,
    })
    assert respuesta.status_code == 201
    return respuesta.json()["id"]


def datos_formulario() -> dict[str, str]:
    return {
        "habilidades": "Sé organizar documentos y manejar hojas de cálculo.",
        "actividades_deseadas": "Quiero apoyar procesos administrativos.",
        "actividades_no_deseadas": "Ventas puerta a puerta",
        "asunto": "Solicitud de práctica",
        "cuerpo": "Hola, me interesa conocer las funciones de esta oportunidad de práctica. Gracias por su tiempo.",
    }


def test_guarda_recupera_y_borra_sin_exponer_texto(cliente_temporal) -> None:
    cliente, configuracion = cliente_temporal
    campana_id = crear_campana(cliente)
    ruta = f"/api/v1/campanas/{campana_id}/contenido"
    cabeceras = {"Authorization": "Bearer clave-local-para-probar-contenido-2026"}

    assert cliente.put(ruta, data=datos_formulario(), files=[
        ("archivos", ("hoja.txt", b"Texto privado de mi hoja de vida\n", "text/plain")),
    ]).status_code == 401
    guardado = cliente.put(ruta, headers=cabeceras, data=datos_formulario(), files=[
        ("archivos", ("hoja.txt", b"Texto privado de mi hoja de vida\n", "text/plain")),
    ])
    assert guardado.status_code == 200
    assert guardado.json()["archivos"] == ["hoja.txt"]
    assert cliente.get(ruta, headers=cabeceras).json()["archivos"] == ["hoja.txt"]
    lista = cliente.get("/api/v1/contenidos-temporales", headers=cabeceras)
    assert [contenido["campana_id"] for contenido in lista.json()] == [campana_id]

    with cliente.app.state.fabrica_sesiones() as sesion:
        campana = sesion.get(Campana, campana_id)
        contenido = sesion.get(ContenidoTemporal, campana_id)
        adjunto = sesion.scalar(select(AdjuntoTemporal))
        assert contenido is not None and adjunto is not None
        assert b"hojas de c" not in contenido.contenido_cifrado
        assert b"hoja.txt" not in adjunto.metadatos_cifrados
        assert b"Texto privado" not in adjunto.contenido_cifrado
        recuperado = recuperar_contenido(sesion, campana, configuracion.clave_cifrado)
        assert recuperado.mensaje.asunto == "Solicitud de práctica"
        assert recuperado.archivos[0].contenido == b"Texto privado de mi hoja de vida\n"

    reemplazo = cliente.put(ruta, headers=cabeceras, data={**datos_formulario(), "asunto": "Mensaje corregido"})
    assert reemplazo.status_code == 200
    assert reemplazo.json()["archivos"] == []
    with cliente.app.state.fabrica_sesiones() as sesion:
        assert sesion.scalar(select(AdjuntoTemporal)) is None

    assert cliente.delete(ruta, headers=cabeceras).status_code == 204
    assert cliente.get(ruta, headers=cabeceras).status_code == 404
    assert cliente.get("/api/v1/contenidos-temporales", headers=cabeceras).json() == []
    with cliente.app.state.fabrica_sesiones() as sesion:
        assert sesion.get(ContenidoTemporal, campana_id) is None
        assert sesion.scalar(select(AdjuntoTemporal)) is None


def test_rechaza_archivos_invalidos_y_ajenos(cliente_temporal) -> None:
    cliente, _ = cliente_temporal
    campana_id = crear_campana(cliente)
    ruta = f"/api/v1/campanas/{campana_id}/contenido"
    cabeceras = {"Authorization": "Bearer clave-local-para-probar-contenido-2026"}
    assert cliente.put(ruta, headers=cabeceras, data=datos_formulario(), files=[
        ("archivos", ("hoja.pdf", b"no es un PDF", "application/pdf")),
    ]).status_code == 422
    assert cliente.put(ruta, headers=cabeceras, data={**datos_formulario(), "clave_sgva": "no-guardar"}).status_code == 422
    assert cliente.put(ruta, headers={**cabeceras, "Content-Length": str(12 * 1024 * 1024)},
                       data=datos_formulario()).status_code == 413
    assert cliente.put(ruta, headers=cabeceras, data=datos_formulario(), files=[
        ("archivos", ("uno.txt", b"uno", "text/plain")),
        ("archivos", ("dos.txt", b"dos", "text/plain")),
    ]).status_code == 422
    with cliente.app.state.fabrica_sesiones() as sesion:
        otro = Usuario(identificador_externo="desarrollo:otra-cuenta")
        sesion.add(otro)
        sesion.flush()
        ajena = Campana(usuario_id=otro.id, plan_aplicado="gratis", limite_contactos=8,
                        modalidad="remoto", departamento="todos", ciudad="todas", antiguedad_dias=7)
        sesion.add(ajena)
        sesion.commit()
        ajena_id = ajena.id
    assert cliente.put(f"/api/v1/campanas/{ajena_id}/contenido", headers=cabeceras, data=datos_formulario()).status_code == 404
    assert cliente.get(f"/api/v1/campanas/{ajena_id}/contenido", headers=cabeceras).status_code == 404


def test_vencimiento_elimina_texto_y_adjuntos(cliente_temporal) -> None:
    cliente, configuracion = cliente_temporal
    campana_id = crear_campana(cliente)
    ruta = f"/api/v1/campanas/{campana_id}/contenido"
    cabeceras = {"Authorization": "Bearer clave-local-para-probar-contenido-2026"}
    assert cliente.put(ruta, headers=cabeceras, data=datos_formulario(), files=[
        ("archivos", ("hoja.txt", b"Hoja temporal", "text/plain")),
    ]).status_code == 200
    with cliente.app.state.fabrica_sesiones() as sesion:
        sesion.get(ContenidoTemporal, campana_id).vence_en = datetime.now(timezone.utc) - timedelta(seconds=1)
        sesion.commit()
        assert recuperar_contenido(sesion, sesion.get(Campana, campana_id), configuracion.clave_cifrado) is None
        assert sesion.scalar(select(AdjuntoTemporal)) is None

    assert cliente.get(ruta, headers=cabeceras).status_code == 404
    with cliente.app.state.fabrica_sesiones() as sesion:
        assert limpiar_expirados(sesion) == 0


def test_limite_de_dos_borradores_activos(cliente_temporal) -> None:
    cliente, _ = cliente_temporal
    cabeceras = {"Authorization": "Bearer clave-local-para-probar-contenido-2026"}
    campanas = [crear_campana(cliente) for _ in range(3)]
    for campana_id in campanas[:2]:
        assert cliente.put(f"/api/v1/campanas/{campana_id}/contenido", headers=cabeceras,
                           data=datos_formulario()).status_code == 200
    tercero = f"/api/v1/campanas/{campanas[2]}/contenido"
    assert cliente.put(tercero, headers=cabeceras, data=datos_formulario()).status_code == 429
    assert cliente.delete(f"/api/v1/campanas/{campanas[0]}/contenido", headers=cabeceras).status_code == 204
    assert cliente.put(tercero, headers=cabeceras, data=datos_formulario()).status_code == 200
