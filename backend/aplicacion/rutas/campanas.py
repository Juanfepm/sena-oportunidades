"""Rutas de consulta, selección y envío de campañas."""

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from starlette.responses import Response

from ..base_datos import obtener_sesion
from ..configuracion import Configuracion
from ..dominio.estados import LIMITES_CONTACTO, EstadoCampana, Plan
from ..esquemas import (
    ResumenCampana,
    ResumenDestinatario,
    SolicitudAccesoSGVA,
    SolicitudBorrador,
)
from ..modelos import Campana, Destinatario, NavegadorSGVA, Usuario
from ..seguridad import obtener_usuario_actual, verificar_csrf
from ..servicios.campanas import (
    EsperaPlanGratis,
    consultar_campana,
    consultar_disponibilidad,
    crear_borrador,
    listar_borradores,
)
from ..servicios.campanas_envio import (
    cancelar_envio,
)
from ..servicios.cola import encolar
from ..servicios.planes import plan_disponible


def crear_router(api: FastAPI, configuracion: Configuracion) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/disponibilidad")
    def disponibilidad(
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, bool | str | None]:
        proxima_fecha = consultar_disponibilidad(sesion, usuario)
        return {
            "puede_buscar": proxima_fecha is None,
            "proxima_fecha": proxima_fecha.isoformat() if proxima_fecha else None,
        }

    @router.post("/api/v1/campanas", response_model=ResumenCampana, status_code=201)
    def nueva_campana(
        solicitud: SolicitudBorrador,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> ResumenCampana:
        try:
            return ResumenCampana.model_validate(crear_borrador(sesion, usuario, solicitud))
        except EsperaPlanGratis as espera:
            raise HTTPException(
                429,
                {
                    "mensaje": "El plan gratis debe esperar un mes después del último envío.",
                    "proxima_fecha": espera.fecha.isoformat(),
                },
            ) from espera

    @router.get("/api/v1/campanas", response_model=list[ResumenCampana])
    def campanas(
        limite: int = Query(default=50, ge=1, le=100),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[ResumenCampana]:
        return [
            ResumenCampana.model_validate(campana)
            for campana in listar_borradores(sesion, usuario, limite)
        ]

    @router.get("/api/v1/campanas/{campana_id}", response_model=ResumenCampana)
    def campana(
        campana_id: str,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> ResumenCampana:
        encontrada = consultar_campana(sesion, usuario, campana_id)
        if encontrada is None:
            raise HTTPException(404, "Campaña no encontrada.")
        return ResumenCampana.model_validate(encontrada)

    @router.get("/api/v1/campanas/{campana_id}/turno")
    def turno_campana(
        campana_id: str,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> dict[str, int | str]:
        encontrada = consultar_campana(sesion, usuario, campana_id)
        if encontrada is None:
            raise HTTPException(404, "Campaña no encontrada.")
        if encontrada.estado != EstadoCampana.EN_COLA:
            return {"estado": encontrada.estado, "personas_delante": 0}
        anteriores = (
            sesion.scalar(
                select(func.count())
                .select_from(Campana)
                .where(
                    Campana.estado == EstadoCampana.EN_COLA,
                    or_(
                        Campana.creado_en < encontrada.creado_en,
                        and_(
                            Campana.creado_en == encontrada.creado_en,
                            Campana.id < encontrada.id,
                        ),
                    ),
                )
            )
            or 0
        )
        ocupadas = (
            sesion.scalar(
                select(func.count())
                .select_from(Campana)
                .where(Campana.estado == EstadoCampana.CONSULTANDO)
            )
            or 0
        )
        return {"estado": encontrada.estado, "personas_delante": anteriores + ocupadas}

    @router.post("/api/v1/campanas/{campana_id}/cancelar", response_model=ResumenCampana)
    async def cancelar_campana(
        campana_id: str,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> ResumenCampana:
        campana = sesion.scalar(
            select(Campana)
            .where(
                Campana.id == campana_id,
                Campana.usuario_id == usuario.id,
            )
            .with_for_update()
        )
        if campana is None:
            raise HTTPException(404, "Campaña no encontrada.")
        if campana.estado in {EstadoCampana.EN_COLA, EstadoCampana.CONSULTANDO}:
            navegador = sesion.get(NavegadorSGVA, 1, with_for_update=True)
            if navegador is not None and navegador.campana_id == campana.id:
                navegador.campana_id = None
                navegador.reserva_hasta = None
            campana.estado = EstadoCampana.CANCELADA
            campana.etapa = "Consulta cancelada por el aprendiz"
            sesion.commit()
            tarea = api.state.tareas_sgva.get(campana_id)
            if tarea is not None:
                tarea.cancel()
        elif campana.estado == EstadoCampana.ENVIANDO:
            cancelar_envio(sesion, campana)
        elif campana.estado not in {
            EstadoCampana.CANCELADA,
            EstadoCampana.ERROR,
            EstadoCampana.INTERRUMPIDA,
        }:
            raise HTTPException(409, "Esta campaña ya terminó; consulta su resultado.")
        return ResumenCampana.model_validate(campana)

    @router.post("/api/v1/campanas/{campana_id}/iniciar")
    async def iniciar_campana(
        campana_id: str,
        acceso: SolicitudAccesoSGVA | None = None,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> ResumenCampana:
        campana = sesion.scalar(
            select(Campana)
            .where(Campana.id == campana_id, Campana.usuario_id == usuario.id)
            .with_for_update()
        )
        if campana is None:
            raise HTTPException(404, "Campaña no encontrada.")
        if campana.estado != EstadoCampana.BORRADOR:
            raise HTTPException(409, "La campaña ya fue iniciada o no puede volver a la cola.")
        if configuracion.sgva_activo:
            if acceso is None:
                raise HTTPException(
                    422,
                    "Introduce tu documento y contraseña de SGVA para esta consulta.",
                )
            if configuracion.gemini_clave and (not acceso.acepta_ia or acceso.perfil_ia is None):
                raise HTTPException(
                    422,
                    "Debes autorizar el análisis de IA y completar tu perfil para esta consulta.",
                )
            if acceso.acepta_ia and (not configuracion.gemini_clave or acceso.perfil_ia is None):
                raise HTTPException(
                    422, "La IA requiere tu perfil y una clave de servicio configurada."
                )
            if api.state.cola_sgva.full():
                raise HTTPException(429, "La cola de consultas está llena. Inténtalo después.")
            campana.modo_consulta = "sgva"
        encolar(sesion, campana)
        sesion.commit()
        if configuracion.sgva_activo:
            perfil = (
                acceso.perfil_ia.model_dump() if acceso.acepta_ia and acceso.perfil_ia else None
            )
            api.state.cola_sgva.put_nowait(
                (
                    campana.id,
                    acceso.numero_documento,
                    acceso.clave_sgva.get_secret_value(),
                    perfil,
                )
            )
        else:
            api.state.aviso_cola.set()
        return ResumenCampana.model_validate(campana)

    @router.get(
        "/api/v1/campanas/{campana_id}/destinatarios",
        response_model=list[ResumenDestinatario],
    )
    def destinatarios_campana(
        campana_id: str,
        respuesta: Response,
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[ResumenDestinatario]:
        campana = consultar_campana(sesion, usuario, campana_id)
        if campana is None:
            raise HTTPException(404, "Campaña no encontrada.")
        if campana.estado != EstadoCampana.ESPERANDO_CONFIRMACION:
            raise HTTPException(409, "Los resultados aún no están listos para revisión.")
        filtro = Destinatario.campana_id == campana_id
        consulta = (
            select(Destinatario)
            .where(filtro)
            .order_by(
                Destinatario.puntuacion.desc().nulls_last(),
                Destinatario.id,
            )
        )
        plan_actual = plan_disponible(usuario)
        respuesta.headers["X-DEBUPA-PLAN"] = plan_actual.value
        respuesta.headers["X-DEBUPA-LIMITE-CONTACTOS"] = str(LIMITES_CONTACTO[plan_actual])
        if plan_actual == Plan.GRATIS:
            total = (
                sesion.scalar(select(func.count()).select_from(Destinatario).where(filtro)) or 0
            )
            respuesta.headers["X-DEBUPA-RESULTADOS-OCULTOS"] = str(max(0, total - 9))
            consulta = consulta.limit(9)
        else:
            respuesta.headers["X-DEBUPA-RESULTADOS-OCULTOS"] = "0"
        return [
            ResumenDestinatario.model_validate(destino) for destino in sesion.scalars(consulta)
        ]

    return router
