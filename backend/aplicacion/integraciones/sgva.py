"""Lectura de solicitudes visibles para el aprendiz; nunca ejecuta «Aplicar»."""

import asyncio
import html
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from playwright.async_api import Error as ErrorPlaywright
from playwright.async_api import TimeoutError as TiempoAgotado
from playwright.async_api import async_playwright

from ..dominio.ofertas import OfertaSGVA
from .contratos import AccesoSGVARestringido, SGVAEntornoIncompatible, SGVANoDisponible

ORIGEN = "https://caprendizaje.sena.edu.co"
INGRESO = f"{ORIGEN}/sgva/SGVA_Diseno/pag/login.aspx"
BUSQUEDA = f"{ORIGEN}/sgva/Aprendices/Solicitudes/"
MAXIMO_OFERTAS = 70
ID_SOLICITUD = re.compile(r'data-id-solicitud=["\'](\d+)["\']')


def normalizar(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.casefold())
    limpio = re.sub(
        r"[^a-z0-9]", "", "".join(letra for letra in base if not unicodedata.combining(letra))
    )
    return {"valledelcauca": "valle", "bogota": "bogotadc"}.get(limpio, limpio)


def seleccionar_opcion(opciones: list[dict[str, str]], nombre: str) -> str:
    """Obtiene el valor publicado por SGVA, sin asumir códigos de DIVIPOLA."""
    buscado = normalizar(nombre)
    for opcion in opciones:
        if opcion["value"] != "0" and normalizar(opcion["label"]) == buscado:
            return opcion["value"]
    raise AccesoSGVARestringido("La ubicación elegida no aparece en SGVA.")


def dias_desde(fecha_texto: str, hoy: date | None = None) -> int | None:
    try:
        dia, mes, anio = map(int, fecha_texto.split("/"))
        return ((hoy or date.today()) - date(anio, mes, dia)).days
    except (ValueError, TypeError):
        return None


def filas_recientes(filas: list, hoy: date) -> list:
    """El resultado completo llega en una respuesta, aunque SGVA lo pagine de 20 en 20."""

    def antiguedad(fila: object) -> int:
        if not isinstance(fila, list) or len(fila) < 6:
            return 10**9
        dias = dias_desde(texto_plano(fila[5]), hoy)
        return dias if dias is not None else 10**9

    return sorted(reversed(filas), key=antiguedad)


async def _opciones(selector) -> list[dict[str, str]]:
    return await selector.locator("option").evaluate_all(
        "elementos => elementos.map(e => ({value: e.value, label: e.textContent.trim()}))"
    )


def mensaje_error_ingreso(texto: str) -> str:
    """Conserva solo los avisos de credenciales reconocidos de SGVA."""
    aviso = normalizar(texto)
    if "usuarionoseencuentraenelsistema" in aviso:
        return "El usuario no se encuentra en el sistema."
    if "usuarioocontrasenaincorrecta" in aviso:
        return "Usuario o contraseña incorrecta."
    return "SGVA no aceptó el acceso como aprendiz."


async def _ingresar(pagina, documento: str, clave: str) -> None:
    respuesta = await pagina.goto(INGRESO, wait_until="domcontentloaded", timeout=30000)
    if respuesta is None or respuesta.status >= 500:
        raise SGVANoDisponible("La página de acceso no respondió.")
    await pagina.locator("#aprendices").click()
    await pagina.locator("#tbLoginUsuario").fill(documento)
    await pagina.locator("#__tbPasswordUsuario").fill(clave)
    await pagina.locator("#ini_session_aprendiz").click()
    try:
        await pagina.wait_for_function(
            """() => {
            const aviso = document.querySelector('#LabelError')?.textContent?.trim();
            return Boolean(aviso) || location.pathname.toLowerCase()
                .includes('/sgva/aprendices/index')
                || location.href.startsWith('chrome-error://');
        }""",
            timeout=30000,
        )
    except TiempoAgotado as error:
        if "login.aspx" in pagina.url:
            raise AccesoSGVARestringido("SGVA no aceptó el acceso como aprendiz.") from error
        raise SGVANoDisponible("SGVA no terminó el inicio de sesión.") from error
    if "login.aspx" in pagina.url:
        aviso = await pagina.locator("#LabelError").text_content()
        raise AccesoSGVARestringido(mensaje_error_ingreso(aviso or ""))
    if pagina.url.startswith("chrome-error://"):
        # SGVA redirige a HTTP tras autenticarse y el puerto 80 no responde.
        # La cookie ya fue entregada; seguimos por la ruta HTTPS equivalente.
        await pagina.goto(
            f"{ORIGEN}/sgva/Aprendices/Index", wait_until="domcontentloaded", timeout=30000
        )
    if "/sgva/Aprendices/Index" not in pagina.url:
        raise AccesoSGVARestringido("SGVA no aceptó el acceso como aprendiz.")

    await asyncio.sleep(0.5)

    # Aviso recurrente observado en SGVA: aceptar datos prellenados y cancelar
    # la confirmación posterior. No se modifica ningún campo de contacto.
    actualizar = pagina.locator("#btnModalActAceptar")
    if await actualizar.is_visible():
        await actualizar.click()
        cancelar = pagina.get_by_role("button", name="Cancelar", exact=True)
        await cancelar.wait_for(state="visible", timeout=10000)
        await cancelar.click()


def texto_plano(valor: object) -> str:
    return html.unescape(re.sub(r"<[^>]*>", " ", str(valor or ""))).strip()


async def _detalle(pagina, identificador: str, nombre: str, hoy: date) -> OfertaSGVA:
    """Usa el mismo GET de solo lectura que abre el detalle del SGVA."""
    respuesta = await pagina.context.request.get(
        f"{ORIGEN}/sgva/Solicitudes/ConsultarSolicitud",
        params={"solicitudID": identificador},
        timeout=15000,
    )
    if respuesta.status != 200:
        raise SGVANoDisponible("SGVA no entregó el detalle de una solicitud.")
    try:
        fila = (await respuesta.json())["aaData"][0]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise SGVANoDisponible("SGVA devolvió un detalle incompleto.") from error
    return OfertaSGVA(
        nombre_empresa=nombre,
        correo=texto_plano(fila[9]) or None,
        telefono_original=texto_plano(fila[6]) or None,
        descripcion=f"Perfil: {texto_plano(fila[1])}\nFunciones: {texto_plano(fila[2])}",
        departamento=texto_plano(fila[3]),
        ciudad=texto_plano(fila[4]),
        dias_publicada=dias_desde(texto_plano(fila[10]), hoy),
    )


async def _buscar_departamento(
    pagina,
    departamento: str,
    ciudad: str,
    antiguedad: int,
    ofertas: list[OfertaSGVA],
    vistos: set[str],
    hoy: date,
    avance: Callable[[int, str], Awaitable[None]] | None = None,
    limite: int = MAXIMO_OFERTAS,
) -> None:
    selector_departamento = pagina.locator("#sel_departamento")
    opciones = await _opciones(selector_departamento)
    if departamento == "todos":
        # SGVA solo muestra todas las regiones después de una búsqueda concreta.
        primera = next((opcion["value"] for opcion in opciones if opcion["value"] != "0"), None)
        if primera is None:
            raise AccesoSGVARestringido("SGVA no ofreció departamentos para consultar.")
        await selector_departamento.select_option(primera)
        await _filas_busqueda(pagina)  # Búsqueda preparatoria; no se leen sus detalles.
        await selector_departamento.select_option("0")
    else:
        await selector_departamento.select_option(seleccionar_opcion(opciones, departamento))
    if ciudad != "todas":
        selector_ciudad = pagina.locator("#sel_ciudad")
        for _ in range(20):
            try:
                valor_ciudad = seleccionar_opcion(await _opciones(selector_ciudad), ciudad)
                break
            except AccesoSGVARestringido:
                await asyncio.sleep(0.25)
        else:
            raise AccesoSGVARestringido("El municipio elegido no aparece en SGVA.")
        await selector_ciudad.select_option(valor_ciudad)
    filas = await _filas_busqueda(pagina)
    if avance and not filas:
        await avance(min(70, 20 + len(ofertas)), f"Sin solicitudes recientes en {departamento}")
    # El JSON de SGVA contiene todas las páginas. Invertirlo equivale a entrar
    # por la última página; ordenar por fecha evita depender del orden de empates.
    for indice, fila in enumerate(filas_recientes(filas, hoy)):
        if avance and indice % 10 == 0:
            await avance(min(70, 20 + len(ofertas)), f"Revisando solicitudes de {departamento}")
        if not isinstance(fila, list) or len(fila) < 6:
            continue
        coincidencia = ID_SOLICITUD.search(str(fila[0]))
        if not coincidencia:
            continue
        identificador = coincidencia.group(1)
        if identificador in vistos:
            continue
        vistos.add(identificador)
        edad = dias_desde(texto_plano(fila[5]), hoy)
        if edad is None or edad < 0 or edad > antiguedad:
            continue
        oferta = await _detalle(pagina, identificador, texto_plano(fila[1]), hoy)
        ofertas.append(oferta)
        if len(ofertas) >= limite:
            return
        await asyncio.sleep(0.2)


async def _filas_busqueda(pagina) -> list:
    async with pagina.expect_response(
        lambda respuesta: "/sgva/Solicitudes/AprendizConsultarSolicitudesRequeridas"
        in respuesta.url,
        timeout=20000,
    ) as respuesta_pendiente:
        await pagina.locator("#btn_buscar_solicitud").click()
    respuesta_busqueda = await respuesta_pendiente.value
    if respuesta_busqueda.status != 200:
        raise SGVANoDisponible("SGVA rechazó la búsqueda de solicitudes.")
    try:
        datos = await respuesta_busqueda.json()
        filas = datos["aaData"]
    except (ValueError, KeyError, TypeError) as error:
        raise AccesoSGVARestringido("SGVA no entregó solicitudes para este aprendiz.") from error
    if not isinstance(filas, list):
        raise SGVANoDisponible("SGVA devolvió una lista de solicitudes inesperada.")
    total = datos.get("iTotalRecords", datos.get("recordsTotal"))
    if total is not None and int(total) > len(filas):
        raise SGVANoDisponible(
            "SGVA entregó solo una página de solicitudes; no se puede completar la consulta."
        )
    return filas


async def consultar_sgva(
    documento: str,
    clave: str,
    departamento: str,
    ciudad: str,
    antiguedad: int,
    avance: Callable[[int, str], Awaitable[None]] | None = None,
    limite: int = MAXIMO_OFERTAS,
) -> list[OfertaSGVA]:
    """Consulta una sesión aislada. La contraseña vive solo durante esta llamada."""
    ofertas: list[OfertaSGVA] = []
    if not 1 <= limite <= MAXIMO_OFERTAS:
        raise ValueError("El límite de consulta debe estar entre 1 y 70.")
    vistos: set[str] = set()
    hoy = datetime.now(ZoneInfo("America/Bogota")).date()
    ruta_local = Path(sys.prefix) / "ms-playwright"
    if ruta_local.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ruta_local))
    if sys.platform == "win32" and not isinstance(
        asyncio.get_running_loop(), asyncio.ProactorEventLoop
    ):
        raise SGVAEntornoIncompatible(
            "En Windows, inicia el servidor sin --reload para usar Playwright."
        )
    try:
        async with async_playwright() as playwright:
            navegador = await playwright.chromium.launch(headless=True)
            try:
                contexto = await navegador.new_context(accept_downloads=False)
                pagina = await contexto.new_page()
                await _ingresar(pagina, documento, clave)
                if avance:
                    await avance(15, "Acceso a SGVA confirmado")
                respuesta = await pagina.goto(BUSQUEDA, wait_until="load", timeout=30000)
                if (
                    respuesta is None
                    or respuesta.status >= 500
                    or urlparse(pagina.url).path != "/sgva/Aprendices/Solicitudes/"
                ):
                    raise AccesoSGVARestringido("No fue posible abrir Buscar empresa.")
                try:
                    await pagina.wait_for_load_state("networkidle", timeout=12000)
                except TiempoAgotado:
                    pass  # La búsqueda esperará su respuesta específica.
                await _buscar_departamento(
                    pagina, departamento, ciudad, antiguedad, ofertas, vistos, hoy, avance, limite
                )
                await contexto.close()
            finally:
                await navegador.close()
    except (AccesoSGVARestringido, SGVANoDisponible):
        raise
    except (ErrorPlaywright, OSError) as error:
        raise SGVANoDisponible("SGVA interrumpió la consulta.") from error
    return ofertas
