"""
Vista de Gestión de Clientes (ClientesView).
Cumple con:
- PR-03: Crear, consultar, editar y desactivar clientes.
- PR-04: Datos requeridos: tipo/número doc, nombres, apellidos, fecha nac, tel, correo, dirección, ocupación, ingresos.
- PR-05: Validaciones de formato (email, teléfono, doc) e impedimento de duplicados.
- PR-06: Búsqueda por nombre o documento con paginación.
"""

import re
from datetime import date
from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QComboBox, QDateEdit,
    QDoubleSpinBox, QCheckBox
)
from PyQt6.QtCore import Qt, QDate

from src.database.db_manager import db_manager


class ClienteDialog(QDialog):
    """Diálogo modal para crear o editar un cliente con validaciones."""

    def __init__(self, parent=None, cliente_data=None):
        super().__init__(parent)
        self.cliente_data = cliente_data
        self.es_edicion = cliente_data is not None
        self.setWindowTitle("Editar Cliente" if self.es_edicion else "Nuevo Cliente")
        self.setMinimumWidth(450)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.cb_tipo_doc = QComboBox(self)
        self.cb_tipo_doc.addItems(["CC", "CE", "NIT", "PASAPORTE"])
        form.addRow("Tipo Documento (*):", self.cb_tipo_doc)

        self.txt_num_doc = QLineEdit(self)
        self.txt_num_doc.setPlaceholderText("Ej: 1045678901")
        form.addRow("Número Documento (*):", self.txt_num_doc)

        self.txt_nombres = QLineEdit(self)
        form.addRow("Nombres (*):", self.txt_nombres)

        self.txt_apellidos = QLineEdit(self)
        form.addRow("Apellidos (*):", self.txt_apellidos)

        self.dt_nacimiento = QDateEdit(self)
        self.dt_nacimiento.setCalendarPopup(True)
        self.dt_nacimiento.setDate(QDate(1995, 1, 1))
        form.addRow("Fecha de Nacimiento:", self.dt_nacimiento)

        self.txt_telefono = QLineEdit(self)
        self.txt_telefono.setPlaceholderText("Ej: 3001234567")
        form.addRow("Teléfono (*):", self.txt_telefono)

        self.txt_correo = QLineEdit(self)
        self.txt_correo.setPlaceholderText("ejemplo@correo.com")
        form.addRow("Correo Electrónico (*):", self.txt_correo)

        self.txt_direccion = QLineEdit(self)
        form.addRow("Dirección (*):", self.txt_direccion)

        self.txt_ocupacion = QLineEdit(self)
        form.addRow("Ocupación:", self.txt_ocupacion)

        self.sp_ingresos = QDoubleSpinBox(self)
        self.sp_ingresos.setRange(0.0, 999999999.0)
        self.sp_ingresos.setPrefix("$ ")
        self.sp_ingresos.setValue(2500000.0)
        form.addRow("Ingresos Mensuales (*):", self.sp_ingresos)

        self.chk_activo = QCheckBox("Cliente Activo", self)
        self.chk_activo.setChecked(True)
        if self.es_edicion:
            form.addRow("Estado:", self.chk_activo)

        layout.addLayout(form)

        # Botones de acción
        btn_layout = QHBoxLayout()
        self.btn_guardar = QPushButton("Guardar Cliente", self)
        self.btn_guardar.setStyleSheet("background-color: #2563eb; color: white; padding: 8px; font-weight: bold;")
        self.btn_guardar.clicked.connect(self._guardar)

        self.btn_cancelar = QPushButton("Cancelar", self)
        self.btn_cancelar.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancelar)
        btn_layout.addWidget(self.btn_guardar)
        layout.addLayout(btn_layout)

        if self.es_edicion and self.cliente_data:
            self._cargar_datos()

    def _cargar_datos(self):
        c = self.cliente_data
        self.cb_tipo_doc.setCurrentText(c["tipo_documento"])
        self.txt_num_doc.setText(str(c["numero_documento"]))
        self.txt_num_doc.setEnabled(False)  # No se permite alterar número de doc en edición
        self.txt_nombres.setText(c["nombres"])
        self.txt_apellidos.setText(c["apellidos"])
        if c["fecha_nacimiento"]:
            y, m, d = map(int, str(c["fecha_nacimiento"]).split("-"))
            self.dt_nacimiento.setDate(QDate(y, m, d))
        self.txt_telefono.setText(c["telefono"])
        self.txt_correo.setText(c["correo"])
        self.txt_direccion.setText(c["direccion"])
        self.txt_ocupacion.setText(c["ocupacion"] or "")
        self.sp_ingresos.setValue(float(c["ingresos_mensuales"]))
        self.chk_activo.setChecked(bool(c["activo"]))

    def _validar_entradas(self) -> bool:
        """Valida formatos según PR-05."""
        if not self.txt_num_doc.text().strip():
            QMessageBox.warning(self, "Validación", "El número de documento es obligatorio.")
            return False

        if not self.txt_nombres.text().strip() or not self.txt_apellidos.text().strip():
            QMessageBox.warning(self, "Validación", "Nombres y apellidos son obligatorios.")
            return False

        tel = self.txt_telefono.text().strip()
        if not re.match(r"^\+?[0-9]{7,15}$", tel):
            QMessageBox.warning(self, "Validación", "El teléfono debe contener entre 7 y 15 dígitos numéricos.")
            return False

        correo = self.txt_correo.text().strip()
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", correo):
            QMessageBox.warning(self, "Validación", "El correo electrónico no tiene un formato válido.")
            return False

        if not self.txt_direccion.text().strip():
            QMessageBox.warning(self, "Validación", "La dirección es obligatoria.")
            return False

        return True

    def _guardar(self):
        if not self._validar_entradas():
            return

        tipo_doc = self.cb_tipo_doc.currentText()
        num_doc = self.txt_num_doc.text().strip()
        nombres = self.txt_nombres.text().strip()
        apellidos = self.txt_apellidos.text().strip()
        f_nac = self.dt_nacimiento.date().toString("yyyy-MM-dd")
        tel = self.txt_telefono.text().strip()
        correo = self.txt_correo.text().strip()
        direccion = self.txt_direccion.text().strip()
        ocupacion = self.txt_ocupacion.text().strip()
        ingresos = Decimal(str(self.sp_ingresos.value()))
        activo = 1 if self.chk_activo.isChecked() else 0

        try:
            with db_manager.transaction() as conn:
                if not self.es_edicion:
                    # Verificar duplicado (PR-05)
                    cur = conn.execute("SELECT id FROM clientes WHERE numero_documento = ?", (num_doc,))
                    if cur.fetchone():
                        QMessageBox.warning(self, "Duplicado", "Ya existe un cliente registrado con ese número de documento.")
                        return

                    conn.execute(
                        """
                        INSERT INTO clientes (tipo_documento, numero_documento, nombres, apellidos,
                                             fecha_nacimiento, telefono, correo, direccion, ocupacion, ingresos_mensuales, activo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (tipo_doc, num_doc, nombres, apellidos, f_nac, tel, correo, direccion, ocupacion, str(ingresos))
                    )
                else:
                    conn.execute(
                        """
                        UPDATE clientes
                        SET nombres = ?, apellidos = ?, fecha_nacimiento = ?, telefono = ?,
                            correo = ?, direccion = ?, ocupacion = ?, ingresos_mensuales = ?, activo = ?
                        WHERE id = ?
                        """,
                        (nombres, apellidos, f_nac, tel, correo, direccion, ocupacion, str(ingresos), activo, self.cliente_data["id"])
                    )

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar", f"No se pudo guardar el cliente: {e}")


class ClientesView(QWidget):
    """Pestaña de administración y consulta de clientes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pagina_actual = 0
        self.tamanio_pagina = 10
        self.total_paginas = 1
        self._setup_ui()
        self.cargar_clientes()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # Barra superior con búsqueda y botón nuevo
        top_bar = QHBoxLayout()
        self.txt_buscar = QLineEdit(self)
        self.txt_buscar.setPlaceholderText("🔍 Buscar cliente por nombre o documento...")
        self.txt_buscar.textChanged.connect(self._al_cambiar_busqueda)
        top_bar.addWidget(self.txt_buscar, stretch=4)

        self.btn_nuevo = QPushButton("+ Registrar Cliente", self)
        self.btn_nuevo.setStyleSheet("background-color: #16a34a; color: white; padding: 8px 14px; font-weight: bold; border-radius: 4px;")
        self.btn_nuevo.clicked.connect(self._nuevo_cliente)
        top_bar.addWidget(self.btn_nuevo, stretch=1)

        layout.addLayout(top_bar)

        # Tabla de clientes
        self.tabla = QTableWidget(self)
        self.tabla.setColumnCount(8)
        self.tabla.setHorizontalHeaderLabels([
            "ID", "Documento", "Nombre Completo", "Teléfono", "Correo", "Ingresos", "Estado", "Acciones"
        ])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        layout.addWidget(self.tabla)

        # Barra de paginación inferior (PR-06)
        pag_bar = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Anterior", self)
        self.btn_prev.clicked.connect(self._pagina_anterior)
        self.lbl_paginacion = QLabel("Página 1 de 1", self)
        self.btn_next = QPushButton("Siguiente ▶", self)
        self.btn_next.clicked.connect(self._pagina_siguiente)

        pag_bar.addStretch()
        pag_bar.addWidget(self.btn_prev)
        pag_bar.addWidget(self.lbl_paginacion)
        pag_bar.addWidget(self.btn_next)
        pag_bar.addStretch()
        layout.addLayout(pag_bar)

    def _al_cambiar_busqueda(self):
        self.pagina_actual = 0
        self.cargar_clientes()

    def _pagina_anterior(self):
        if self.pagina_actual > 0:
            self.pagina_actual -= 1
            self.cargar_clientes()

    def _pagina_siguiente(self):
        if self.pagina_actual < self.total_paginas - 1:
            self.pagina_actual += 1
            self.cargar_clientes()

    def cargar_clientes(self):
        """Carga clientes aplicando filtro y paginación (PR-06)."""
        termino = f"%{self.txt_buscar.text().strip()}%"
        offset = self.pagina_actual * self.tamanio_pagina

        try:
            conn = db_manager.get_connection()
            # Conteo total
            c_cur = conn.execute(
                """
                SELECT COUNT(*) FROM clientes
                WHERE numero_documento LIKE ? OR (nombres || ' ' || apellidos) LIKE ?
                """,
                (termino, termino)
            )
            total = c_cur.fetchone()[0]
            self.total_paginas = max(1, (total + self.tamanio_pagina - 1) // self.tamanio_pagina)
            self.lbl_paginacion.setText(f"Página {self.pagina_actual + 1} de {self.total_paginas} (Total: {total} clientes)")

            self.btn_prev.setEnabled(self.pagina_actual > 0)
            self.btn_next.setEnabled(self.pagina_actual < self.total_paginas - 1)

            # Consulta paginada
            cur = conn.execute(
                """
                SELECT * FROM clientes
                WHERE numero_documento LIKE ? OR (nombres || ' ' || apellidos) LIKE ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (termino, termino, self.tamanio_pagina, offset)
            )
            rows = cur.fetchall()
            conn.close()

            self.tabla.setRowCount(len(rows))
            for i, r in enumerate(rows):
                self.tabla.setItem(i, 0, QTableWidgetItem(str(r["id"])))
                self.tabla.setItem(i, 1, QTableWidgetItem(f"{r['tipo_documento']} {r['numero_documento']}"))
                self.tabla.setItem(i, 2, QTableWidgetItem(f"{r['nombres']} {r['apellidos']}"))
                self.tabla.setItem(i, 3, QTableWidgetItem(r["telefono"]))
                self.tabla.setItem(i, 4, QTableWidgetItem(r["correo"]))
                self.tabla.setItem(i, 5, QTableWidgetItem(f"${float(r['ingresos_mensuales']):,.2f}"))

                # Estado
                estado_lbl = "Activo" if r["activo"] else "Inactivo"
                self.tabla.setItem(i, 6, QTableWidgetItem(estado_lbl))

                # Botón de edición
                btn_edit = QPushButton("Editar", self)
                btn_edit.setStyleSheet("padding: 3px 8px; font-size: 11px;")
                btn_edit.clicked.connect(lambda checked, data=dict(r): self._editar_cliente(data))
                self.tabla.setCellWidget(i, 7, btn_edit)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Fallo al cargar clientes: {e}")

    def _nuevo_cliente(self):
        dlg = ClienteDialog(self)
        if dlg.exec():
            self.cargar_clientes()

    def _editar_cliente(self, cliente_data: dict):
        dlg = ClienteDialog(self, cliente_data=cliente_data)
        if dlg.exec():
            self.cargar_clientes()
