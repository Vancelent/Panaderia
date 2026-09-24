import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    """Limita intentos fallidos de login por clave (IP + usuario).

    En memoria y por proceso: suficiente para un único worker de uvicorn.
    Con varias réplicas habría que moverlo a Redis.
    """

    def __init__(self, max_intentos: int, ventana_segundos: int):
        self.max_intentos = max_intentos
        self.ventana = ventana_segundos
        self._fallos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _purgar(self, key: str, ahora: float) -> deque[float]:
        fallos = self._fallos[key]
        while fallos and ahora - fallos[0] > self.ventana:
            fallos.popleft()
        return fallos

    def bloqueado(self, key: str) -> bool:
        with self._lock:
            return len(self._purgar(key, time.monotonic())) >= self.max_intentos

    def registrar_fallo(self, key: str) -> None:
        with self._lock:
            ahora = time.monotonic()
            self._purgar(key, ahora).append(ahora)

    def limpiar(self, key: str) -> None:
        with self._lock:
            self._fallos.pop(key, None)
