"""Un turno de revisión final por proceso, con espera ordenada y vencimiento."""

from collections import deque
from threading import Lock
from time import monotonic


class TurnosConfirmacion:
    """Coordina las ventanas de confirmación del único servidor de envíos."""

    def __init__(self, duracion_segundos: int = 90) -> None:
        self._duracion = duracion_segundos
        self._candado = Lock()
        self._actual: str | None = None
        self._vence_actual = 0.0
        self._pendientes: deque[str] = deque()
        self._vence_pendientes: dict[str, float] = {}

    def _depurar(self, ahora: float) -> None:
        if self._actual and self._vence_actual <= ahora:
            self._actual = None
        self._pendientes = deque(
            campana_id
            for campana_id in self._pendientes
            if self._vence_pendientes.get(campana_id, 0) > ahora
        )
        self._vence_pendientes = {
            campana_id: self._vence_pendientes[campana_id] for campana_id in self._pendientes
        }

    def solicitar(self, campana_id: str) -> dict[str, str | int]:
        with self._candado:
            ahora = monotonic()
            self._depurar(ahora)
            if self._actual == campana_id:
                self._vence_actual = ahora + self._duracion
                return {"estado": "listo", "personas_delante": 0}
            if campana_id not in self._vence_pendientes:
                self._pendientes.append(campana_id)
            self._vence_pendientes[campana_id] = ahora + self._duracion
            if self._actual is None and self._pendientes[0] == campana_id:
                self._pendientes.popleft()
                self._vence_pendientes.pop(campana_id)
                self._actual = campana_id
                self._vence_actual = ahora + self._duracion
                return {"estado": "listo", "personas_delante": 0}
            delante = self._pendientes.index(campana_id)
            return {"estado": "en_espera", "personas_delante": delante + bool(self._actual)}

    def vigente(self, campana_id: str) -> bool:
        with self._candado:
            self._depurar(monotonic())
            return self._actual == campana_id

    def liberar(self, campana_id: str) -> None:
        with self._candado:
            if self._actual == campana_id:
                self._actual = None
                self._vence_actual = 0
            self._vence_pendientes.pop(campana_id, None)
            self._pendientes = deque(
                pendiente for pendiente in self._pendientes if pendiente != campana_id
            )
