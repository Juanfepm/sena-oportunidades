"""API del contenido temporal cifrado de una campaña."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..base_datos import obtener_sesion
from ..dominio.archivos import MAXIMO_BYTES
from ..dominio.estados import EstadoCampana, LIMITES_ARCHIVOS, Plan
from ..esquemas import ResumenContenidoTemporal, SolicitudContenidoTemporal
from ..modelos import Usuario
from ..seguridad import obtener_usuario_actual, verificar_csrf
from ..servicios.campanas import consultar_campana
from ..servicios.gmail import ClaveCifradoInvalida
from ..servicios.temporales import (
    ArchivoTemporal,
    CupoTemporalExcedido,
    eliminar_contenido,
    guardar_contenido,
    listar_contenidos,
    resumir_contenido,
)


router = APIRouter(prefix="/api/v1")


@router.get("/contenidos-temporales", response_model=list[ResumenContenidoTemporal])
def contenidos_temporales(
    request: Request,
    usuario: Usuario = Depends(obtener_usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> list[ResumenContenidoTemporal]:
    try:
        return listar_contenidos(sesion, usuario, request.app.state.configuracion.clave_cifrado)
    except ClaveCifradoInvalida as error:
        raise HTTPException(503, "No fue posible leer los borradores cifrados.") from error


@router.put("/campanas/{campana_id}/contenido", response_model=ResumenContenidoTemporal)
async def guardar_contenido_temporal(
    campana_id: str,
    request: Request,
    habilidades: str = Form(...),
    actividades_deseadas: str = Form(...),
    actividades_no_deseadas: str = Form(""),
    asunto: str = Form(...),
    cuerpo: str = Form(...),
    archivos: list[UploadFile] | None = File(default=None),
    _: None = Depends(verificar_csrf),
    usuario: Usuario = Depends(obtener_usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> ResumenContenidoTemporal:
    campana = consultar_campana(sesion, usuario, campana_id)
    if campana is None:
        raise HTTPException(404, "Campaña no encontrada.")
    if not request.app.state.cifrado_disponible:
        raise HTTPException(503, "El almacenamiento cifrado no está configurado.")
    campos = await request.form()
    permitidos = {"habilidades", "actividades_deseadas", "actividades_no_deseadas", "asunto", "cuerpo", "archivos"}
    if set(campos.keys()) - permitidos:
        raise HTTPException(422, "La solicitud contiene campos no permitidos.")
    if len(archivos or []) > LIMITES_ARCHIVOS[Plan(campana.plan_aplicado)]:
        raise HTTPException(422, "Tu plan no admite tantos adjuntos.")
    try:
        mensaje = SolicitudContenidoTemporal.model_validate({
            "habilidades": habilidades,
            "actividades_deseadas": actividades_deseadas,
            "actividades_no_deseadas": actividades_no_deseadas,
            "asunto": asunto,
            "cuerpo": cuerpo,
        })
        adjuntos = []
        for archivo in archivos or []:
            contenido = await archivo.read(MAXIMO_BYTES + 1)
            adjuntos.append(ArchivoTemporal(archivo.filename or "", archivo.content_type or "", contenido))
        return guardar_contenido(sesion, campana, mensaje, tuple(adjuntos), request.app.state.configuracion.clave_cifrado)
    except CupoTemporalExcedido as error:
        raise HTTPException(429, str(error)) from error
    except (ValidationError, ValueError) as error:
        raise HTTPException(422, "Revisa el texto y el formato de los archivos.") from error


@router.get("/campanas/{campana_id}/contenido", response_model=ResumenContenidoTemporal)
def estado_contenido_temporal(
    campana_id: str,
    request: Request,
    usuario: Usuario = Depends(obtener_usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> ResumenContenidoTemporal:
    campana = consultar_campana(sesion, usuario, campana_id)
    if campana is None:
        raise HTTPException(404, "Campaña no encontrada.")
    try:
        resumen = resumir_contenido(sesion, campana, request.app.state.configuracion.clave_cifrado)
    except ClaveCifradoInvalida as error:
        raise HTTPException(503, "No fue posible leer el contenido cifrado.") from error
    if resumen is None:
        raise HTTPException(404, "El contenido temporal venció o no existe.")
    return resumen


@router.delete("/campanas/{campana_id}/contenido", status_code=204)
def borrar_contenido_temporal(
    campana_id: str,
    _: None = Depends(verificar_csrf),
    usuario: Usuario = Depends(obtener_usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> None:
    campana = consultar_campana(sesion, usuario, campana_id)
    if campana is None:
        raise HTTPException(404, "Campaña no encontrada.")
    if campana.estado != EstadoCampana.BORRADOR:
        raise HTTPException(409, "No puedes borrar el contenido mientras la campaña está activa.")
    eliminar_contenido(sesion, campana)
