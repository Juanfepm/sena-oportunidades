"""Casos críticos de selección, recontacto, cola y pagos."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base
from backend.aplicacion.consola_navegadores import main as controlar_navegadores
from backend.aplicacion.dominio.archivos import ArchivoAdjunto, validar_adjuntos
from backend.aplicacion.dominio.contactos import evaluar_contacto, hace_seis_meses
from backend.aplicacion.dominio.disponibilidad import proxima_busqueda
from backend.aplicacion.dominio.estados import EstadoCampana, EstadoPago, Plan
from backend.aplicacion.dominio.ofertas import cumple_filtros
from backend.aplicacion.dominio.seleccion import Coincidencia, separar_coincidencias
from backend.aplicacion.dominio.ubicaciones import MUNICIPIOS_POR_DEPARTAMENTO, RUTA_CATALOGO
from backend.aplicacion.integraciones.contratos import OfertaSGVA
from backend.aplicacion.modelos import Campana, HistorialEnvio, NavegadorSGVA, PagoPremium, Usuario
from backend.aplicacion.servicios.campanas import consultar_disponibilidad
from backend.aplicacion.servicios.cola import encolar, liberar, renovar_reserva, reservar_siguiente
from backend.aplicacion.servicios.pagos import verificar_pago
from backend.aplicacion.servicios.planes import plan_disponible
from backend.aplicacion.servicios.trabajador_demo import recuperar_reserva_vencida
from backend.aplicacion.servicios.trabajador_sgva import interrumpir_sin_credenciales


@pytest.fixture
def sesion():
    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    with Session(motor, expire_on_commit=False) as sesion_actual:
        sesion_actual.add_all([NavegadorSGVA(id=1), NavegadorSGVA(id=2, habilitado=False)])
        sesion_actual.commit()
        yield sesion_actual
    motor.dispose()


def test_recontacto_solo_despues_de_seis_meses_y_con_permiso():
    hoy = datetime(2026, 10, 23, tzinfo=timezone.utc)
    reciente = hoy - timedelta(days=10)
    antiguo = datetime(2026, 4, 23, tzinfo=timezone.utc)

    assert not evaluar_contacto("empresa@ejemplo.com", set(), reciente, True, hoy).permitido
    assert not evaluar_contacto("empresa@ejemplo.com", set(), antiguo, False, hoy).permitido
    assert evaluar_contacto("empresa@ejemplo.com", set(), antiguo, True, hoy).permitido
    assert not evaluar_contacto(
        "empresa@ejemplo.com", {"EMPRESA@EJEMPLO.COM"}, None, True, hoy
    ).permitido
    assert evaluar_contacto("empresa@ejemplo.com", set(), None, False, hoy).permitido


def test_seis_meses_respeta_finales_de_mes():
    assert (
        hace_seis_meses(datetime(2026, 8, 31, tzinfo=timezone.utc)).date().isoformat()
        == "2026-02-28"
    )


def test_cuenta_administradora_puede_repetir_campanas(sesion: Session):
    usuario = Usuario(
        identificador_externo="google:servicio",
        correo_google="debupawebapp@gmail.com",
        es_administrador=True,
    )
    sesion.add(usuario)
    sesion.flush()
    campana = Campana(
        usuario_id=usuario.id,
        plan_aplicado=Plan.PREMIUM,
        limite_contactos=70,
        modalidad="remoto",
        departamento="todos",
        ciudad="todas",
        antiguedad_dias=7,
    )
    sesion.add(campana)
    sesion.flush()
    sesion.add(
        HistorialEnvio(
            usuario_id=usuario.id,
            campana_id=campana.id,
            correo="empresa@ejemplo.com",
            estado="enviado",
            enviado_en=datetime.now(timezone.utc),
        )
    )
    sesion.commit()
    assert plan_disponible(usuario) == Plan.PREMIUM
    assert consultar_disponibilidad(sesion, usuario) is None
    usuario.correo_google = "otra@ejemplo.com"
    assert plan_disponible(usuario) == Plan.GRATIS
    assert consultar_disponibilidad(sesion, usuario) is not None


def test_seleccion_no_rellena_cupos_con_coincidencias_dudosas():
    ofertas = [
        Coincidencia(f"empresa{numero}@ejemplo.com", 90 - numero, "Funciones afines", True)
        for numero in range(10)
    ]
    ofertas += [Coincidencia("posible@ejemplo.com", 95, "Remoto no confirmado", False)]
    gratis = separar_coincidencias(ofertas, Plan.GRATIS)
    premium = separar_coincidencias(ofertas, Plan.PREMIUM)

    assert len(gratis.alta) == 8
    assert len(premium.alta) == 10
    assert [oferta.correo for oferta in gratis.por_revisar] == ["posible@ejemplo.com"]


def test_cola_reserva_un_solo_navegador(sesion: Session):
    usuario = Usuario(identificador_externo="desarrollo:cola")
    sesion.add(usuario)
    sesion.flush()
    campanas = [
        Campana(
            usuario_id=usuario.id,
            plan_aplicado=Plan.GRATIS,
            limite_contactos=8,
            modalidad="remoto",
            departamento="todos",
            ciudad="todas",
            antiguedad_dias=7,
        )
        for _ in range(2)
    ]
    sesion.add_all(campanas)
    sesion.flush()
    for campana in campanas:
        encolar(sesion, campana)
    sesion.commit()

    ahora = datetime(2026, 10, 23, tzinfo=timezone.utc)
    primera = reservar_siguiente(sesion, ahora)
    assert primera is not None
    assert reservar_siguiente(sesion, ahora) is None
    renovar_reserva(sesion, primera, ahora + timedelta(minutes=10))
    assert reservar_siguiente(sesion, ahora + timedelta(minutes=16)) is None
    liberar(sesion, primera, EstadoCampana.ESPERANDO_CONFIRMACION)
    segunda = reservar_siguiente(sesion, ahora)
    assert segunda is not None and segunda.id != primera.id


def test_demostracion_reencola_reserva_vencida(sesion: Session):
    usuario = Usuario(identificador_externo="desarrollo:recuperacion")
    sesion.add(usuario)
    sesion.flush()
    campana = Campana(
        usuario_id=usuario.id,
        plan_aplicado=Plan.GRATIS,
        limite_contactos=8,
        modalidad="remoto",
        departamento="todos",
        ciudad="todas",
        antiguedad_dias=7,
        estado=EstadoCampana.CONSULTANDO,
    )
    sesion.add(campana)
    sesion.flush()
    ahora = datetime(2026, 10, 23, tzinfo=timezone.utc)
    navegador = sesion.get(NavegadorSGVA, 1)
    navegador.campana_id = campana.id
    navegador.reserva_hasta = ahora - timedelta(seconds=1)
    sesion.commit()

    recuperar_reserva_vencida(sesion, ahora)
    assert campana.estado == EstadoCampana.EN_COLA
    assert navegador.campana_id is None
    assert navegador.reserva_hasta is None


def test_segundo_navegador_solo_trabaja_al_activarse(sesion: Session):
    usuario = Usuario(identificador_externo="desarrollo:dos-navegadores")
    sesion.add(usuario)
    sesion.flush()
    campanas = [
        Campana(
            usuario_id=usuario.id,
            plan_aplicado=Plan.GRATIS,
            limite_contactos=8,
            modalidad="remoto",
            departamento="todos",
            ciudad="todas",
            antiguedad_dias=7,
        )
        for _ in range(3)
    ]
    sesion.add_all(campanas)
    sesion.flush()
    for campana in campanas:
        encolar(sesion, campana)
    sesion.commit()

    ahora = datetime(2026, 10, 29, tzinfo=timezone.utc)
    primera = reservar_siguiente(sesion, ahora)
    assert primera is not None
    assert reservar_siguiente(sesion, ahora, navegador_id=2) is None

    segundo = sesion.get(NavegadorSGVA, 2)
    segundo.habilitado = True
    sesion.commit()
    otra = reservar_siguiente(sesion, ahora, navegador_id=2)
    assert otra is not None and otra.id != primera.id
    renovar_reserva(sesion, otra, ahora + timedelta(minutes=1))
    segundo.apagado_pendiente = True
    sesion.commit()
    assert segundo.habilitado
    assert reservar_siguiente(sesion, ahora, navegador_id=2) is None
    renovar_reserva(sesion, otra, ahora + timedelta(minutes=2))
    liberar(sesion, otra, EstadoCampana.ESPERANDO_CONFIRMACION)
    assert not segundo.habilitado
    assert not segundo.apagado_pendiente
    assert reservar_siguiente(sesion, ahora, navegador_id=2) is None
    assert reservar_siguiente(sesion, ahora) is None


def test_consola_activa_y_desactiva_segundo_navegador(tmp_path, monkeypatch):
    ruta = tmp_path / "navegadores.sqlite3"
    direccion = f"sqlite:///{ruta.as_posix()}"
    motor = create_engine(direccion)
    Base.metadata.create_all(motor)
    with Session(motor) as sesion:
        sesion.add_all([NavegadorSGVA(id=1), NavegadorSGVA(id=2, habilitado=False)])
        sesion.commit()
    motor.dispose()
    monkeypatch.setenv("DEBUPA_BASE_DATOS", direccion)

    for accion, esperado in (("activar", True), ("desactivar", False)):
        monkeypatch.setattr(sys, "argv", ["consola_navegadores", accion])
        controlar_navegadores()
        with Session(create_engine(direccion)) as sesion:
            assert sesion.get(NavegadorSGVA, 2).habilitado is esperado


def test_consola_difiere_apagado_hasta_terminar_consulta(tmp_path, monkeypatch, capsys):
    ruta = tmp_path / "apagado-diferido.sqlite3"
    direccion = f"sqlite:///{ruta.as_posix()}"
    motor = create_engine(direccion)
    Base.metadata.create_all(motor)
    with Session(motor) as sesion:
        usuario = Usuario(identificador_externo="desarrollo:apagado-diferido")
        sesion.add(usuario)
        sesion.flush()
        campana = Campana(
            usuario_id=usuario.id,
            plan_aplicado=Plan.GRATIS,
            limite_contactos=8,
            modalidad="remoto",
            departamento="todos",
            ciudad="todas",
            antiguedad_dias=7,
            estado=EstadoCampana.CONSULTANDO,
        )
        sesion.add(campana)
        sesion.flush()
        sesion.add_all(
            [
                NavegadorSGVA(id=1),
                NavegadorSGVA(
                    id=2,
                    habilitado=True,
                    campana_id=campana.id,
                    reserva_hasta=datetime.now(timezone.utc) + timedelta(minutes=15),
                ),
            ]
        )
        sesion.commit()
        campana_id = campana.id
    monkeypatch.setenv("DEBUPA_BASE_DATOS", direccion)

    monkeypatch.setattr(sys, "argv", ["consola_navegadores", "desactivar"])
    controlar_navegadores()
    assert "apagado pendiente" in capsys.readouterr().out
    with Session(motor) as sesion:
        navegador = sesion.get(NavegadorSGVA, 2)
        assert navegador.habilitado and navegador.apagado_pendiente
        campana = sesion.get(Campana, campana_id)
        renovar_reserva(sesion, campana, datetime.now(timezone.utc))
        sesion.commit()

    monkeypatch.setattr(sys, "argv", ["consola_navegadores", "activar"])
    controlar_navegadores()
    with Session(motor) as sesion:
        assert not sesion.get(NavegadorSGVA, 2).apagado_pendiente
    monkeypatch.setattr(sys, "argv", ["consola_navegadores", "desactivar"])
    controlar_navegadores()
    with Session(motor) as sesion:
        campana = sesion.get(Campana, campana_id)
        liberar(sesion, campana, EstadoCampana.ESPERANDO_CONFIRMACION)
        sesion.commit()
    monkeypatch.setattr(sys, "argv", ["consola_navegadores", "estado"])
    controlar_navegadores()
    assert "Segundo navegador SGVA: apagado." in capsys.readouterr().out
    motor.dispose()


def test_reinicio_completa_apagado_pendiente(sesion: Session):
    usuario = Usuario(identificador_externo="desarrollo:reinicio-pendiente")
    sesion.add(usuario)
    sesion.flush()
    campana = Campana(
        usuario_id=usuario.id,
        plan_aplicado=Plan.GRATIS,
        limite_contactos=8,
        modalidad="remoto",
        departamento="todos",
        ciudad="todas",
        antiguedad_dias=7,
        estado=EstadoCampana.CONSULTANDO,
    )
    sesion.add(campana)
    sesion.flush()
    navegador = sesion.get(NavegadorSGVA, 2)
    navegador.habilitado = True
    navegador.apagado_pendiente = True
    navegador.campana_id = campana.id
    sesion.commit()

    interrumpir_sin_credenciales(sesion)
    assert not navegador.habilitado
    assert not navegador.apagado_pendiente
    assert navegador.campana_id is None
    sesion.refresh(campana)
    assert campana.estado == EstadoCampana.INTERRUMPIDA


def test_pago_requiere_administrador_y_revision_pendiente(sesion: Session):
    aprendiz = Usuario(identificador_externo="desarrollo:aprendiz")
    administrador = Usuario(identificador_externo="desarrollo:admin", es_administrador=True)
    sesion.add_all([aprendiz, administrador])
    sesion.flush()
    pago = PagoPremium(usuario_id=aprendiz.id, referencia_comprobante="privado/comprobante-prueba")
    sesion.add(pago)
    sesion.flush()

    with pytest.raises(PermissionError):
        verificar_pago(sesion, pago, aprendiz, True)
    assert aprendiz.plan == Plan.GRATIS
    verificar_pago(sesion, pago, administrador, True)
    assert pago.estado == EstadoPago.APROBADO
    assert aprendiz.plan == Plan.PREMIUM
    assert aprendiz.premium_hasta is not None
    with pytest.raises(ValueError):
        verificar_pago(sesion, pago, administrador, True)


def test_rechazar_pago_no_activa_premium(sesion: Session):
    aprendiz = Usuario(identificador_externo="desarrollo:aprendiz-rechazado")
    administrador = Usuario(
        identificador_externo="desarrollo:admin-rechazado", es_administrador=True
    )
    sesion.add_all([aprendiz, administrador])
    sesion.flush()
    pago = PagoPremium(
        usuario_id=aprendiz.id,
        referencia_comprobante="comprobante-de-prueba",
        comprobante_cifrado=b"contenido-de-prueba",
    )
    sesion.add(pago)
    sesion.flush()
    verificar_pago(sesion, pago, administrador, False)
    assert pago.estado == EstadoPago.RECHAZADO
    assert pago.comprobante_cifrado is None
    assert aprendiz.plan == Plan.GRATIS


def test_remoto_es_posibilidad_y_la_fecha_es_obligatoria():
    oferta = OfertaSGVA(
        "Empresa", "empresa@ejemplo.com", None, "Contenido digital", "Antioquia", "Medellín", 4
    )
    assert cumple_filtros(oferta, "remoto", "todos", "todas", 7)
    assert not cumple_filtros(oferta, "presencial", "Bogotá D. C.", "todas", 7)
    assert not cumple_filtros(oferta, "hibrido", "Antioquia", "Cali", 7)
    sin_fecha = OfertaSGVA(
        "Empresa", "empresa@ejemplo.com", None, "Contenido digital", "Antioquia", "Medellín", None
    )
    assert not cumple_filtros(sin_fecha, "remoto", "todos", "todas", 30)


def test_adjuntos_limita_cantidad_tamano_y_tipo():
    validar_adjuntos([ArchivoAdjunto("hoja-de-vida.pdf", "application/pdf", 2000)])
    dos_archivos = [
        ArchivoAdjunto("uno.pdf", "application/pdf", 100),
        ArchivoAdjunto("dos.pdf", "application/pdf", 100),
    ]
    with pytest.raises(ValueError):
        validar_adjuntos(dos_archivos, Plan.GRATIS)
    validar_adjuntos(dos_archivos, Plan.PREMIUM)
    with pytest.raises(ValueError):
        validar_adjuntos([ArchivoAdjunto("uno.pdf", "application/pdf", 1)] * 3)
    with pytest.raises(ValueError):
        validar_adjuntos([ArchivoAdjunto("hoja-de-vida.pdf", "application/pdf", 6 * 1024 * 1024)])
    with pytest.raises(ValueError):
        validar_adjuntos([ArchivoAdjunto("hoja-de-vida.exe", "application/pdf", 100)])
    with pytest.raises(ValueError):
        validar_adjuntos([ArchivoAdjunto("..\\hoja-de-vida.pdf", "application/pdf", 100)])


def test_espera_gratis_un_mes_calendario_y_premium_sin_espera():
    envio = datetime(2026, 1, 31, 5, tzinfo=timezone.utc)
    ahora = datetime(2026, 2, 27, tzinfo=timezone.utc)
    assert proxima_busqueda(Plan.GRATIS, envio, ahora) == datetime(
        2026, 2, 28, 5, tzinfo=timezone.utc
    )
    assert (
        proxima_busqueda(Plan.GRATIS, envio, datetime(2026, 2, 28, 5, tzinfo=timezone.utc)) is None
    )
    assert proxima_busqueda(Plan.PREMIUM, envio, ahora) is None
    assert proxima_busqueda(Plan.GRATIS, None, ahora) is None


def test_catalogo_municipal_compartido_con_frontend():
    ruta_frontend = Path(__file__).resolve().parents[2] / "frontend" / "datos" / "municipios.json"
    assert RUTA_CATALOGO.read_bytes() == ruta_frontend.read_bytes()
    assert len(MUNICIPIOS_POR_DEPARTAMENTO) == 33
    assert 80 <= sum(map(len, MUNICIPIOS_POR_DEPARTAMENTO.values())) <= 120
    assert "Medellín" in MUNICIPIOS_POR_DEPARTAMENTO["Antioquia"]
    assert "Abejorral" not in MUNICIPIOS_POR_DEPARTAMENTO["Antioquia"]
