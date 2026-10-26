"""Pago manual: aislamiento del comprobante, autorización y vigencia."""

from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.aplicacion.base_datos import Base, obtener_sesion
from backend.aplicacion.configuracion import Configuracion
from backend.aplicacion.dominio.estados import Plan
from backend.aplicacion.integraciones.cifrado import cifrar_token
from backend.aplicacion.modelos import ConexionGmail, NavegadorSGVA, PagoPremium, Usuario
from backend.aplicacion.principal import crear_aplicacion
from backend.aplicacion.seguridad import actualizar_plan_vencido, obtener_usuario_actual
from backend.aplicacion.servicios.pagos import sumar_tres_meses


def test_tres_meses_son_meses_calendario() -> None:
    assert sumar_tres_meses(datetime(2026, 11, 30, tzinfo=timezone.utc)) == datetime(
        2027, 2, 28, tzinfo=timezone.utc
    )


def test_pago_privado_aprobacion_y_aviso(monkeypatch) -> None:
    from backend.aplicacion.servicios import avisos_premium

    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    clave = Fernet.generate_key().decode()
    configuracion = Configuracion(
        entorno="pruebas",
        base_datos="sqlite://",
        clave_cifrado=clave,
        secreto_sesion="secreto-local-para-revisar-pagos-premium-2026",
        correo_administrador="debupawebapp@gmail.com",
    )
    aplicacion = crear_aplicacion(configuracion, motor)
    with aplicacion.state.fabrica_sesiones() as sesion:
        aprendiz = Usuario(
            identificador_externo="google:aprendiz", correo_google="aprendiz@ejemplo.com"
        )
        admin = Usuario(
            identificador_externo="google:administrador",
            correo_google="debupawebapp@gmail.com",
            es_administrador=True,
        )
        sesion.add_all([aprendiz, admin, NavegadorSGVA(id=1)])
        sesion.flush()
        sesion.add(
            ConexionGmail(
                usuario_id=admin.id,
                correo_google=admin.correo_google,
                token_renovacion_cifrado=cifrar_token("token-de-prueba", clave),
                permisos="https://www.googleapis.com/auth/gmail.send",
            )
        )
        sesion.commit()
        aprendiz_id, admin_id = aprendiz.id, admin.id

    identidad = {"id": aprendiz_id}

    def usuario_ficticio(sesion=Depends(obtener_sesion)):
        return sesion.get(Usuario, identidad["id"])

    aplicacion.dependency_overrides[obtener_usuario_actual] = usuario_ficticio
    enviados = []

    async def envio_ficticio(_configuracion, _token, remitente, destinatario, *_args):
        enviados.append((remitente, destinatario))
        return "mensaje-confirmado"

    monkeypatch.setattr(avisos_premium, "enviar_gmail", envio_ficticio)
    captura = b"\x89PNG\r\n\x1a\n" + b"captura-ficticia" + b"IEND\xaeB`\x82"
    with TestClient(aplicacion) as cliente:
        sin_aceptar = cliente.post(
            "/api/v1/pagos-premium",
            data={"acepta_condiciones": "false"},
            files={"comprobante": ("pago.png", captura, "image/png")},
        )
        assert sin_aceptar.status_code == 422
        solicitud = cliente.post(
            "/api/v1/pagos-premium",
            data={"acepta_condiciones": "true"},
            files={"comprobante": ("pago.png", captura, "image/png")},
        )
        assert solicitud.status_code == 201
        pago_id = solicitud.json()["id"]
        assert cliente.get("/api/v1/administracion/resumen").status_code == 403
        with aplicacion.state.fabrica_sesiones() as sesion:
            pago = sesion.get(PagoPremium, pago_id)
            assert captura not in pago.comprobante_cifrado
            assert pago.referencia_comprobante != "pago.png"
        identidad["id"] = admin_id
        resumen = cliente.get("/api/v1/administracion/resumen").json()
        assert (resumen["usuarios"], resumen["gratis"], resumen["premium"]) == (2, 2, 0)
        assert resumen["correo_servicio_conectado"] is True
        assert len(resumen["solicitudes"]) == 1
        assert resumen["periodos"]["todo"]["ingresos_aprobados_cop"] == 0
        assert resumen["evolucion_premium"][-1]["postuladas"] == 1
        comprobante = cliente.get(f"/api/v1/administracion/pagos/{pago_id}/comprobante")
        assert comprobante.content == captura
        decision = cliente.post(
            f"/api/v1/administracion/pagos/{pago_id}/decision", json={"aprobar": True}
        )
        assert decision.status_code == 200
        assert decision.json() == {"estado": "aprobado", "notificacion_estado": "enviado"}
        assert enviados == [("debupawebapp@gmail.com", "aprendiz@ejemplo.com")]
        resumen_actualizado = cliente.get("/api/v1/administracion/resumen").json()
        assert resumen_actualizado["periodos"]["todo"]["ingresos_aprobados_cop"] == 7500
        assert resumen_actualizado["evolucion_premium"][-1]["aprobadas"] == 1
        assert (
            cliente.get(f"/api/v1/administracion/pagos/{pago_id}/comprobante").status_code == 404
        )
        assert (
            cliente.post(
                f"/api/v1/administracion/pagos/{pago_id}/decision", json={"aprobar": True}
            ).status_code
            == 409
        )
        with aplicacion.state.fabrica_sesiones() as sesion:
            usuario = sesion.get(Usuario, aprendiz_id)
            pago = sesion.get(PagoPremium, pago_id)
            assert usuario.plan == Plan.PREMIUM
            assert usuario.premium_hasta.replace(tzinfo=timezone.utc) > datetime.now(
                timezone.utc
            ) + timedelta(days=80)
            assert pago.comprobante_cifrado is None
        identidad["id"] = aprendiz_id
        estado = cliente.get("/api/v1/pagos-premium/estado").json()
        assert estado["plan"] == "premium"
        with aplicacion.state.fabrica_sesiones() as sesion:
            usuario = sesion.get(Usuario, aprendiz_id)
            usuario.premium_hasta = datetime.now(timezone.utc) - timedelta(days=1)
            sesion.commit()
            actualizar_plan_vencido(sesion, usuario)
        assert cliente.get("/api/v1/pagos-premium/estado").json()["plan"] == "gratis"
    motor.dispose()
