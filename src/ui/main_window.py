"""
Ventana Principal de PrestamoOS (MainWindow).
Cumple con:
- PR-01 / PR-02: Control de acceso por roles (Administrador vs Cajero).
- SO-02 / Rendimiento: Navegación fluida y multihilo.
- SO-03 / IPC: Indicador en tiempo real del estado de comunicación con el demonio.
"""

import sys
from typing import Dict, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QStatusBar, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon

from src.ui.login_dialog import LoginDialog
from src.ui.clientes_view import ClientesView
from src.ui.prestamos_view import PrestamosView
from src.ui.pagos_view import PagosView
from src.ui.config_view import ConfigView
from src.ui.reportes_view import ReportesView
from src.ui.calendar_view import CalendarioView
from src.daemon.ipc_client import DaemonIPCClient
from src.config import config_app


class MainWindow(QMainWindow):
    """Ventana principal de la aplicación de escritorio."""

    def __init__(self, user_session: Dict[str, Any]):
        super().__init__()
        self.user_session = user_session
        self.ipc_client = DaemonIPCClient()

        self.setWindowTitle(f"PrestamoOS — Entidad Cooperativa ({user_session['nombre_completo']})")
        self.resize(1180, 750)
        self.setMinimumSize(960, 600)

        self._setup_ui()
        self._iniciar_monitor_ipc()

    def _setup_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 1. Barra de Encabezado Superior
        header_frame = QFrame(self)
        header_frame.setStyleSheet(
            "background-color: #1e293b; color: white; border-radius: 8px; padding: 6px 12px;"
        )
        header_layout = QHBoxLayout(header_frame)

        lbl_app = QLabel("💼 PrestamoOS", self)
        font_app = QFont()
        font_app.setPointSize(14)
        font_app.setBold(True)
        lbl_app.setFont(font_app)
        header_layout.addWidget(lbl_app)

        header_layout.addStretch()

        # Insignia de Usuario y Rol
        es_admin = self.user_session["rol"] == "ADMINISTRADOR"
        rol_color = "#3b82f6" if es_admin else "#10b981"
        lbl_user = QLabel(
            f"👤 <b>{self.user_session['nombre_completo']}</b> "
            f"<span style='background-color: {rol_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;'>"
            f"{self.user_session['rol']}</span>",
            self
        )
        lbl_user.setStyleSheet("font-size: 13px;")
        header_layout.addWidget(lbl_user)

        # Botón Cerrar Sesión
        btn_logout = QPushButton("Cerrar Sesión", self)
        btn_logout.setStyleSheet(
            "background-color: #ef4444; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px; font-size: 11px;"
        )
        btn_logout.clicked.connect(self._cerrar_sesion)
        header_layout.addWidget(btn_logout)

        main_layout.addWidget(header_frame)

        # 2. Pestañas de Navegación del Sistema
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(
            """
            QTabBar::tab {
                font-weight: bold;
                padding: 10px 20px;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background: #2563eb;
                color: white;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            """
        )

        self.tab_clientes = ClientesView(self)
        self.tab_prestamos = PrestamosView(self, user_session=self.user_session)
        self.tab_pagos = PagosView(self, user_session=self.user_session)
        self.tab_calendario = CalendarioView(self, user_session=self.user_session)
        self.tab_reportes = ReportesView(self, user_session=self.user_session)

        self.tabs.addTab(self.tab_clientes, "👥 Clientes")
        self.tabs.addTab(self.tab_prestamos, "📊 Préstamos y Simulación")
        self.tabs.addTab(self.tab_pagos, "💰 Pagos y Recaudos")
        self.tabs.addTab(self.tab_calendario, "📅 Calendario de Vencimientos")
        self.tabs.addTab(self.tab_reportes, "📑 Reportes y Exportación")

        # PR-02: La pestaña de configuración solo está habilitada para Administradores
        if es_admin:
            self.tab_config = ConfigView(self, user_session=self.user_session)
            self.tabs.addTab(self.tab_config, "⚙️ Configuración y Demonio IPC")

        # Refrescar listas al cambiar de pestaña
        self.tabs.currentChanged.connect(self._al_cambiar_pestana)

        main_layout.addWidget(self.tabs)

        # 3. Barra de Estado Inferior con Monitor IPC
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.lbl_status_db = QLabel(f"📁 BD: {config_app.db_file.name} (Modo WAL)", self)
        self.lbl_status_ipc = QLabel("● Demonio IPC: Verificando...", self)
        self.status_bar.addWidget(self.lbl_status_db)
        self.status_bar.addPermanentWidget(self.lbl_status_ipc)

    def _al_cambiar_pestana(self, index: int):
        # Actualizar dinámicamente datos según la pestaña activa
        if index == 1:
            self.tab_prestamos.actualizar_lista_clientes()
        elif index == 2:
            self.tab_pagos.cargar_prestamos_activos()
        elif index == 3:
            self.tab_calendario.cargar_datos_calendario()

    def _iniciar_monitor_ipc(self):
        """Temporizador periódico de bajo impacto para vigilar el estado del Demonio."""
        self.timer_ipc = QTimer(self)
        self.timer_ipc.timeout.connect(self._actualizar_estado_demonio_status_bar)
        self.timer_ipc.start(5000)  # Cada 5 segundos
        self._actualizar_estado_demonio_status_bar()

    def _actualizar_estado_demonio_status_bar(self):
        resp = self.ipc_client.obtener_estado()
        if resp.get("status") == "OK":
            pid = resp.get("data", {}).get("daemon_pid")
            self.lbl_status_ipc.setText(f"● Demonio IPC: ACTIVO (PID: {pid})")
            self.lbl_status_ipc.setStyleSheet("color: #16a34a; font-weight: bold; padding-right: 15px;")
        else:
            self.lbl_status_ipc.setText("○ Demonio IPC: DETENIDO / OFFLINE")
            self.lbl_status_ipc.setStyleSheet("color: #dc2626; font-weight: bold; padding-right: 15px;")

    def _cerrar_sesion(self):
        resp = QMessageBox.question(
            self, "Cerrar Sesión", "¿Está seguro de que desea cerrar la sesión actual?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.Yes:
            self.close()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Diálogo de Login Modal Obligatorio (PR-01)
    login_dlg = LoginDialog()
    if login_dlg.exec() != LoginDialog.DialogCode.Accepted or not login_dlg.user_session:
        sys.exit(0)

    # Iniciar Ventana Principal con la sesión autenticada
    window = MainWindow(user_session=login_dlg.user_session)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
