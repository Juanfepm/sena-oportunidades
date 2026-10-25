"""La consulta real solo prepara resultados; no contacta ni postula empresas."""

from datetime import date
from time import monotonic, sleep

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base
from backend.aplicacion.configuracion import Configuracion
from backend.aplicacion.integraciones.contratos import OfertaSGVA
from backend.aplicacion.integraciones.sgva import dias_desde, seleccionar_opcion
from backend.aplicacion.modelos import NavegadorSGVA
from backend.aplicacion.principal import crear_aplicacion


def test_opciones_y_fecha_sgva() -> None:
    opciones = [{"value": "0", "label": "Seleccione"}, {"value": "11", "label": "BOGOTA D.C."},
                {"value": "76", "label": "VALLE"}]
    assert seleccionar_opcion(opciones, "Bogotá D. C.") == "11"
    assert seleccionar_opcion(opciones, "Bogotá") == "11"
    assert seleccionar_opcion(opciones, "Valle del Cauca") == "76"
    assert dias_desde("20/10/2026", date(2026, 10, 25)) == 5
    assert dias_desde("fecha inválida", date(2026, 10, 25)) is None


def test_campana_sgva_recibe_credenciales_solo_en_memoria(monkeypatch) -> None:
    from backend.aplicacion.servicios import trabajador_sgva

    recibidas = []

    async def consulta_ficticia(documento, clave, departamento, ciudad, antiguedad, avance=None):
        recibidas.append((documento, clave, departamento, ciudad, antiguedad))
        await avance(50, "Leyendo detalle")
        return [OfertaSGVA("Empresa de prueba", "contacto@empresa.invalid", "3001234567",
                           "Perfil y funciones observadas", "BOGOTA D.C.", "BOGOTA D. C.", 1)]

    monkeypatch.setattr(trabajador_sgva, "consultar_sgva", consulta_ficticia)
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    with motor.begin() as conexion:
        conexion.execute(NavegadorSGVA.__table__.insert().values(id=1))
    configuracion = Configuracion(entorno="desarrollo", base_datos="sqlite://", sgva_activo=True,
                                 clave_pruebas="clave-segura-de-pruebas-locales-2026",
                                 secreto_sesion="secreto-de-sesion-local-largo-2026")
    with TestClient(crear_aplicacion(configuracion, motor)) as cliente:
        acceso = {"Authorization": "Bearer clave-segura-de-pruebas-locales-2026"}
        solicitud = {"modalidad": "presencial", "departamento": "Bogotá D. C.", "ciudad": "todas",
                     "antiguedad_dias": 7, "mayor_de_edad": True, "acepta_tratamiento": True}
        borrador = cliente.post("/api/v1/campanas", headers=acceso, json=solicitud)
        assert borrador.status_code == 201, borrador.json()
        campana = borrador.json()
        ruta = f"/api/v1/campanas/{campana['id']}/iniciar"
        assert cliente.post(ruta, headers=acceso).status_code == 422
        respuesta = cliente.post(ruta, headers=acceso, json={"numero_documento": "1234567890",
                                                         "clave_sgva": "clave-sgva-solo-prueba"})
        assert respuesta.status_code == 200
        plazo = monotonic() + 5
        while monotonic() < plazo:
            estado = cliente.get(f"/api/v1/campanas/{campana['id']}", headers=acceso).json()
            if estado["estado"] == "esperando_confirmacion":
                break
            sleep(0.05)
        assert estado["modo_consulta"] == "sgva"
        assert estado["estado"] == "esperando_confirmacion"
        ofertas = cliente.get(f"/api/v1/campanas/{campana['id']}/destinatarios", headers=acceso).json()
        assert ofertas[0]["estado"] == "pendiente_ia"
        assert ofertas[0]["puntuacion"] is None
        assert ofertas[0]["descripcion"] == "Perfil y funciones observadas"
        assert "clave-sgva-solo-prueba" not in str(estado) + str(ofertas)
        with motor.connect() as conexion:
            datos_persistidos = [tuple(fila) for tabla in ("campanas", "destinatarios")
                                for fila in conexion.execute(text(f"SELECT * FROM {tabla}"))]
        assert "clave-sgva-solo-prueba" not in str(datos_persistidos)
        assert recibidas == [("1234567890", "clave-sgva-solo-prueba", "Bogotá D. C.", "todas", 7)]
    motor.dispose()
