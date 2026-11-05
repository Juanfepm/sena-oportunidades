"""La consulta real solo prepara resultados; no contacta ni postula empresas."""

import asyncio
import sys
from datetime import date
from time import monotonic, sleep

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base
from backend.aplicacion.configuracion import Configuracion
from backend.aplicacion.integraciones.contratos import (
    AccesoSGVARestringido,
    EvaluacionIA,
    OfertaSGVA,
    SGVACaido,
    SGVAEntornoIncompatible,
    SGVANoDisponible,
    SGVASinConexion,
)
from backend.aplicacion.integraciones.sgva import (
    _buscar_departamento,
    _respuesta_ingreso,
    consultar_sgva,
    dias_desde,
    filas_recientes,
    mensaje_error_ingreso,
    seleccionar_opcion,
)
from backend.aplicacion.modelos import Campana, ContenidoTemporal, NavegadorSGVA
from backend.aplicacion.principal import crear_aplicacion
from backend.aplicacion.servicios.trabajador_sgva import etapa_error_sgva


def test_opciones_y_fecha_sgva() -> None:
    opciones = [
        {"value": "0", "label": "Seleccione"},
        {"value": "11", "label": "BOGOTA D.C."},
        {"value": "76", "label": "VALLE"},
    ]
    assert seleccionar_opcion(opciones, "Bogotá D. C.") == "11"
    assert seleccionar_opcion(opciones, "Bogotá") == "11"
    assert seleccionar_opcion(opciones, "Valle del Cauca") == "76"
    assert dias_desde("20/10/2026", date(2026, 10, 25)) == 5
    assert dias_desde("fecha inválida", date(2026, 10, 25)) is None


def test_distingue_avisos_de_credenciales_publicados_por_sgva() -> None:
    assert (
        mensaje_error_ingreso("El usuario no se encuentra en el sistema.")
        == "El usuario no se encuentra en el sistema."
    )
    assert (
        mensaje_error_ingreso("Usuario o contraseña incorrecta.")
        == "Usuario o contraseña incorrecta."
    )
    assert mensaje_error_ingreso("Error desconocido") == "SGVA no aceptó el acceso como aprendiz."


def test_redireccion_de_ingreso_sgva_conserva_https() -> None:
    class Respuesta:
        headers = {
            "location": "http://caprendizaje.sena.edu.co/sgva/Aprendices/Index",
            "set-cookie": "sesion=ficticia",
        }

    class Ruta:
        request = type("Peticion", (), {"method": "POST"})()

        async def fetch(self, *, max_redirects):
            assert max_redirects == 0
            return Respuesta()

        async def fulfill(self, *, response, headers):
            assert isinstance(response, Respuesta)
            assert headers["location"] == (
                "https://caprendizaje.sena.edu.co/sgva/Aprendices/Index"
            )
            assert headers["set-cookie"] == "sesion=ficticia"

    asyncio.run(_respuesta_ingreso(Ruta()))


def test_errores_sgva_distinguen_conexion_y_fallo_del_servidor() -> None:
    assert etapa_error_sgva(SGVASinConexion()) == "SGVA sin conexión"
    assert etapa_error_sgva(SGVACaido()) == "SGVA fuera de servicio"
    assert etapa_error_sgva(SGVANoDisponible()) == "SGVA no respondió"
    assert etapa_error_sgva(AccesoSGVARestringido("Usuario o contraseña incorrecta.")) == (
        "SGVA rechazó la consulta: Usuario o contraseña incorrecta."
    )


@pytest.mark.skipif(
    sys.platform != "win32", reason="El bucle Selector causa el fallo solo en Windows"
)
def test_windows_rechaza_bucle_selector_antes_de_abrir_playwright() -> None:
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        with pytest.raises(SGVAEntornoIncompatible, match="sin --reload"):
            runner.run(consultar_sgva("documento", "clave", "todos", "todas", 30))


def test_todos_los_departamentos_y_ofertas_recientes_primero(monkeypatch) -> None:
    from backend.aplicacion.integraciones import sgva

    acciones = []

    class Selector:
        async def select_option(self, valor):
            acciones.append(("seleccionar", valor))

    class Pagina:
        def locator(self, selector):
            assert selector == "#sel_departamento"
            return Selector()

    async def opciones(_):
        return [{"value": "0", "label": "Seleccione"}, {"value": "91", "label": "AMAZONAS"}]

    async def buscar(_):
        acciones.append(("buscar", None))
        if acciones.count(("buscar", None)) == 1:
            return []
        return [
            [f'<button data-id-solicitud="{identificador}">', nombre, "", "", "", fecha]
            for identificador, nombre, fecha in (
                (1, "Antigua", "01/09/2026"),
                (2, "Reciente", "24/10/2026"),
                (3, "Más reciente", "25/10/2026"),
            )
        ]

    async def detalle(_, identificador, nombre, hoy):
        acciones.append(("detalle", identificador))
        return OfertaSGVA(
            nombre,
            None,
            None,
            "Perfil",
            "BOGOTA D.C.",
            "BOGOTA D.C.",
            dias_desde("25/10/2026", hoy),
        )

    async def pausa(_):
        return None

    monkeypatch.setattr(sgva, "_opciones", opciones)
    monkeypatch.setattr(sgva, "_filas_busqueda", buscar)
    monkeypatch.setattr(sgva, "_detalle", detalle)
    monkeypatch.setattr(sgva.asyncio, "sleep", pausa)
    ofertas = []
    asyncio.run(
        _buscar_departamento(
            Pagina(), "todos", "todas", 30, ofertas, set(), date(2026, 10, 25), limite=2
        )
    )
    assert acciones[:4] == [
        ("seleccionar", "91"),
        ("buscar", None),
        ("seleccionar", "0"),
        ("buscar", None),
    ]
    assert [accion for accion in acciones if accion[0] == "detalle"] == [
        ("detalle", "3"),
        ("detalle", "2"),
    ]
    assert [oferta.nombre_empresa for oferta in ofertas] == ["Más reciente", "Reciente"]


def test_orden_reciente_no_depende_del_orden_de_las_filas() -> None:
    filas = [["", "", "", "", "", fecha] for fecha in ("24/10/2026", "01/09/2026", "25/10/2026")]
    assert [fila[5] for fila in filas_recientes(filas, date(2026, 10, 25))] == [
        "25/10/2026",
        "24/10/2026",
        "01/09/2026",
    ]


@pytest.mark.parametrize("usar_ia", [False, True])
def test_campana_sgva_recibe_credenciales_solo_en_memoria(monkeypatch, usar_ia) -> None:
    from backend.aplicacion.servicios import trabajador_sgva

    recibidas = []
    progresos = []

    async def consulta_ficticia(documento, clave, departamento, ciudad, antiguedad, avance=None):
        recibidas.append((documento, clave, departamento, ciudad, antiguedad))
        await avance(80, "Leyendo detalle")
        await avance(72, "Analizando coincidencias")
        with cliente.app.state.fabrica_sesiones() as sesion:
            progresos.append(sesion.scalar(select(Campana.progreso)))
        return [
            OfertaSGVA(
                "Empresa excluida",
                "fuera@empresa.invalid",
                "3001234567",
                "Perfil excluido",
                "BOGOTA D.C.",
                "BOGOTA D. C.",
                1,
            ),
            OfertaSGVA(
                "Empresa de prueba",
                "contacto@empresa.invalid",
                "3001234567",
                "Perfil y funciones observadas",
                "BOGOTA D.C.",
                "BOGOTA D. C.",
                1,
            ),
        ]

    async def clasificacion_ficticia(clave, perfil, modalidad, ofertas, avance=None):
        assert clave == "clave-ia-de-prueba"
        assert perfil["habilidades"] == "Aprendí hojas de cálculo y análisis"
        assert modalidad == "presencial"
        assert len(ofertas) == 1
        assert ofertas[0].nombre_empresa == "Empresa de prueba"
        return [EvaluacionIA(90, "Coinciden las funciones.", "confirmada")]

    monkeypatch.setattr(trabajador_sgva, "consultar_sgva", consulta_ficticia)
    monkeypatch.setattr(trabajador_sgva, "clasificar_ofertas", clasificacion_ficticia)
    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    with motor.begin() as conexion:
        conexion.execute(NavegadorSGVA.__table__.insert().values(id=1))
    configuracion = Configuracion(
        entorno="desarrollo",
        base_datos="sqlite://",
        sgva_activo=True,
        clave_pruebas="clave-segura-de-pruebas-locales-2026",
        secreto_sesion="secreto-de-sesion-local-largo-2026",
        gemini_clave="clave-ia-de-prueba" if usar_ia else None,
    )
    with TestClient(crear_aplicacion(configuracion, motor)) as cliente:
        acceso = {"Authorization": "Bearer clave-segura-de-pruebas-locales-2026"}
        solicitud = {
            "modalidad": "presencial",
            "departamento": "Bogotá D. C.",
            "ciudad": "todas",
            "antiguedad_dias": 7,
            "mayor_de_edad": True,
            "acepta_tratamiento": True,
            "correos_excluidos": ["fuera@empresa.invalid"],
        }
        borrador = cliente.post("/api/v1/campanas", headers=acceso, json=solicitud)
        assert borrador.status_code == 201, borrador.json()
        campana = borrador.json()
        ruta = f"/api/v1/campanas/{campana['id']}/iniciar"
        assert cliente.post(ruta, headers=acceso).status_code == 422
        datos_acceso = {"numero_documento": "1234567890", "clave_sgva": "clave-sgva-solo-prueba"}
        if usar_ia:
            assert cliente.post(ruta, headers=acceso, json=datos_acceso).status_code == 422
            assert (
                cliente.post(
                    ruta, headers=acceso, json={**datos_acceso, "numero_documento": "1.235.678"}
                ).status_code
                == 422
            )
            datos_acceso.update(
                {
                    "acepta_ia": True,
                    "perfil_ia": {
                        "habilidades": "Aprendí hojas de cálculo y análisis",
                        "actividades_deseadas": "Analizar datos",
                        "actividades_no_deseadas": "Ventas",
                    },
                }
            )
        respuesta = cliente.post(ruta, headers=acceso, json=datos_acceso)
        assert respuesta.status_code == 200
        plazo = monotonic() + 5
        while monotonic() < plazo:
            estado = cliente.get(f"/api/v1/campanas/{campana['id']}", headers=acceso).json()
            if estado["estado"] == "esperando_confirmacion":
                break
            sleep(0.05)
        assert estado["modo_consulta"] == "sgva"
        assert estado["estado"] == "esperando_confirmacion"
        ofertas = cliente.get(
            f"/api/v1/campanas/{campana['id']}/destinatarios", headers=acceso
        ).json()
        assert len(ofertas) == 1
        assert ofertas[0]["estado"] == ("alta_coincidencia" if usar_ia else "pendiente_ia")
        assert ofertas[0]["puntuacion"] == (90 if usar_ia else None)
        assert ofertas[0]["descripcion"] == "Perfil y funciones observadas"
        assert "clave-sgva-solo-prueba" not in str(estado) + str(ofertas)
        with motor.connect() as conexion:
            datos_persistidos = [
                tuple(fila)
                for tabla in ("campanas", "destinatarios")
                for fila in conexion.execute(text(f"SELECT * FROM {tabla}"))
            ]
        assert "clave-sgva-solo-prueba" not in str(datos_persistidos)
        assert "Aprendí hojas de cálculo y análisis" not in str(datos_persistidos)
        assert recibidas == [("1234567890", "clave-sgva-solo-prueba", "Bogotá D. C.", "todas", 7)]
        assert progresos == [80]
    motor.dispose()


def test_cancelar_consulta_libera_navegador_y_conserva_error_concreto(monkeypatch) -> None:
    from backend.aplicacion.integraciones.contratos import AccesoSGVARestringido
    from backend.aplicacion.servicios import trabajador_sgva

    async def consulta_ficticia(documento, _clave, _departamento, _ciudad, _dias, avance=None):
        if documento == "1234567890":
            await avance(15, "Acceso a SGVA confirmado")
            await asyncio.sleep(60)
        if documento == "0000000000":
            raise AccesoSGVARestringido("El usuario no se encuentra en el sistema.")
        return []

    monkeypatch.setattr(trabajador_sgva, "consultar_sgva", consulta_ficticia)
    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    with motor.begin() as conexion:
        conexion.execute(NavegadorSGVA.__table__.insert().values(id=1))
    configuracion = Configuracion(
        entorno="desarrollo",
        base_datos="sqlite://",
        sgva_activo=True,
        clave_pruebas="clave-segura-de-pruebas-locales-2026",
        clave_cifrado=Fernet.generate_key().decode(),
        secreto_sesion="secreto-de-sesion-local-largo-2026",
    )
    with TestClient(crear_aplicacion(configuracion, motor)) as cliente:
        acceso = {"Authorization": "Bearer clave-segura-de-pruebas-locales-2026"}
        solicitud = {
            "modalidad": "remoto",
            "departamento": "todos",
            "ciudad": "todas",
            "antiguedad_dias": 7,
            "mayor_de_edad": True,
            "acepta_tratamiento": True,
            "correos_excluidos": [],
        }

        def iniciar(documento):
            borrador = cliente.post("/api/v1/campanas", headers=acceso, json=solicitud)
            assert borrador.status_code == 201
            identificador = borrador.json()["id"]
            contenido = cliente.put(
                f"/api/v1/campanas/{identificador}/contenido",
                headers=acceso,
                data={
                    "habilidades": "Organizo información y preparo reportes.",
                    "actividades_deseadas": "Apoyar al equipo administrativo.",
                    "asunto": "Solicitud de práctica",
                    "cuerpo": (
                        "Hola, me interesa conocer las funciones de esta práctica. "
                        "Gracias por su tiempo."
                    ),
                },
            )
            assert contenido.status_code == 200
            respuesta = cliente.post(
                f"/api/v1/campanas/{identificador}/iniciar",
                headers=acceso,
                json={"numero_documento": documento, "clave_sgva": "clave-ficticia"},
            )
            assert respuesta.status_code == 200
            return identificador

        def esperar_estado(identificador, esperado):
            plazo = monotonic() + 5
            while monotonic() < plazo:
                estado = cliente.get(f"/api/v1/campanas/{identificador}", headers=acceso).json()
                if estado["estado"] == esperado:
                    return estado
                sleep(0.05)
            pytest.fail(f"La campaña no llegó a {esperado}.")

        primera = iniciar("1234567890")
        esperar_estado(primera, "consultando")
        cancelada = cliente.post(f"/api/v1/campanas/{primera}/cancelar", headers=acceso)
        assert cancelada.status_code == 200
        assert cancelada.json()["estado"] == "cancelada"
        with cliente.app.state.fabrica_sesiones() as sesion:
            assert sesion.get(ContenidoTemporal, primera) is None
        segunda = iniciar("2222222222")
        esperar_estado(segunda, "esperando_confirmacion")
        tercera = iniciar("0000000000")
        error = esperar_estado(tercera, "error")
        assert (
            error["etapa"] == "SGVA rechazó la consulta: El usuario no se encuentra en el sistema."
        )
        with cliente.app.state.fabrica_sesiones() as sesion:
            assert sesion.get(ContenidoTemporal, tercera) is None
    motor.dispose()
