"""Límites locales para las rutas que pueden consumir recursos o crear datos."""

import asyncio
from collections import defaultdict, deque
from time import monotonic


class LimiteSolicitudes:
    """Ventana deslizante por cliente y operación, válida para un solo proceso."""

    def __init__(self) -> None:
        self._intentos: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._bloqueo = asyncio.Lock()

    async def comprobar(self, cliente: str, operacion: str, cantidad: int, ventana: int) -> int:
        ahora = monotonic()
        clave = (cliente, operacion)
        async with self._bloqueo:
            if len(self._intentos) > 5000:
                self._intentos = defaultdict(
                    deque,
                    {
                        llave: tiempos
                        for llave, tiempos in self._intentos.items()
                        if tiempos and ahora - tiempos[-1] < 86400
                    },
                )
            intentos = self._intentos[clave]
            while intentos and ahora - intentos[0] >= ventana:
                intentos.popleft()
            if len(intentos) >= cantidad:
                return max(1, int(ventana - (ahora - intentos[0])) + 1)
            intentos.append(ahora)
        return 0


def regla_para(metodo: str, ruta: str) -> tuple[str, int, int] | None:
    if ruta == "/api/v1/autenticacion/google/iniciar":
        return "inicio-google", 10, 900
    if metodo == "POST" and ruta == "/api/v1/pagos-premium":
        return "comprobantes", 6, 86400
    if metodo == "POST" and ruta == "/api/v1/campanas":
        return "campanas", 12, 3600
    if metodo == "POST" and ruta.endswith("/iniciar") and ruta.startswith("/api/v1/campanas/"):
        return "consultas-sgva", 12, 3600
    if metodo == "POST" and ruta.endswith("/enviar") and ruta.startswith("/api/v1/campanas/"):
        return "envios", 20, 3600
    if ruta.startswith("/api/v1/") and metodo not in {"GET", "HEAD", "OPTIONS"}:
        return "cambios", 120, 60
    return None
