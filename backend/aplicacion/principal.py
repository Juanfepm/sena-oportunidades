"""API preparada para integraciones futuras, sin simulaciones engañosas."""

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from starlette.responses import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from .base_datos import crear_motor, obtener_sesion
from .configuracion import Configuracion
from .dominio.estados import LIMITES_ARCHIVOS, LIMITES_CONTACTO, TARJETAS_RESUMEN, Plan
from .esquemas import ResumenCampana, ResumenHistorial, SolicitudBorrador
from .modelos import HistorialEnvio, Usuario
from .seguridad import obtener_usuario_actual
from .servicios.campanas import EsperaPlanGratis, consultar_campana, consultar_disponibilidad, crear_borrador, listar_borradores
from .servicios.exclusiones import listar_exclusiones, quitar_exclusion


def crear_aplicacion(configuracion: Configuracion | None = None, motor: Engine | None = None) -> FastAPI:
    configuracion = configuracion or Configuracion.desde_entorno()
    motor = motor or crear_motor(configuracion)
    api = FastAPI(title="API de DEBUPA", version="0.1.0")
    api.state.configuracion = configuracion
    api.state.fabrica_sesiones = sessionmaker(motor, expire_on_commit=False)

    @api.middleware("http")
    async def proteger_respuestas(peticion: Request, siguiente) -> Response:
        respuesta = await siguiente(peticion)
        respuesta.headers["Cache-Control"] = "no-store"
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        return respuesta

    @api.get("/api/v1/salud")
    def salud(sesion: Session = Depends(obtener_sesion)) -> dict[str, str]:
        sesion.execute(select(1))
        return {"estado": "activo"}

    @api.get("/api/v1/capacidades")
    def capacidades() -> dict[str, bool]:
        return {
            "borradores": True,
            "historial_local": True,
            "cola_persistente": True,
            "trabajador_activo": False,
            "google_oauth": False,
            "sgva": False,
            "gmail": False,
            "clasificacion_ia": False,
            "comprobantes_nequi": False,
        }

    @api.get("/api/v1/planes")
    def planes() -> dict[str, dict[str, int]]:
        return {
            plan: {"maximo_contactos": LIMITES_CONTACTO[plan], "maximo_archivos": LIMITES_ARCHIVOS[plan],
                   "tarjetas_detalladas": TARJETAS_RESUMEN[plan]}
            for plan in Plan
        }

    @api.get("/api/v1/disponibilidad")
    def disponibilidad(
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, bool | str | None]:
        proxima_fecha = consultar_disponibilidad(sesion, usuario)
        return {"puede_buscar": proxima_fecha is None, "proxima_fecha": proxima_fecha.isoformat() if proxima_fecha else None}

    @api.post("/api/v1/campanas", response_model=ResumenCampana, status_code=201)
    def nueva_campana(
        solicitud: SolicitudBorrador,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> ResumenCampana:
        try:
            return ResumenCampana.model_validate(crear_borrador(sesion, usuario, solicitud))
        except EsperaPlanGratis as espera:
            raise HTTPException(429, {"mensaje": "El plan gratis debe esperar un mes después del último envío.",
                                      "proxima_fecha": espera.fecha.isoformat()}) from espera

    @api.get("/api/v1/campanas", response_model=list[ResumenCampana])
    def campanas(
        limite: int = Query(default=50, ge=1, le=100),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[ResumenCampana]:
        return [ResumenCampana.model_validate(campana) for campana in listar_borradores(sesion, usuario, limite)]

    @api.get("/api/v1/campanas/{campana_id}", response_model=ResumenCampana)
    def campana(
        campana_id: str,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> ResumenCampana:
        encontrada = consultar_campana(sesion, usuario, campana_id)
        if encontrada is None:
            raise HTTPException(404, "Campaña no encontrada.")
        return ResumenCampana.model_validate(encontrada)

    @api.post("/api/v1/campanas/{campana_id}/iniciar")
    def iniciar_campana(
        campana_id: str,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> None:
        if consultar_campana(sesion, usuario, campana_id) is None:
            raise HTTPException(404, "Campaña no encontrada.")
        raise HTTPException(503, "El inicio requiere Google, SGVA, Gmail y almacenamiento temporal cifrado.")

    @api.get("/api/v1/correos-excluidos", response_model=list[str])
    def correos_excluidos(
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[str]:
        return listar_exclusiones(sesion, usuario)

    @api.delete("/api/v1/correos-excluidos/{correo}", status_code=204)
    def retirar_exclusion(
        correo: str,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> None:
        if not quitar_exclusion(sesion, usuario, correo):
            raise HTTPException(404, "Correo excluido no encontrado.")

    @api.get("/api/v1/historial", response_model=list[ResumenHistorial])
    def historial(
        limite: int = Query(default=100, ge=1, le=100),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[ResumenHistorial]:
        consulta = (
            select(HistorialEnvio)
            .where(HistorialEnvio.usuario_id == usuario.id)
            .order_by(HistorialEnvio.enviado_en.desc())
            .limit(limite)
        )
        return [ResumenHistorial.model_validate(envio) for envio in sesion.scalars(consulta)]

    return api


aplicacion = crear_aplicacion()
