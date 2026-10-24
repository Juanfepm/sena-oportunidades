"""La API no acepta plan, claves ni contenido del correo desde un borrador."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base
from backend.aplicacion.configuracion import Configuracion
from backend.aplicacion.modelos import Campana, HistorialEnvio, NavegadorSGVA, Usuario
from backend.aplicacion.principal import crear_aplicacion


@pytest.fixture
def cliente():
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    with motor.begin() as conexion:
        conexion.execute(NavegadorSGVA.__table__.insert().values(id=1))
    configuracion = Configuracion(entorno="desarrollo", base_datos="sqlite://", clave_pruebas="clave-segura-de-pruebas-locales-2026")
    with TestClient(crear_aplicacion(configuracion, motor)) as cliente_actual:
        yield cliente_actual
    motor.dispose()


def solicitud_valida() -> dict:
    return {
        "modalidad": "remoto",
        "departamento": "todos",
        "ciudad": "todas",
        "antiguedad_dias": 14,
        "permitir_recontacto": True,
        "correos_excluidos": ["Empresa@Ejemplo.COM", "empresa@ejemplo.com"],
        "mayor_de_edad": True,
        "acepta_tratamiento": True,
    }


def acceso() -> dict[str, str]:
    return {"Authorization": "Bearer clave-segura-de-pruebas-locales-2026"}


def test_capacidades_no_prometen_integraciones(cliente: TestClient):
    respuesta = cliente.get("/api/v1/salud")
    assert respuesta.status_code == 200
    assert respuesta.headers["Cache-Control"] == "no-store"
    capacidades = cliente.get("/api/v1/capacidades").json()
    assert capacidades["borradores"] is True
    assert capacidades["sgva"] is False
    assert capacidades["gmail"] is False
    assert capacidades["trabajador_activo"] is False


def test_borrador_necesita_autorizacion(cliente: TestClient):
    assert cliente.post("/api/v1/campanas", json=solicitud_valida()).status_code == 401
    assert cliente.post("/api/v1/campanas", json=solicitud_valida(), headers={"Authorization": "Bearer incorrecta"}).status_code == 401


def test_borrador_persistente_y_exclusiones_normalizadas(cliente: TestClient):
    respuesta = cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso())
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["estado"] == "borrador"
    assert datos["plan_aplicado"] == "gratis"
    assert datos["limite_contactos"] == 8
    assert cliente.get("/api/v1/campanas", headers=acceso()).json()[0]["id"] == datos["id"]
    assert cliente.get("/api/v1/correos-excluidos", headers=acceso()).json() == ["empresa@ejemplo.com"]
    assert cliente.post(f"/api/v1/campanas/{datos['id']}/iniciar", headers=acceso()).status_code == 503
    assert cliente.get("/api/v1/historial", headers=acceso()).json() == []
    assert cliente.delete("/api/v1/correos-excluidos/empresa@ejemplo.com", headers=acceso()).status_code == 204


def test_un_usuario_no_puede_leer_una_campana_ajena(cliente: TestClient):
    with cliente.app.state.fabrica_sesiones() as sesion:
        otro = Usuario(identificador_externo="desarrollo:otro")
        sesion.add(otro)
        sesion.flush()
        ajena = Campana(usuario_id=otro.id, plan_aplicado="gratis", limite_contactos=8,
                        modalidad="remoto", departamento="todos", ciudad="todas", antiguedad_dias=7)
        sesion.add(ajena)
        sesion.commit()
        identificador = ajena.id
    assert cliente.get(f"/api/v1/campanas/{identificador}", headers=acceso()).status_code == 404


def test_ubicacion_valida_del_formulario(cliente: TestClient):
    solicitud = solicitud_valida()
    solicitud.update(modalidad="presencial", departamento="Antioquia", ciudad="Abejorral")
    assert cliente.post("/api/v1/campanas", json=solicitud, headers=acceso()).status_code == 201


def test_plan_gratis_espera_despues_de_un_envio_y_premium_no(cliente: TestClient):
    primera = cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso()).json()
    with cliente.app.state.fabrica_sesiones() as sesion:
        usuario = sesion.scalar(select(Usuario).where(Usuario.identificador_externo == "desarrollo:aprendiz-local"))
        sesion.add(HistorialEnvio(usuario_id=usuario.id, campana_id=primera["id"],
                                 correo="empresa@ejemplo.com", enviado_en=datetime.now(timezone.utc)))
        sesion.commit()
    disponibilidad = cliente.get("/api/v1/disponibilidad", headers=acceso()).json()
    assert disponibilidad["puede_buscar"] is False
    assert disponibilidad["proxima_fecha"] is not None
    assert cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso()).status_code == 429
    with cliente.app.state.fabrica_sesiones() as sesion:
        usuario = sesion.scalar(select(Usuario).where(Usuario.identificador_externo == "desarrollo:aprendiz-local"))
        usuario.plan = "premium"
        sesion.commit()
    assert cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso()).status_code == 201


@pytest.mark.parametrize("departamento,ciudad", [
    ("Inventado", "todas"),
    ("Antioquia", "Cali"),
])
def test_ubicacion_fuera_del_formulario(cliente: TestClient, departamento: str, ciudad: str):
    solicitud = solicitud_valida()
    solicitud.update(modalidad="presencial", departamento=departamento, ciudad=ciudad)
    assert cliente.post("/api/v1/campanas", json=solicitud, headers=acceso()).status_code == 422


@pytest.mark.parametrize("campo,valor", [
    ("mayor_de_edad", False),
    ("acepta_tratamiento", False),
    ("antiguedad_dias", 45),
    ("departamento", "Antioquia"),
    ("plan", "premium"),
    ("clave_sgva", "contraseña-no-admitida"),
    ("cuerpo_correo", "texto-no-admitido"),
    ("correos_excluidos", [f"empresa{numero}@ejemplo.com" for numero in range(6)]),
])
def test_borrador_rechaza_datos_no_permitidos(cliente: TestClient, campo: str, valor):
    solicitud = solicitud_valida()
    solicitud[campo] = valor
    assert cliente.post("/api/v1/campanas", json=solicitud, headers=acceso()).status_code == 422
