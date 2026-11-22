"""
Cliente IPC para la interfaz gráfica (PyQt6).
Se comunica con el demonio a través del Socket Unix o fallback de red.
"""

import json
import socket
from typing import Any, Dict, Optional

from src.config import config_app


class DaemonIPCClient:
    """Cliente para enviar comandos y recibir el estado del Demonio."""

    def __init__(self):
        self.socket_path = config_app.socket_path

    def enviar_comando(self, accion: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 3.0) -> Dict[str, Any]:
        """Envía una acción al demonio y espera la respuesta JSON."""
        usar_unix = hasattr(socket, "AF_UNIX") and self.socket_path.exists()
        
        req = {
            "id": f"req-{accion}",
            "action": accion,
            "payload": payload or {}
        }
        raw_msg = json.dumps(req).encode("utf-8")

        try:
            if usar_unix:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect(str(self.socket_path))
            else:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect(("127.0.0.1", 49152))

            with s:
                s.sendall(raw_msg)
                resp_bytes = s.recv(8192)
                if not resp_bytes:
                    return {"status": "ERROR", "error": "Respuesta vacía del demonio"}
                return json.loads(resp_bytes.decode("utf-8"))
        except (socket.error, OSError) as e:
            return {"status": "OFFLINE", "error": f"Demonio no disponible: {e}"}

    def obtener_estado(self) -> Dict[str, Any]:
        return self.enviar_comando("STATUS")

    def forzar_respaldo(self) -> Dict[str, Any]:
        return self.enviar_comando("TRIGGER_BACKUP")

    def recargar_configuracion(self) -> Dict[str, Any]:
        return self.enviar_comando("RELOAD_CONFIG")
