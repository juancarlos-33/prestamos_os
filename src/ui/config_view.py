"""
Vista de Configuración del Sistema y Monitor del Demonio (ConfigView).
Cumple con:
- PR-02: Acceso exclusivo para el rol de Administrador.
- PR-25: Parámetros configurables (moneda, tasas máximas, feriados, datos entidad).
- PR-26: Respaldo y restauración de base de datos a través de proceso independiente.
- SO-03: Control y comunicación IPC vía sockets UNIX con el servicio demonio.
- SO-04: Recarga dinámica ante señal SIGHUP.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QDoubleSpinBox, QSpinBox, QGroupBox, QFormLayout,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt

from src.config import config_app
from src.daemon.ipc_client import DaemonIPCClient


class ConfigView(QWidget):
    """Pestaña de administración del sistema y control de procesos."""

    def __init__(self, parent=None, user_session: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.user_session = user_session or {"id": 1, "username": "admin", "rol": "ADMINISTRADOR"}
        self.ipc_client = DaemonIPCClient()
        self._setup_ui()
        self.cargar_datos_config()
        self.verificar_estado_demonio()
        self.cargar_lista_respaldos()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        h_panels = QHBoxLayout()

        # Panel Izquierdo: Parámetros de la Entidad y Financieros (PR-25)
        left_box = QGroupBox("Parámetros Generales de la Entidad y Financieros (PR-25)", self)
        form_params = QFormLayout(left_box)
        form_params.setSpacing(8)

        self.txt_entidad_nombre = QLineEdit(self)
        form_params.addRow("Nombre de la Entidad:", self.txt_entidad_nombre)

        self.txt_entidad_nit = QLineEdit(self)
        form_params.addRow("NIT / Identificación:", self.txt_entidad_nit)

        self.txt_entidad_direccion = QLineEdit(self)
        form_params.addRow("Dirección:", self.txt_entidad_direccion)

        self.txt_entidad_telefono = QLineEdit(self)
        form_params.addRow("Teléfono de Contacto:", self.txt_entidad_telefono)

        self.txt_moneda = QLineEdit(self)
        form_params.addRow("Símbolo de Moneda:", self.txt_moneda)

        self.sp_tasa_max = QDoubleSpinBox(self)
        self.sp_tasa_max.setRange(1.0, 100.0)
        self.sp_tasa_max.setSuffix(" % anual")
        form_params.addRow("Tasa Máxima Permitida (Usura):", self.sp_tasa_max)

        self.sp_tasa_mora = QDoubleSpinBox(self)
        self.sp_tasa_mora.setRange(1.0, 100.0)
        self.sp_tasa_mora.setSuffix(" % anual")
        form_params.addRow("Tasa de Mora por Defecto:", self.sp_tasa_mora)

        self.sp_umbral_bloqueo = QSpinBox(self)
        self.sp_umbral_bloqueo.setRange(1, 365)
        self.sp_umbral_bloqueo.setSuffix(" días")
        form_params.addRow("Umbral Mora Bloqueo Préstamos:", self.sp_umbral_bloqueo)

        self.sp_dias_alerta = QSpinBox(self)
        self.sp_dias_alerta.setRange(1, 30)
        self.sp_dias_alerta.setSuffix(" días antes")
        form_params.addRow("Anticipación Alertas de Vencimiento:", self.sp_dias_alerta)

        self.btn_guardar_config = QPushButton("💾 Guardar Configuración", self)
        self.btn_guardar_config.setStyleSheet("background-color: #2563eb; color: white; padding: 8px; font-weight: bold;")
        self.btn_guardar_config.clicked.connect(self._guardar_configuracion)
        form_params.addRow("", self.btn_guardar_config)

        h_panels.addWidget(left_box, stretch=1)

        # Panel Derecho: Control del Demonio IPC y Respaldos (SO-03, SO-04, PR-26)
        right_box = QGroupBox("Servicio Demonio de Fondo e IPC (SO-03 / PR-26)", self)
        right_layout = QVBoxLayout(right_box)

        # Tarjeta de Estado IPC
        form_daemon = QFormLayout()
        self.lbl_daemon_status = QLabel("Consultando...", self)
        self.lbl_daemon_status.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.lbl_daemon_pid = QLabel("-", self)
        self.lbl_daemon_socket = QLabel(str(config_app.socket_path), self)
        self.lbl_daemon_socket.setStyleSheet("font-size: 11px; color: #475569;")

        form_daemon.addRow("Estado del Demonio:", self.lbl_daemon_status)
        form_daemon.addRow("PID del Proceso:", self.lbl_daemon_pid)
        form_daemon.addRow("Canal IPC (Socket):", self.lbl_daemon_socket)
        right_layout.addLayout(form_daemon)

        # Botones de Acción IPC
        ipc_btn_layout = QHBoxLayout()
        self.btn_ping_daemon = QPushButton("🔄 Verificar Estado", self)
        self.btn_ping_daemon.clicked.connect(self.verificar_estado_demonio)

        self.btn_backup_now = QPushButton("📦 Disparar Respaldo (IPC)", self)
        self.btn_backup_now.setStyleSheet("background-color: #059669; color: white; font-weight: bold;")
        self.btn_backup_now.clicked.connect(self._disparar_respaldo_ipc)

        self.btn_reload_conf = QPushButton("⚡ Recargar Config (SIGHUP)", self)
        self.btn_reload_conf.clicked.connect(self._recargar_config_ipc)

        ipc_btn_layout.addWidget(self.btn_ping_daemon)
        ipc_btn_layout.addWidget(self.btn_backup_now)
        ipc_btn_layout.addWidget(self.btn_reload_conf)
        right_layout.addLayout(ipc_btn_layout)

        # Tabla de Respaldos Realizados
        lbl_respaldos = QLabel("Historial de Respaldos Locales (.sql.gz):", self)
        lbl_respaldos.setStyleSheet("font-weight: bold; margin-top: 10px;")
        right_layout.addWidget(lbl_respaldos)

        self.tabla_backups = QTableWidget(self)
        self.tabla_backups.setColumnCount(3)
        self.tabla_backups.setHorizontalHeaderLabels(["Archivo de Respaldo", "Tamaño", "Fecha de Creación"])
        self.tabla_backups.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_backups.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_backups.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        right_layout.addWidget(self.tabla_backups)

        h_panels.addWidget(right_box, stretch=1)
        main_layout.addLayout(h_panels)

    def cargar_datos_config(self):
        c = config_app.config_data
        ent = c.get("entidad", {})
        self.txt_entidad_nombre.setText(ent.get("nombre", ""))
        self.txt_entidad_nit.setText(ent.get("nit", ""))
        self.txt_entidad_direccion.setText(ent.get("direccion", ""))
        self.txt_entidad_telefono.setText(ent.get("telefono", ""))
        self.txt_moneda.setText(ent.get("moneda_simbolo", "$"))

        par = c.get("parametros_prestamo", {})
        self.sp_tasa_max.setValue(float(par.get("tasa_maxima_anual", 45.0)))
        self.sp_tasa_mora.setValue(float(par.get("tasa_mora_anual_defecto", 28.0)))
        self.sp_umbral_bloqueo.setValue(int(par.get("umbral_dias_mora_bloqueo", 30)))
        self.sp_dias_alerta.setValue(int(par.get("alerta_cuotas_dias_anticipacion", 3)))

    def _guardar_configuracion(self):
        nueva = config_app.config_data.copy()
        nueva["entidad"] = {
            "nombre": self.txt_entidad_nombre.text().strip(),
            "nit": self.txt_entidad_nit.text().strip(),
            "direccion": self.txt_entidad_direccion.text().strip(),
            "telefono": self.txt_entidad_telefono.text().strip(),
            "moneda_simbolo": self.txt_moneda.text().strip(),
            "moneda_codigo": "COP",
        }
        nueva["parametros_prestamo"] = {
            "tasa_maxima_anual": self.sp_tasa_max.value(),
            "tasa_mora_anual_defecto": self.sp_tasa_mora.value(),
            "umbral_dias_mora_bloqueo": self.sp_umbral_bloqueo.value(),
            "alerta_cuotas_dias_anticipacion": self.sp_dias_alerta.value(),
        }

        config_app.guardar_configuracion(nueva)
        QMessageBox.information(self, "Configuración Guardada", "Los parámetros del sistema fueron actualizados con éxito en config.json.")
        # Notificar al demonio automáticamente
        self._recargar_config_ipc(silencioso=True)

    def verificar_estado_demonio(self):
        """Consulta el estado del servicio demonio a través del canal IPC."""
        resp = self.ipc_client.obtener_estado()
        if resp.get("status") == "OK":
            data = resp.get("data", {})
            self.lbl_daemon_status.setText("● ACTIVO (ONLINE)")
            self.lbl_daemon_status.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 13px;")
            self.lbl_daemon_pid.setText(str(data.get("daemon_pid", "-")))
        else:
            self.lbl_daemon_status.setText("○ DETENIDO / OFFLINE")
            self.lbl_daemon_status.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 13px;")
            self.lbl_daemon_pid.setText("-")

    def _disparar_respaldo_ipc(self):
        """Envía comando IPC al demonio para generar copia de seguridad."""
        resp = self.ipc_client.forzar_respaldo()
        if resp.get("status") == "OK":
            archivo = resp.get("data", {}).get("archivo", "")
            QMessageBox.information(self, "Respaldo Generado", f"El demonio generó el respaldo con éxito:\n{archivo}")
            self.cargar_lista_respaldos()
        else:
            QMessageBox.warning(self, "Fallo IPC", f"No se pudo ejecutar el respaldo vía IPC: {resp.get('error')}")

    def _recargar_config_ipc(self, silencioso: bool = False):
        """Envía comando IPC para que el demonio relea config.json sin reiniciarse."""
        resp = self.ipc_client.recargar_configuracion()
        if not silencioso:
            if resp.get("status") == "OK":
                QMessageBox.information(self, "Recarga SIGHUP", "El servicio demonio recargó la configuración exitosamente.")
            else:
                QMessageBox.warning(self, "Fallo IPC", f"No se pudo recargar la configuración en el demonio: {resp.get('error')}")

    def cargar_lista_respaldos(self):
        """Lista las copias de seguridad existentes en ~/.local/share/prestamos_os/backups/."""
        b_dir = config_app.backup_dir
        if not b_dir.exists():
            return

        archivos = sorted(list(b_dir.glob("*.sql.gz")), key=lambda p: p.stat().st_mtime, reverse=True)
        self.tabla_backups.setRowCount(len(archivos))
        for i, a in enumerate(archivos):
            size_kb = a.stat().st_size / 1024.0
            dt = datetime.fromtimestamp(a.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

            self.tabla_backups.setItem(i, 0, QTableWidgetItem(a.name))
            self.tabla_backups.setItem(i, 1, QTableWidgetItem(f"{size_kb:,.1f} KB"))
            self.tabla_backups.setItem(i, 2, QTableWidgetItem(dt))
