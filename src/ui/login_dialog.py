"""
Diálogo de Inicio de Sesión (LoginDialog).
Cumple con:
- PR-01: Autenticación segura mediante verificación de hash de contraseña.
- PR-02: Detección y retorno del rol asignado (Administrador o Cajero).
"""

from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from src.database.db_manager import db_manager, verify_password


class LoginDialog(QDialog):
    """Diálogo modal para la autenticación de usuarios en el sistema."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PrestamoOS - Autenticación")
        self.setFixedSize(380, 420)
        self.setModal(True)
        self.user_session: Optional[Dict[str, Any]] = None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        # Tarjeta contenedora
        card = QFrame(self)
        card.setObjectName("loginCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 20, 15, 20)
        card_layout.setSpacing(12)

        # Encabezado
        lbl_title = QLabel("PrestamoOS", self)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font_title = QFont()
        font_title.setPointSize(18)
        font_title.setBold(True)
        lbl_title.setFont(font_title)
        card_layout.addWidget(lbl_title)

        lbl_subtitle = QLabel("Gestión Cooperativa de Préstamos", self)
        lbl_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_subtitle.setStyleSheet("color: #64748b; font-size: 12px; margin-bottom: 10px;")
        card_layout.addWidget(lbl_subtitle)

        # Campo Usuario
        lbl_user = QLabel("Nombre de Usuario:", self)
        lbl_user.setStyleSheet("font-weight: bold; font-size: 12px;")
        card_layout.addWidget(lbl_user)

        self.txt_username = QLineEdit(self)
        self.txt_username.setPlaceholderText("Ej: admin o cajero")
        self.txt_username.setStyleSheet("padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px;")
        card_layout.addWidget(self.txt_username)

        # Campo Contraseña
        lbl_pass = QLabel("Contraseña:", self)
        lbl_pass.setStyleSheet("font-weight: bold; font-size: 12px;")
        card_layout.addWidget(lbl_pass)

        self.txt_password = QLineEdit(self)
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("••••••••")
        self.txt_password.setStyleSheet("padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px;")
        card_layout.addWidget(self.txt_password)

        card_layout.addSpacing(10)

        # Botón Ingresar
        self.btn_login = QPushButton("Iniciar Sesión", self)
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setStyleSheet(
            """
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            """
        )
        self.btn_login.clicked.connect(self._intentar_login)
        card_layout.addWidget(self.btn_login)

        # Nota de credenciales por defecto para evaluación
        lbl_demo = QLabel("Usuarios iniciales:\nadmin / admin123  |  cajero / cajero123", self)
        lbl_demo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_demo.setStyleSheet("color: #94a3b8; font-size: 11px; margin-top: 8px;")
        card_layout.addWidget(lbl_demo)

        layout.addWidget(card)

        # Permitir presionar Enter en los campos
        self.txt_username.returnPressed.connect(self._intentar_login)
        self.txt_password.returnPressed.connect(self._intentar_login)

    def _intentar_login(self):
        username = self.txt_username.text().strip()
        password = self.txt_password.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Campos Requeridos", "Por favor ingrese su usuario y contraseña.")
            return

        try:
            conn = db_manager.get_connection()
            cur = conn.execute(
                """
                SELECT u.id, u.username, u.password_hash, u.nombre_completo, u.activo, r.nombre AS rol
                FROM usuarios u
                JOIN roles r ON u.rol_id = r.id
                WHERE u.username = ?
                """,
                (username,)
            )
            row = cur.fetchone()
            conn.close()

            if not row:
                QMessageBox.critical(self, "Error de Acceso", "Usuario o contraseña incorrectos.")
                return

            if not row["activo"]:
                QMessageBox.warning(self, "Usuario Desactivado", "Este usuario se encuentra inactivo en el sistema.")
                return

            if not verify_password(row["password_hash"], password):
                QMessageBox.critical(self, "Error de Acceso", "Usuario o contraseña incorrectos.")
                return

            # Autenticación exitosa
            self.user_session = {
                "id": row["id"],
                "username": row["username"],
                "nombre_completo": row["nombre_completo"],
                "rol": row["rol"],  # 'ADMINISTRADOR' o 'CAJERO'
            }
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error del Sistema", f"Error durante la autenticación: {e}")
