"""Indicadores del panel calculados a partir de decisiones persistidas."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..dominio.estados import EstadoCampana, EstadoPago, Plan
from ..dominio.fechas import desplazar_meses
from ..modelos import Campana, PagoPremium, Usuario

PERIODOS_MESES = (1, 3, 6)


def _contar(sesion: Session, modelo: type, *condiciones: object) -> int:
    return sesion.scalar(select(func.count()).select_from(modelo).where(*condiciones)) or 0


def _inicio_mes(fecha: datetime) -> datetime:
    return fecha.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def obtener_estadisticas(sesion: Session) -> dict:
    ahora = datetime.now(timezone.utc)
    cuentas_google = Usuario.identificador_externo.like("google:%")
    usuarios = _contar(sesion, Usuario, cuentas_google)
    premium = _contar(
        sesion,
        Usuario,
        cuentas_google,
        Usuario.plan == Plan.PREMIUM,
        Usuario.premium_hasta > ahora,
    )

    def periodo(desde: datetime | None) -> dict[str, int]:
        pagos = [PagoPremium.estado == EstadoPago.APROBADO]
        campanas = [Campana.estado != EstadoCampana.BORRADOR]
        if desde is not None:
            pagos.append(PagoPremium.verificado_en >= desde)
            campanas.append(Campana.creado_en >= desde)
        ingresos = sesion.scalar(select(func.sum(PagoPremium.importe_cop)).where(*pagos)) or 0
        return {
            "ingresos_aprobados_cop": ingresos,
            "campanas": _contar(sesion, Campana, *campanas),
        }

    periodos = {"todo": periodo(None)}
    periodos.update(
        {str(meses): periodo(desplazar_meses(ahora, -meses)) for meses in PERIODOS_MESES}
    )

    inicio = _inicio_mes(desplazar_meses(ahora, -5))
    solicitudes = sesion.scalars(
        select(PagoPremium).where(
            (PagoPremium.creado_en >= inicio) | (PagoPremium.verificado_en >= inicio)
        )
    ).all()
    meses = []
    for indice in range(6):
        desde = desplazar_meses(inicio, indice)
        hasta = desplazar_meses(inicio, indice + 1)

        def dentro(fecha: datetime | None) -> bool:
            if fecha is None:
                return False
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            return desde <= fecha < hasta

        meses.append(
            {
                "mes": desde.strftime("%Y-%m"),
                "postuladas": sum(dentro(pago.creado_en) for pago in solicitudes),
                "aprobadas": sum(
                    pago.estado == EstadoPago.APROBADO and dentro(pago.verificado_en)
                    for pago in solicitudes
                ),
                "rechazadas": sum(
                    pago.estado == EstadoPago.RECHAZADO and dentro(pago.verificado_en)
                    for pago in solicitudes
                ),
            }
        )
    return {
        "usuarios": usuarios,
        "gratis": usuarios - premium,
        "premium": premium,
        "periodos": periodos,
        "evolucion_premium": meses,
    }
