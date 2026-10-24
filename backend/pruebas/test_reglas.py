"""Casos críticos de selección, recontacto, cola y pagos."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base
from backend.aplicacion.dominio.contactos import evaluar_contacto, hace_seis_meses
from backend.aplicacion.dominio.archivos import ArchivoAdjunto, validar_adjuntos
from backend.aplicacion.dominio.estados import EstadoCampana, EstadoPago, Plan
from backend.aplicacion.dominio.ofertas import cumple_filtros
from backend.aplicacion.dominio.seleccion import Coincidencia, separar_coincidencias
from backend.aplicacion.integraciones.contratos import OfertaSGVA
from backend.aplicacion.modelos import Campana, NavegadorSGVA, PagoPremium, Usuario
from backend.aplicacion.servicios.cola import encolar, liberar, renovar_reserva, reservar_siguiente
from backend.aplicacion.servicios.pagos import verificar_pago


@pytest.fixture
def sesion():
    motor = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    with Session(motor, expire_on_commit=False) as sesion_actual:
        sesion_actual.add(NavegadorSGVA(id=1))
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
    assert not evaluar_contacto("empresa@ejemplo.com", {"EMPRESA@EJEMPLO.COM"}, None, True, hoy).permitido
    assert evaluar_contacto("empresa@ejemplo.com", set(), None, False, hoy).permitido


def test_seis_meses_respeta_finales_de_mes():
    assert hace_seis_meses(datetime(2026, 8, 31, tzinfo=timezone.utc)).date().isoformat() == "2026-02-28"


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
        Campana(usuario_id=usuario.id, plan_aplicado=Plan.GRATIS, limite_contactos=8,
                modalidad="remoto", departamento="todos", ciudad="todas", antiguedad_dias=7)
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
    with pytest.raises(ValueError):
        verificar_pago(sesion, pago, administrador, True)


def test_remoto_es_posibilidad_y_la_fecha_es_obligatoria():
    oferta = OfertaSGVA("Empresa", "empresa@ejemplo.com", None, "Contenido digital", "Antioquia", "Medellín", 4)
    assert cumple_filtros(oferta, "remoto", "todos", "todas", 7)
    assert not cumple_filtros(oferta, "presencial", "Bogotá D. C.", "todas", 7)
    assert not cumple_filtros(oferta, "hibrido", "Antioquia", "Cali", 7)
    sin_fecha = OfertaSGVA("Empresa", "empresa@ejemplo.com", None, "Contenido digital", "Antioquia", "Medellín", None)
    assert not cumple_filtros(sin_fecha, "remoto", "todos", "todas", 30)


def test_adjuntos_limita_cantidad_tamano_y_tipo():
    validar_adjuntos([ArchivoAdjunto("hoja-de-vida.pdf", "application/pdf", 2000)])
    with pytest.raises(ValueError):
        validar_adjuntos([ArchivoAdjunto("uno.pdf", "application/pdf", 1)] * 3)
    with pytest.raises(ValueError):
        validar_adjuntos([ArchivoAdjunto("hoja-de-vida.pdf", "application/pdf", 6 * 1024 * 1024)])
    with pytest.raises(ValueError):
        validar_adjuntos([ArchivoAdjunto("hoja-de-vida.exe", "application/pdf", 100)])
