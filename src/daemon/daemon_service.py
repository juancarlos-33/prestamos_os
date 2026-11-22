"""
Demonio en Segundo Plano para el Sistema de Gestión de Préstamos (prestamo-daemon).

Cumple con:
- SO-03 / IPC: Servidor de Sockets de Dominio UNIX (AF_UNIX) con protocolo JSON por líneas.
- SO-04 / Señales: Manejo de SIGTERM/SIGINT (cierre ordenado) y SIGHUP (recarga de configuración).
- PR-16 / Alertas: Detección periódica de cuotas por vencer y emisión de notificaciones de escritorio.
- PR-26 / Respaldos: Ejecución de respaldos programados en segundo plano sin congelar la UI.
"""

import gzip
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from src.config import config_app
from src.database.db_manager import db_manager


class PrestamoDaemon:
    """Servicio demonio de fondo independiente de la interfaz gráfica."""

    def __init__(self):
        self.running = False
        self.socket_path = config_app.socket_path
        self.server_socket: socket.socket | None = None
        self.worker_thread: threading.Thread | None = None
        self.last_backup_time: datetime | None = None

        # Registro de señales POSIX
        self._registrar_senales()

    def _registrar_senales(self):
        """Asigna manejadores de señales estándar POSIX."""
        try:
            signal.signal(signal.SIGTERM, self._manejador_terminacion)
            signal.signal(signal.SIGINT, self._manejador_terminacion)
            if hasattr(signal, "SIGHUP"):
                signal.signal(signal.SIGHUP, self._manejador_recarga)
        except (ValueError, AttributeError) as e:
            print(f"[DAEMON] Advertencia registrando señales: {e}", file=sys.stderr)

    def _manejador_terminacion(self, signum, frame):
        """Manejo de cierre ordenado ante SIGTERM o SIGINT (SO-04 / Criterio 4)."""
        signame = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\n[DAEMON] Señal {signame} recibida. Iniciando cierre ordenado...", file=sys.stdout)
        self.detener()
        sys.exit(0)

    def _manejador_recarga(self, signum, frame):
        """Recarga dinámica de configuración ante SIGHUP sin detener el servicio (SO-04)."""
        print("\n[DAEMON] Señal SIGHUP recibida. Recargando configuración...", file=sys.stdout)
        config_app.config_data = config_app.cargar_configuracion()
        print("[DAEMON] Configuración recargada con éxito.", file=sys.stdout)

    def enviar_notificacion_escritorio(self, titulo: str, mensaje: str, urgencia: str = "normal"):
        """Envía notificación de escritorio en Linux utilizando notify-send o libnotify (PR-16)."""
        if shutil.which("notify-send"):
            try:
                subprocess.Popen(
                    ["notify-send", "-u", urgencia, "-a", "PrestamoOS", titulo, mensaje],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as e:
                print(f"[NOTIFICACION] Error invocando notify-send: {e}", file=sys.stderr)
        else:
            # Fallback a salida estándar cuando se ejecuta en consola o entorno sin display
            print(f"[NOTIFICACION ESCRITORIO] [{titulo}] {mensaje}")

    def ejecutar_respaldo_bd(self) -> Path:
        """
        Genera un respaldo comprimido .sql.gz de la base de datos SQLite (PR-26).
        Aplica permisos restrictivos 0700 en la carpeta y 0600 en el archivo.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = config_app.backup_dir / f"prestamos_backup_{ts}.sql.gz"

        with db_manager.transaction() as conn:
            # Volcado seguro de SQLite usando iterdump
            dump_lines = "\n".join(conn.iterdump()).encode("utf-8")
            with gzip.open(backup_file, "wb") as f_out:
                f_out.write(dump_lines)

        config_app._aplicar_permisos(backup_file, 0o600)
        self.last_backup_time = datetime.now()
        print(f"[DAEMON] Respaldo generado exitosamente: {backup_file.name}")
        return backup_file

    def verificar_cuotas_vencidas_y_proximas(self):
        """Vigila la cartera y genera alertas para cuotas en mora o próximas a vencer (PR-16)."""
        dias_aviso = config_app.config_data.get("parametros_prestamo", {}).get(
            "alerta_cuotas_dias_anticipacion", 3
        )
        hoy = date.today()
        limite_aviso = hoy + timedelta(days=dias_aviso)

        try:
            conn = db_manager.get_connection()
            # 1. Cuotas que vencen en los próximos N días
            cur = conn.execute(
                """
                SELECT c.numero_cuota, c.fecha_vencimiento, c.saldo_pendiente_cuota,
                       cl.nombres, cl.apellidos, cl.telefono
                FROM cuotas_amortizacion c
                JOIN prestamos p ON c.prestamo_id = p.id
                JOIN clientes cl ON p.cliente_id = cl.id
                WHERE c.estado = 'PENDIENTE'
                  AND c.fecha_vencimiento BETWEEN ? AND ?
                """,
                (hoy.isoformat(), limite_aviso.isoformat()),
            )
            proximas = cur.fetchall()
            if proximas:
                self.enviar_notificacion_escritorio(
                    titulo="Cuotas Próximas a Vencer",
                    mensaje=f"Hay {len(proximas)} cuotas próximas a vencer en los siguientes {dias_aviso} días.",
                    urgencia="normal",
                )

            # 2. Actualizar estado de cuotas vencidas no pagadas a EN_MORA
            with db_manager.transaction() as tx_conn:
                tx_conn.execute(
                    """
                    UPDATE cuotas_amortizacion
                    SET estado = 'EN_MORA'
                    WHERE estado = 'PENDIENTE' AND fecha_vencimiento < ?
                    """,
                    (hoy.isoformat(),),
                )
                tx_conn.execute(
                    """
                    UPDATE prestamos
                    SET estado = 'EN_MORA'
                    WHERE estado = 'ACTIVO' AND id IN (
                        SELECT DISTINCT prestamo_id FROM cuotas_amortizacion WHERE estado = 'EN_MORA'
                    )
                    """
                )
            conn.close()
        except Exception as e:
            print(f"[DAEMON ALERTA ERROR] Fallo al verificar cuotas: {e}", file=sys.stderr)

    def _bucle_vigia(self):
        """Hilo secundario del demonio para tareas periódicas (respaldos y alertas)."""
        print("[DAEMON] Hilo vigía iniciado en segundo plano.")
        while self.running:
            try:
                self.verificar_cuotas_vencidas_y_proximas()

                # Respaldo automático si pasaron las horas configuradas
                conf_respaldo = config_app.config_data.get("respaldos", {})
                if conf_respaldo.get("respaldo_automatico_activo", True):
                    intervalo_segundos = conf_respaldo.get("intervalo_horas", 24) * 3600
                    if not self.last_backup_time or (
                        datetime.now() - self.last_backup_time
                    ).total_seconds() >= intervalo_segundos:
                        self.ejecutar_respaldo_bd()

            except Exception as e:
                print(f"[DAEMON VIGIA EXCEPCION] {e}", file=sys.stderr)

            # Dormir en intervalos pequeños para permitir salida reactiva
            for _ in range(60):
                if not self.running:
                    break
                time.sleep(1)

    def _atender_peticion_ipc(self, mensaje_str: str) -> Dict[str, Any]:
        """Procesa peticiones JSON recibidas a través del socket Unix."""
        try:
            req = json.loads(mensaje_str)
            action = req.get("action")
            req_id = req.get("id", "req-0")

            if action == "STATUS":
                return {
                    "id": req_id,
                    "status": "OK",
                    "data": {
                        "daemon_pid": os.getpid(),
                        "running": True,
                        "last_backup": self.last_backup_time.isoformat() if self.last_backup_time else None,
                        "uptime": "active",
                    },
                }
            elif action == "TRIGGER_BACKUP":
                archivo = self.ejecutar_respaldo_bd()
                return {"id": req_id, "status": "OK", "data": {"archivo": str(archivo)}}
            elif action == "CHECK_OVERDUE":
                self.verificar_cuotas_vencidas_y_proximas()
                return {"id": req_id, "status": "OK", "data": {"mensaje": "Verificación completada"}}
            elif action == "RELOAD_CONFIG":
                config_app.config_data = config_app.cargar_configuracion()
                return {"id": req_id, "status": "OK", "data": {"mensaje": "Configuración recargada"}}
            else:
                return {"id": req_id, "status": "ERROR", "error": f"Acción desconocida: {action}"}
        except json.JSONDecodeError as e:
            return {"status": "ERROR", "error": f"JSON inválido: {e}"}

    def iniciar(self):
        """Inicia el servidor de socket Unix y el hilo de tareas de fondo."""
        self.running = True

        # Iniciar hilo de tareas de fondo
        self.worker_thread = threading.Thread(target=self._bucle_vigia, daemon=True)
        self.worker_thread.start()

        # Configurar socket Unix (o loopback en Windows si no está AF_UNIX disponible)
        usar_unix_socket = hasattr(socket, "AF_UNIX")

        if usar_unix_socket:
            if self.socket_path.exists():
                try:
                    self.socket_path.unlink()
                except OSError:
                    pass
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(str(self.socket_path))
            config_app._aplicar_permisos(self.socket_path, 0o600)
            print(f"[DAEMON] Servidor IPC escuchando en socket Unix: {self.socket_path}")
        else:
            # Fallback de desarrollo para pruebas en entornos Windows
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind(("127.0.0.1", 49152))
            print("[DAEMON] Servidor IPC escuchando en socket loopback TCP 127.0.0.1:49152")

        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)

        while self.running:
            try:
                conn, _ = self.server_socket.accept()
                with conn:
                    datos = conn.recv(4096)
                    if datos:
                        respuesta = self._atender_peticion_ipc(datos.decode("utf-8"))
                        conn.sendall((json.dumps(respuesta) + "\n").encode("utf-8"))
            except socket.timeout:
                continue
            except OSError:
                break

    def detener(self):
        """Detiene el servicio y limpia los descriptores y el socket del sistema."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass

        if hasattr(socket, "AF_UNIX") and self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass

        print("[DAEMON] Servicio detenido y recursos liberados limpiamente.")


if __name__ == "__main__":
    daemon = PrestamoDaemon()
    try:
        daemon.iniciar()
    except KeyboardInterrupt:
        daemon.detener()
