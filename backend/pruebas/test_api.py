"""La API no acepta plan, claves ni contenido del correo desde un borrador."""

from datetime import datetime, timedelta, timezone
from time import monotonic, sleep
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base
from backend.aplicacion.configuracion import Configuracion
from backend.aplicacion.modelos import (
    Campana,
    ConexionGmail,
    Destinatario,
    HistorialEnvio,
    NavegadorSGVA,
    Usuario,
)
from backend.aplicacion.principal import crear_aplicacion


@pytest.fixture
def cliente():
    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    with motor.begin() as conexion:
        conexion.execute(NavegadorSGVA.__table__.insert().values(id=1))
    configuracion = Configuracion(
        entorno="desarrollo",
        base_datos="sqlite://",
        clave_pruebas="clave-segura-de-pruebas-locales-2026",
        secreto_sesion="secreto-de-sesion-local-largo-2026",
    )
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
    assert capacidades["trabajador_activo"] is True
    assert capacidades["trabajador_demo"] is True


def test_google_oauth_requiere_configuracion(cliente: TestClient):
    respuesta = cliente.get("/api/v1/autenticacion/google/iniciar", follow_redirects=False)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/error.html?tipo=servicio"


def test_frontend_y_cuenta_requieren_sesion(cliente: TestClient):
    portada = cliente.get("/")
    assert portada.status_code == 200
    assert "Entrar con Google" in portada.text
    assert cliente.get("/guiones/autenticacion.js").status_code == 200
    assert cliente.get("/api/v1/autenticacion/yo").status_code == 401
    assert "No encontramos esta página" in cliente.get("/no-existe").text
    assert "Servicio temporalmente no disponible" in cliente.get("/error.html?tipo=servicio").text


def test_turno_solo_revela_posicion_de_la_campana_propia(cliente: TestClient):
    cliente.get("/api/v1/autenticacion/yo", headers=acceso())
    with cliente.app.state.fabrica_sesiones() as sesion:
        usuario = sesion.scalar(
            select(Usuario).where(Usuario.identificador_externo == "desarrollo:aprendiz-local")
        )
        ajeno = Usuario(identificador_externo="google:otro", correo_google="otro@ejemplo.com")
        sesion.add(ajeno)
        sesion.flush()
        ahora = datetime.now(timezone.utc)

        def campana_para(propietario, estado, segundos):
            return Campana(
                usuario_id=propietario.id,
                estado=estado,
                modo_consulta="sgva",
                plan_aplicado="gratis",
                limite_contactos=8,
                modalidad="remoto",
                departamento="todos",
                ciudad="todas",
                antiguedad_dias=7,
                creado_en=ahora + timedelta(seconds=segundos),
            )

        sesion.add_all(
            [
                campana_para(ajeno, "consultando", 0),
                campana_para(usuario, "en_cola", 1),
                campana_para(usuario, "en_cola", 2),
            ]
        )
        sesion.flush()
        propias = list(
            sesion.scalars(
                select(Campana).where(Campana.usuario_id == usuario.id).order_by(Campana.creado_en)
            )
        )
        ajena = sesion.scalar(select(Campana).where(Campana.usuario_id == ajeno.id))
        sesion.commit()
    primera = cliente.get(f"/api/v1/campanas/{propias[0].id}/turno", headers=acceso())
    segunda = cliente.get(f"/api/v1/campanas/{propias[1].id}/turno", headers=acceso())
    assert primera.json()["personas_delante"] == 1
    assert segunda.json()["personas_delante"] == 2
    assert cliente.get(f"/api/v1/campanas/{ajena.id}/turno", headers=acceso()).status_code == 404


def test_google_inicia_sesion_y_permita_cerrarla(monkeypatch: pytest.MonkeyPatch):
    from backend.aplicacion.integraciones import oauth_google

    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    configuracion = Configuracion(
        entorno="pruebas",
        base_datos="sqlite://",
        google_cliente_id="cliente-prueba.apps.googleusercontent.com",
        google_cliente_secreto="secreto-ficticio",
        secreto_sesion="clave-firmada-para-pruebas-de-google-2026",
        clave_cifrado=Fernet.generate_key().decode(),
    )

    revocaciones = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        if peticion.url.path == "/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "token-ficticio",
                    "refresh_token": "renovacion-secreta",
                    "scope": "openid email profile https://www.googleapis.com/auth/gmail.send",
                },
            )
        if peticion.url.path == "/v1/userinfo":
            assert peticion.headers["Authorization"] == "Bearer token-ficticio"
            return httpx.Response(
                200,
                json={
                    "sub": "identificador-estable",
                    "email": "Aprendiz@Ejemplo.com",
                    "email_verified": True,
                    "name": "Aprendiz de prueba",
                },
            )
        if peticion.url.path == "/revoke":
            revocaciones.append(peticion.content)
            return httpx.Response(200)
        return httpx.Response(404)

    cliente_httpx = httpx.AsyncClient
    monkeypatch.setattr(
        oauth_google.httpx,
        "AsyncClient",
        lambda **opciones: cliente_httpx(transport=httpx.MockTransport(responder), **opciones),
    )
    try:
        with TestClient(crear_aplicacion(configuracion, motor)) as cliente:
            inicio = cliente.get("/api/v1/autenticacion/google/iniciar", follow_redirects=False)
            assert inicio.status_code == 307
            parametros = parse_qs(urlsplit(inicio.headers["location"]).query)
            assert "https://www.googleapis.com/auth/gmail.send" in parametros["scope"][0]
            assert parametros["access_type"] == ["offline"]
            invalido = cliente.get(
                "/api/v1/autenticacion/google/callback?code=ficticio&state=incorrecto",
                follow_redirects=False,
            )
            assert invalido.status_code == 303
            assert invalido.headers["location"] == "/error.html?tipo=google"

            inicio = cliente.get("/api/v1/autenticacion/google/iniciar", follow_redirects=False)
            estado = parse_qs(urlsplit(inicio.headers["location"]).query)["state"][0]
            regreso = cliente.get(
                f"/api/v1/autenticacion/google/callback?code=ficticio&state={estado}",
                follow_redirects=False,
            )
            assert regreso.status_code == 303
            assert regreso.headers["location"] == "/#inicio"
            cuenta = cliente.get("/api/v1/autenticacion/yo")
            assert cuenta.status_code == 200
            assert cuenta.json()["correo"] == "aprendiz@ejemplo.com"
            assert cuenta.json()["plan"] == "gratis"
            assert cliente.get("/api/v1/gmail/estado").json()["conectado"] is True
            with cliente.app.state.fabrica_sesiones() as sesion:
                conexion = sesion.scalar(select(ConexionGmail))
                assert conexion is not None
                assert "renovacion-secreta" not in conexion.token_renovacion_cifrado
            assert cliente.post("/api/v1/autenticacion/cerrar-sesion").status_code == 403
            csrf = cliente.get("/api/v1/autenticacion/csrf").json()["token"]
            assert cliente.post("/api/v1/campanas", json=solicitud_valida()).status_code == 403
            creada = cliente.post(
                "/api/v1/campanas", json=solicitud_valida(), headers={"X-CSRF-Token": csrf}
            )
            assert creada.status_code == 201
            ruta_contenido = f"/api/v1/campanas/{creada.json()['id']}/contenido"
            datos_contenido = {
                "habilidades": "Sé organizar documentos y manejar hojas de cálculo.",
                "actividades_deseadas": "Quiero apoyar procesos administrativos.",
                "asunto": "Solicitud de práctica",
                "cuerpo": (
                    "Hola, me interesa conocer las funciones de esta oportunidad de práctica. "
                    "Gracias por su tiempo."
                ),
            }
            assert cliente.put(ruta_contenido, data=datos_contenido).status_code == 403
            assert (
                cliente.put(
                    ruta_contenido, data=datos_contenido, headers={"X-CSRF-Token": csrf}
                ).status_code
                == 200
            )
            assert (
                cliente.post(
                    "/api/v1/autenticacion/cerrar-sesion", headers={"X-CSRF-Token": csrf}
                ).status_code
                == 204
            )
            assert cliente.get("/api/v1/autenticacion/yo").status_code == 401
            assert cliente.get("/api/v1/gmail/estado").status_code == 401
            assert revocaciones == [b"token=renovacion-secreta"]
            with cliente.app.state.fabrica_sesiones() as sesion:
                assert sesion.scalar(select(ConexionGmail)) is None
    finally:
        motor.dispose()


def test_cuenta_debupa_conserva_permiso_de_servicio_al_cerrar_sesion(
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.aplicacion.integraciones import oauth_google

    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    configuracion = Configuracion(
        entorno="pruebas",
        base_datos="sqlite://",
        google_cliente_id="cliente-prueba.apps.googleusercontent.com",
        google_cliente_secreto="secreto-ficticio",
        secreto_sesion="secreto-de-sesion-para-cuenta-debupa-2026",
        clave_cifrado=Fernet.generate_key().decode(),
        correo_administrador="debupawebapp@gmail.com",
    )

    def responder(peticion: httpx.Request) -> httpx.Response:
        if peticion.url.path == "/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "acceso-ficticio",
                    "refresh_token": "renovacion-del-servicio",
                    "scope": "openid email profile https://www.googleapis.com/auth/gmail.send",
                },
            )
        if peticion.url.path == "/v1/userinfo":
            return httpx.Response(
                200,
                json={
                    "sub": "cuenta-debupa",
                    "email": "debupawebapp@gmail.com",
                    "email_verified": True,
                    "name": "DEBUPA",
                },
            )
        if peticion.url.path == "/revoke":
            raise AssertionError(
                "El permiso del correo de servicio no debe revocarse al cerrar la sesión."
            )
        return httpx.Response(404)

    cliente_httpx = httpx.AsyncClient
    monkeypatch.setattr(
        oauth_google.httpx,
        "AsyncClient",
        lambda **opciones: cliente_httpx(transport=httpx.MockTransport(responder), **opciones),
    )
    try:
        with TestClient(crear_aplicacion(configuracion, motor)) as cliente:
            inicio = cliente.get("/api/v1/autenticacion/google/iniciar", follow_redirects=False)
            estado = parse_qs(urlsplit(inicio.headers["location"]).query)["state"][0]
            cliente.get(
                f"/api/v1/autenticacion/google/callback?code=ficticio&state={estado}",
                follow_redirects=False,
            )
            assert cliente.get("/api/v1/autenticacion/yo").json()["es_administrador"] is True
            assert cliente.get("/api/v1/autenticacion/yo").json()["plan"] == "premium"
            csrf = cliente.get("/api/v1/autenticacion/csrf").json()["token"]
            assert (
                cliente.post(
                    "/api/v1/autenticacion/cerrar-sesion", headers={"X-CSRF-Token": csrf}
                ).status_code
                == 204
            )
            assert cliente.get("/api/v1/autenticacion/yo").status_code == 401
            with cliente.app.state.fabrica_sesiones() as sesion:
                assert sesion.scalar(select(ConexionGmail)) is not None
    finally:
        motor.dispose()


def test_gmail_reconexion_y_desconexion(monkeypatch: pytest.MonkeyPatch):
    from backend.aplicacion.integraciones import oauth_google

    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    configuracion = Configuracion(
        entorno="pruebas",
        base_datos="sqlite://",
        google_cliente_id="cliente-prueba.apps.googleusercontent.com",
        google_cliente_secreto="secreto-ficticio",
        secreto_sesion="clave-firmada-para-pruebas-de-gmail-2026",
        clave_cifrado=Fernet.generate_key().decode(),
    )

    veces = 0

    def responder(peticion: httpx.Request) -> httpx.Response:
        nonlocal veces
        if peticion.url.path == "/token":
            veces += 1
            datos = {
                "access_token": "token-ficticio",
                "scope": "openid email profile https://www.googleapis.com/auth/gmail.send",
            }
            if veces == 1:
                datos["refresh_token"] = "renovacion-secreta"
            if veces == 3:
                datos["scope"] = "openid email profile"
            return httpx.Response(200, json=datos)
        if peticion.url.path == "/v1/userinfo":
            return httpx.Response(
                200,
                json={
                    "sub": "identificador-estable",
                    "email": "aprendiz@ejemplo.com",
                    "email_verified": True,
                    "name": "Aprendiz de prueba",
                },
            )
        if peticion.url.path == "/revoke":
            return httpx.Response(503)
        return httpx.Response(404)

    cliente_httpx = httpx.AsyncClient
    monkeypatch.setattr(
        oauth_google.httpx,
        "AsyncClient",
        lambda **opciones: cliente_httpx(transport=httpx.MockTransport(responder), **opciones),
    )
    try:
        with TestClient(crear_aplicacion(configuracion, motor)) as cliente:
            inicio = cliente.get("/api/v1/autenticacion/google/iniciar", follow_redirects=False)
            estado = parse_qs(urlsplit(inicio.headers["location"]).query)["state"][0]
            respuesta = cliente.get(
                f"/api/v1/autenticacion/google/callback?code=identidad&state={estado}",
                follow_redirects=False,
            )
            assert respuesta.status_code == 303
            assert cliente.get("/api/v1/gmail/estado").json() == {
                "conectado": True,
                "correo": "aprendiz@ejemplo.com",
                "prueba_solicitada": False,
            }
            with cliente.app.state.fabrica_sesiones() as sesion:
                conexion = sesion.scalar(select(ConexionGmail))
                assert conexion is not None
                assert conexion.token_renovacion_cifrado != "renovacion-secreta"
                assert "renovacion-secreta" not in conexion.token_renovacion_cifrado

            inicio = cliente.get("/api/v1/autenticacion/google/iniciar", follow_redirects=False)
            estado = parse_qs(urlsplit(inicio.headers["location"]).query)["state"][0]
            assert (
                cliente.get(
                    f"/api/v1/autenticacion/google/callback?code=otra-vez&state={estado}",
                    follow_redirects=False,
                ).status_code
                == 303
            )
            assert cliente.get("/api/v1/gmail/estado").json()["conectado"] is True
            assert cliente.post("/api/v1/autenticacion/cerrar-sesion").status_code == 403
            csrf = cliente.get("/api/v1/autenticacion/csrf").json()["token"]
            assert (
                cliente.post(
                    "/api/v1/autenticacion/cerrar-sesion", headers={"X-CSRF-Token": csrf}
                ).status_code
                == 204
            )
            assert cliente.get("/api/v1/gmail/estado").status_code == 401
            with cliente.app.state.fabrica_sesiones() as sesion:
                assert sesion.scalar(select(ConexionGmail)) is None

            inicio = cliente.get("/api/v1/autenticacion/google/iniciar", follow_redirects=False)
            estado = parse_qs(urlsplit(inicio.headers["location"]).query)["state"][0]
            sin_permiso = cliente.get(
                f"/api/v1/autenticacion/google/callback?code=sin-permiso&state={estado}",
                follow_redirects=False,
            )
            assert sin_permiso.headers["location"] == "/error.html?tipo=gmail"
            assert cliente.get("/api/v1/gmail/estado").status_code == 401
    finally:
        motor.dispose()


def test_borrador_necesita_autorizacion(cliente: TestClient):
    assert cliente.post("/api/v1/campanas", json=solicitud_valida()).status_code == 401
    assert (
        cliente.post(
            "/api/v1/campanas",
            json=solicitud_valida(),
            headers={"Authorization": "Bearer incorrecta"},
        ).status_code
        == 401
    )


def test_borrador_persistente_y_exclusiones_normalizadas(cliente: TestClient):
    respuesta = cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso())
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["estado"] == "borrador"
    assert datos["plan_aplicado"] == "gratis"
    assert datos["limite_contactos"] == 8
    assert cliente.get("/api/v1/campanas", headers=acceso()).json()[0]["id"] == datos["id"]
    assert cliente.get("/api/v1/correos-excluidos", headers=acceso()).json() == [
        "empresa@ejemplo.com"
    ]
    iniciada = cliente.post(f"/api/v1/campanas/{datos['id']}/iniciar", headers=acceso())
    assert iniciada.status_code == 200
    assert iniciada.json()["estado"] == "en_cola"
    assert (
        cliente.post(f"/api/v1/campanas/{datos['id']}/iniciar", headers=acceso()).status_code
        == 409
    )
    assert cliente.get("/api/v1/historial", headers=acceso()).json() == []
    assert (
        cliente.delete(
            "/api/v1/correos-excluidos/empresa@ejemplo.com", headers=acceso()
        ).status_code
        == 204
    )


def test_un_usuario_no_puede_leer_una_campana_ajena(cliente: TestClient):
    with cliente.app.state.fabrica_sesiones() as sesion:
        otro = Usuario(identificador_externo="desarrollo:otro")
        sesion.add(otro)
        sesion.flush()
        ajena = Campana(
            usuario_id=otro.id,
            plan_aplicado="gratis",
            limite_contactos=8,
            modalidad="remoto",
            departamento="todos",
            ciudad="todas",
            antiguedad_dias=7,
        )
        sesion.add(ajena)
        sesion.commit()
        identificador = ajena.id
    assert cliente.get(f"/api/v1/campanas/{identificador}", headers=acceso()).status_code == 404
    assert (
        cliente.get(
            f"/api/v1/campanas/{identificador}/destinatarios", headers=acceso()
        ).status_code
        == 404
    )
    assert (
        cliente.put(
            f"/api/v1/campanas/{identificador}/seleccion",
            json={"destinatarios": []},
            headers=acceso(),
        ).status_code
        == 404
    )


def test_plan_gratis_muestra_nueve_ofertas_y_premium_todas(cliente: TestClient):
    primera = cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso()).json()
    with cliente.app.state.fabrica_sesiones() as sesion:
        campana = sesion.get(Campana, primera["id"])
        campana.estado = "esperando_confirmacion"
        sesion.add_all(
            Destinatario(
                campana_id=campana.id,
                nombre_empresa=f"Empresa {indice}",
                correo=f"empresa{indice}@ejemplo.com",
                motivo="Coincidencia de prueba",
                puntuacion=99 - indice,
            )
            for indice in range(12)
        )
        sesion.commit()
        usuario_id = campana.usuario_id

    gratis = cliente.get(f"/api/v1/campanas/{primera['id']}/destinatarios", headers=acceso())
    assert gratis.status_code == 200
    assert len(gratis.json()) == 9
    assert gratis.headers["X-DEBUPA-RESULTADOS-OCULTOS"] == "3"
    assert gratis.headers["X-DEBUPA-PLAN"] == "gratis"
    assert [oferta["puntuacion"] for oferta in gratis.json()] == list(range(99, 90, -1))
    seleccion_gratis = f"/api/v1/campanas/{primera['id']}/seleccion"
    visibles = [oferta["id"] for oferta in gratis.json()]
    with cliente.app.state.fabrica_sesiones() as sesion:
        oculto = sesion.scalar(
            select(Destinatario.id).where(
                Destinatario.campana_id == primera["id"],
                Destinatario.puntuacion == 90,
            )
        )
    assert (
        cliente.put(
            seleccion_gratis, json={"destinatarios": visibles}, headers=acceso()
        ).status_code
        == 422
    )
    assert (
        cliente.put(
            seleccion_gratis, json={"destinatarios": [oculto]}, headers=acceso()
        ).status_code
        == 422
    )
    assert cliente.put(
        seleccion_gratis, json={"destinatarios": visibles[:8]}, headers=acceso()
    ).json() == {
        "seleccionados": 8,
    }
    assert (
        cliente.get(f"/api/v1/campanas/{primera['id']}", headers=acceso()).json()[
            "seleccion_guardada"
        ]
        is True
    )
    assert (
        sum(
            oferta["seleccionado"]
            for oferta in cliente.get(
                f"/api/v1/campanas/{primera['id']}/destinatarios",
                headers=acceso(),
            ).json()
        )
        == 8
    )

    with cliente.app.state.fabrica_sesiones() as sesion:
        usuario = sesion.get(Usuario, usuario_id)
        usuario.plan = "premium"
        usuario.premium_hasta = datetime.now(timezone.utc) + timedelta(days=90)
        sesion.commit()
    segunda = cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso()).json()
    assert segunda["limite_contactos"] == 70
    with cliente.app.state.fabrica_sesiones() as sesion:
        campana = sesion.get(Campana, segunda["id"])
        campana.estado = "esperando_confirmacion"
        sesion.add_all(
            Destinatario(
                campana_id=campana.id,
                nombre_empresa=f"Premium {indice}",
                correo=f"premium{indice}@ejemplo.com",
                motivo="Coincidencia de prueba",
                puntuacion=99 - indice,
            )
            for indice in range(12)
        )
        sesion.commit()
    premium = cliente.get(f"/api/v1/campanas/{segunda['id']}/destinatarios", headers=acceso())
    assert premium.status_code == 200
    assert len(premium.json()) == 12
    assert premium.headers["X-DEBUPA-RESULTADOS-OCULTOS"] == "0"
    assert premium.headers["X-DEBUPA-PLAN"] == "premium"
    assert premium.headers["X-DEBUPA-LIMITE-CONTACTOS"] == "70"
    assert (
        len(
            cliente.get(f"/api/v1/campanas/{primera['id']}/destinatarios", headers=acceso()).json()
        )
        == 12
    )
    assert cliente.put(
        f"/api/v1/campanas/{segunda['id']}/seleccion",
        json={
            "destinatarios": [oferta["id"] for oferta in premium.json()],
        },
        headers=acceso(),
    ).json() == {"seleccionados": 12}
    assert (
        sum(
            oferta["seleccionado"]
            for oferta in cliente.get(
                f"/api/v1/campanas/{segunda['id']}/destinatarios",
                headers=acceso(),
            ).json()
        )
        == 12
    )


def test_trabajador_demo_persiste_resultados_sin_enviar(cliente: TestClient):
    primera = cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso()).json()
    sin_resultados = {
        **solicitud_valida(),
        "modalidad": "hibrido",
        "departamento": "Bogotá D. C.",
        "ciudad": "todas",
        "antiguedad_dias": 0,
    }
    segunda = cliente.post("/api/v1/campanas", json=sin_resultados, headers=acceso()).json()
    for campana in (primera, segunda):
        assert (
            cliente.post(f"/api/v1/campanas/{campana['id']}/iniciar", headers=acceso()).status_code
            == 200
        )
    assert (
        cliente.get(
            f"/api/v1/campanas/{primera['id']}/destinatarios", headers=acceso()
        ).status_code
        == 409
    )

    plazo = monotonic() + 12
    while monotonic() < plazo:
        estados = [
            cliente.get(f"/api/v1/campanas/{campana['id']}", headers=acceso()).json()["estado"]
            for campana in (primera, segunda)
        ]
        if estados == ["esperando_confirmacion", "esperando_confirmacion"]:
            break
        sleep(0.2)
    assert estados == ["esperando_confirmacion", "esperando_confirmacion"]
    resultados = cliente.get(f"/api/v1/campanas/{primera['id']}/destinatarios", headers=acceso())
    assert resultados.status_code == 200
    assert [destino["correo"] for destino in resultados.json()] == ["ejemplo@nexo.invalid"]
    assert resultados.json()[0]["estado"] == "ejemplo_no_enviado"
    assert (
        cliente.get(f"/api/v1/campanas/{segunda['id']}/destinatarios", headers=acceso()).json()
        == []
    )
    assert cliente.get("/api/v1/historial", headers=acceso()).json() == []


def test_ubicacion_valida_del_formulario(cliente: TestClient):
    solicitud = solicitud_valida()
    solicitud.update(modalidad="presencial", departamento="Antioquia", ciudad="Medellín")
    assert cliente.post("/api/v1/campanas", json=solicitud, headers=acceso()).status_code == 201


def test_plan_gratis_espera_despues_de_un_envio_y_premium_no(cliente: TestClient):
    primera = cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso()).json()
    with cliente.app.state.fabrica_sesiones() as sesion:
        usuario = sesion.scalar(
            select(Usuario).where(Usuario.identificador_externo == "desarrollo:aprendiz-local")
        )
        sesion.add(
            HistorialEnvio(
                usuario_id=usuario.id,
                campana_id=primera["id"],
                correo="empresa@ejemplo.com",
                enviado_en=datetime.now(timezone.utc),
            )
        )
        sesion.commit()
    disponibilidad = cliente.get("/api/v1/disponibilidad", headers=acceso()).json()
    assert disponibilidad["puede_buscar"] is False
    assert disponibilidad["proxima_fecha"] is not None
    assert (
        cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso()).status_code
        == 429
    )
    with cliente.app.state.fabrica_sesiones() as sesion:
        usuario = sesion.scalar(
            select(Usuario).where(Usuario.identificador_externo == "desarrollo:aprendiz-local")
        )
        usuario.plan = "premium"
        usuario.premium_hasta = datetime.now(timezone.utc) + timedelta(days=90)
        sesion.commit()
    assert (
        cliente.post("/api/v1/campanas", json=solicitud_valida(), headers=acceso()).status_code
        == 201
    )


@pytest.mark.parametrize(
    "departamento,ciudad",
    [
        ("Inventado", "todas"),
        ("Antioquia", "Cali"),
    ],
)
def test_ubicacion_fuera_del_formulario(cliente: TestClient, departamento: str, ciudad: str):
    solicitud = solicitud_valida()
    solicitud.update(modalidad="presencial", departamento=departamento, ciudad=ciudad)
    assert cliente.post("/api/v1/campanas", json=solicitud, headers=acceso()).status_code == 422


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("mayor_de_edad", False),
        ("acepta_tratamiento", False),
        ("antiguedad_dias", 45),
        ("departamento", "Antioquia"),
        ("plan", "premium"),
        ("clave_sgva", "contraseña-no-admitida"),
        ("cuerpo_correo", "texto-no-admitido"),
        ("correos_excluidos", [f"empresa{numero}@ejemplo.com" for numero in range(6)]),
    ],
)
def test_borrador_rechaza_datos_no_permitidos(cliente: TestClient, campo: str, valor):
    solicitud = solicitud_valida()
    solicitud[campo] = valor
    assert cliente.post("/api/v1/campanas", json=solicitud, headers=acceso()).status_code == 422
