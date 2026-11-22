"""
Módulo de Gestión de Configuración y Rutas según el Estándar XDG Base Directory.

Requerimientos cubiertos:
- SO-05: Guardado en ~/.config/prestamos_app y ~/.local/share/prestamos_app con permisos restrictivos (0700 dir, 0600 file).
- PR-25: Parámetros configurables (moneda, tasa máxima, tasa mora, feriados, datos entidad).
- SO-10: Manejo preventivo de errores del sistema de archivos.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    "entidad": {
        "nombre": "Cooperativa Financiera Popular",
        "nit": "900.123.456-7",
        "direccion": "Calle 45 # 23-10",
        "telefono": "+57 300 123 4567",
        "moneda_simbolo": "$",
        "moneda_codigo": "COP",
    },
    "parametros_prestamo": {
        "tasa_maxima_anual": 45.0,        # Tasa de usura / límite legal
        "tasa_mora_anual_defecto": 28.0,   # Tasa de mora anual
        "umbral_dias_mora_bloqueo": 30,    # PR-11: Bloquear nuevo crédito si mora > 30 días
        "alerta_cuotas_dias_anticipacion": 3, # PR-16: Notificar cuotas por vencer en N días
    },
    "respaldos": {
        "respaldo_automatico_activo": True,
        "intervalo_horas": 24,
        "max_copias_conservadas": 10,
    },
    "servidor_ipc": {
        "socket_nombre": "prestamo_daemon.sock",
    },
}


class ConfigManager:
    """Gestiona rutas XDG, permisos del sistema de archivos y configuración persistente."""

    def __init__(self, app_name: str = "prestamos_os"):
        self.app_name = app_name
        self.config_dir = self._obtener_dir_config()
        self.data_dir = self._obtener_dir_datos()
        self.backup_dir = self.data_dir / "backups"
        self.log_dir = self.data_dir / "logs"
        self.runtime_dir = self._obtener_dir_runtime()

        self.config_file = self.config_dir / "config.json"
        self.db_file = self.data_dir / "prestamos.db"
        self.socket_path = self.runtime_dir / DEFAULT_CONFIG["servidor_ipc"]["socket_nombre"]

        # Crear y asegurar permisos
        self._inicializar_directorios()
        self.config_data = self.cargar_configuracion()

    def _obtener_dir_config(self) -> Path:
        base = os.environ.get("XDG_CONFIG_HOME")
        if base:
            return Path(base) / self.app_name
        return Path.home() / ".config" / self.app_name

    def _obtener_dir_datos(self) -> Path:
        base = os.environ.get("XDG_DATA_HOME")
        if base:
            return Path(base) / self.app_name
        return Path.home() / ".local" / "share" / self.app_name

    def _obtener_dir_runtime(self) -> Path:
        base = os.environ.get("XDG_RUNTIME_DIR")
        if base and Path(base).exists():
            p = Path(base) / self.app_name
        else:
            p = self.data_dir / "run"
        return p

    def _aplicar_permisos(self, path: Path, modo: int):
        """Aplica permisos restrictivos (0700 para dirs, 0600 para files) en entornos POSIX."""
        if os.name != "nt":
            try:
                os.chmod(path, modo)
            except OSError:
                pass

    def _inicializar_directorios(self):
        """Crea la estructura de carpetas XDG con permisos 0700."""
        for d in [self.config_dir, self.data_dir, self.backup_dir, self.log_dir, self.runtime_dir]:
            try:
                d.mkdir(parents=True, exist_ok=True)
                self._aplicar_permisos(d, 0o700)
            except OSError as e:
                print(f"[ERROR SO-10] Error al inicializar directorio {d}: {e}", file=sys.stderr)

    def cargar_configuracion(self) -> Dict[str, Any]:
        """Carga config.json o genera el archivo con valores por defecto si no existe."""
        if not self.config_file.exists():
            self.guardar_configuracion(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except (json.JSONDecodeError, OSError) as e:
            print(f"[ALERTA SO-10] Fallo leyendo config.json ({e}). Usando configuración por defecto.")
            return DEFAULT_CONFIG.copy()

    def guardar_configuracion(self, nueva_config: Dict[str, Any]):
        """Persiste la configuración en config.json asegurando permisos 0600."""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(nueva_config, f, indent=4, ensure_ascii=False)
            self._aplicar_permisos(self.config_file, 0o600)
            self.config_data = nueva_config
        except OSError as e:
            print(f"[ERROR SO-10] Error guardando archivo de configuración {self.config_file}: {e}", file=sys.stderr)


# Instancia singleton para fácil acceso global
config_app = ConfigManager()
