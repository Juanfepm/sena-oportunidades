"""La IA recibe funciones e intereses, sin datos de contacto."""

import asyncio
import json

from backend.aplicacion.integraciones import ia
from backend.aplicacion.integraciones.contratos import OfertaSGVA


def test_clasificacion_oculta_contactos_y_valida_resultado(monkeypatch) -> None:
    peticiones = []

    class Respuesta:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "evaluaciones": [
                                                {
                                                    "id": 0,
                                                    "puntuacion": 86,
                                                    "motivo": "Coinciden tareas de análisis.",
                                                    "modalidad": "posible",
                                                },
                                            ]
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

    class Cliente:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, headers, json):
            peticiones.append((url, headers, json))
            return Respuesta()

    async def pausa(_):
        return None

    monkeypatch.setattr(ia.httpx, "AsyncClient", Cliente)
    monkeypatch.setattr(ia.asyncio, "sleep", pausa)
    oferta = OfertaSGVA(
        "Empresa Privada",
        "empresa@correo.com",
        "3001234567",
        "Analizar datos. Contacto: empresa@correo.com, 3001234567",
        "Bogotá",
        "Bogotá",
        2,
    )
    perfil = {
        "habilidades": "Análisis en Excel y Python",
        "actividades_deseadas": "Analizar datos",
        "actividades_no_deseadas": "Ventas",
    }
    evaluaciones = asyncio.run(
        ia.clasificar_ofertas("clave-de-prueba", perfil, "remoto", [oferta])
    )
    contenido = json.dumps(peticiones[0][2], ensure_ascii=False)
    assert "Empresa Privada" not in contenido
    assert "empresa@correo.com" not in contenido
    assert "3001234567" not in contenido
    assert peticiones[0][1] == {"x-goog-api-key": "clave-de-prueba"}
    assert evaluaciones[0].puntuacion == 86
    assert evaluaciones[0].modalidad == "posible"


def test_saturacion_reintenta_y_cambia_de_modelo(monkeypatch) -> None:
    urls = []

    class Respuesta:
        def __init__(self, estado: int):
            self.status_code = estado

        def json(self):
            if self.status_code == 503:
                return {"error": {"status": "UNAVAILABLE"}}
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "evaluaciones": [
                                                {
                                                    "id": 0,
                                                    "puntuacion": 90,
                                                    "motivo": "Coinciden las funciones.",
                                                    "modalidad": "posible",
                                                }
                                            ]
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

    class Cliente:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, headers, json):
            urls.append(url)
            return Respuesta(503 if len(urls) < 3 else 200)

    async def pausa(_):
        return None

    monkeypatch.setattr(ia.httpx, "AsyncClient", Cliente)
    monkeypatch.setattr(ia.asyncio, "sleep", pausa)
    oferta = OfertaSGVA("Ejemplo", None, None, "Analizar datos", "Bogotá", "Bogotá", 1)
    evaluaciones = asyncio.run(
        ia.clasificar_ofertas("clave-de-prueba", {"habilidades": "Python"}, "remoto", [oferta])
    )

    assert urls == [ia.URL, ia.URL, ia.URL_ALTERNATIVA]
    assert evaluaciones[0].puntuacion == 90
