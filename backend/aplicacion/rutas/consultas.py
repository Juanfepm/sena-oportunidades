"""Consultas de estado, planes, exclusiones e historial."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..base_datos import obtener_sesion
from ..configuracion import Configuracion
from ..dominio.estados import LIMITES_ARCHIVOS, LIMITES_CONTACTO, TARJETAS_RESUMEN, Plan
from ..esquemas import ResumenHistorial
from ..modelos import HistorialEnvio, Usuario
from ..seguridad import obtener_usuario_actual, verificar_csrf
from ..servicios.exclusiones import listar_exclusiones, quitar_exclusion


def crear_router(configuracion: Configuracion, cifrado_disponible: bool) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/salud")
    def salud(sesion: Session = Depends(obtener_sesion)) -> dict[str, str]:
        sesion.execute(select(1))
        return {"estado": "activo"}

    @router.get("/api/v1/capacidades")
    def capacidades() -> dict[str, bool]:
        gmail_configurado = bool(
            configuracion.google_cliente_id
            and configuracion.google_cliente_secreto
            and cifrado_disponible
        )
        return {
            "borradores": True,
            "historial_local": True,
            "cola_persistente": True,
            "trabajador_activo": True,
            "trabajador_demo": not configuracion.sgva_activo,
            "google_oauth": bool(
                configuracion.google_cliente_id
                and configuracion.google_cliente_secreto
                and cifrado_disponible
            ),
            "sgva": configuracion.sgva_activo,
            "gmail": gmail_configurado,
            "envio_campanas": gmail_configurado and configuracion.sgva_activo,
            "gmail_prueba": configuracion.entorno == "desarrollo" and gmail_configurado,
            "clasificacion_ia": bool(configuracion.sgva_activo and configuracion.gemini_clave),
            "comprobantes_nequi": cifrado_disponible,
        }

    @router.get("/api/v1/planes")
    def planes() -> dict[str, dict[str, int]]:
        return {
            plan: {
                "maximo_contactos": LIMITES_CONTACTO[plan],
                "maximo_archivos": LIMITES_ARCHIVOS[plan],
                "tarjetas_detalladas": TARJETAS_RESUMEN[plan],
            }
            for plan in Plan
        }

    @router.get("/api/v1/correos-excluidos", response_model=list[str])
    def correos_excluidos(
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[str]:
        return listar_exclusiones(sesion, usuario)

    @router.delete("/api/v1/correos-excluidos/{correo}", status_code=204)
    def retirar_exclusion(
        correo: str,
        _: None = Depends(verificar_csrf),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> None:
        if not quitar_exclusion(sesion, usuario, correo):
            raise HTTPException(404, "Correo excluido no encontrado.")

    @router.get("/api/v1/historial", response_model=list[ResumenHistorial])
    def historial(
        limite: int = Query(default=100, ge=1, le=100),
        usuario: Usuario = Depends(obtener_usuario_actual),
        sesion: Session = Depends(obtener_sesion),
    ) -> list[ResumenHistorial]:
        consulta = (
            select(HistorialEnvio)
            .where(
                HistorialEnvio.usuario_id == usuario.id,
                HistorialEnvio.estado == "enviado",
            )
            .order_by(HistorialEnvio.enviado_en.desc())
            .limit(limite)
        )
        return [ResumenHistorial.model_validate(envio) for envio in sesion.scalars(consulta)]

    return router
