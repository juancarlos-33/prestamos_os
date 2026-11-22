"""
Vista de Pagos y Recaudos (PagosView).
Cumple con:
- PR-17: Registrar pagos totales, parciales o adelantados con fecha, monto y método.
- PR-18: Aplicar los pagos en orden: mora, interés y capital; recalcular saldo.
- PR-19: Calcular interés moratorio diario con tasa configurable.
- PR-20: Emitir comprobante de pago en PDF.
"""

import os
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QComboBox, QDoubleSpinBox, QGroupBox, QFormLayout, QSplitter
)
from PyQt6.QtCore import Qt

from src.core.loan_engine import LoanEngine, round_money
from src.core.pdf_service import PDFService
from src.database.db_manager import db_manager
from src.config import config_app


class PagosView(QWidget):
    """Pestaña de registro y liquidación de cuotas de préstamos."""

    def __init__(self, parent=None, user_session: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.user_session = user_session or {"id": 1, "username": "admin", "rol": "ADMINISTRADOR"}
        self.prestamo_seleccionado: Optional[Dict[str, Any]] = None
        self._setup_ui()
        self.cargar_prestamos_activos()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Panel Izquierdo: Lista de Préstamos Activos y en Mora
        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)

        lbl_lista = QLabel("Préstamos Activos y en Cartera", self)
        lbl_lista.setStyleSheet("font-weight: bold; font-size: 13px; color: #334155;")
        left_layout.addWidget(lbl_lista)

        self.tabla_prestamos = QTableWidget(self)
        self.tabla_prestamos.setColumnCount(5)
        self.tabla_prestamos.setHorizontalHeaderLabels(["ID", "Cliente", "Saldo Capital", "Estado", "Cuotas"])
        self.tabla_prestamos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_prestamos.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_prestamos.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_prestamos.itemSelectionChanged.connect(self._al_seleccionar_prestamo)
        left_layout.addWidget(self.tabla_prestamos)

        btn_refrescar = QPushButton("🔄 Actualizar Lista de Préstamos", self)
        btn_refrescar.clicked.connect(self.cargar_prestamos_activos)
        left_layout.addWidget(btn_refrescar)

        splitter.addWidget(left_panel)

        # Panel Derecho: Registro de Pago y Liquidación
        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)

        # Información del Préstamo Seleccionado
        self.group_info = QGroupBox("Estado de Cuenta del Préstamo", self)
        info_form = QFormLayout(self.group_info)
        self.lbl_info_cliente = QLabel("Seleccione un préstamo...", self)
        self.lbl_info_saldo = QLabel("$ 0.00", self)
        self.lbl_info_mora = QLabel("$ 0.00 (0 días)", self)
        self.lbl_info_proxima = QLabel("-", self)

        info_form.addRow("Titular:", self.lbl_info_cliente)
        info_form.addRow("Saldo de Capital:", self.lbl_info_saldo)
        info_form.addRow("Mora Acumulada:", self.lbl_info_mora)
        info_form.addRow("Próxima Cuota / Vencimiento:", self.lbl_info_proxima)
        right_layout.addWidget(self.group_info)

        # Formulario de Liquidación
        group_pago = QGroupBox("Registrar Abono o Cancelación", self)
        pago_form = QFormLayout(group_pago)

        self.sp_monto_pago = QDoubleSpinBox(self)
        self.sp_monto_pago.setRange(100.0, 500000000.0)
        self.sp_monto_pago.setValue(100000.0)
        self.sp_monto_pago.setSingleStep(50000.0)
        self.sp_monto_pago.setPrefix("$ ")
        self.sp_monto_pago.valueChanged.connect(self._recalcular_previa_pago)
        pago_form.addRow("Monto a Pagar (*):", self.sp_monto_pago)

        self.cb_metodo = QComboBox(self)
        self.cb_metodo.addItems(["EFECTIVO", "TRANSFERENCIA", "CHEQUE"])
        pago_form.addRow("Método de Pago (*):", self.cb_metodo)

        # Desglose previo
        self.lbl_prev_mora = QLabel("$ 0.00", self)
        self.lbl_prev_interes = QLabel("$ 0.00", self)
        self.lbl_prev_capital = QLabel("$ 0.00", self)
        self.lbl_prev_nuevo_saldo = QLabel("$ 0.00", self)

        pago_form.addRow("→ Aplicado a Mora:", self.lbl_prev_mora)
        pago_form.addRow("→ Aplicado a Interés:", self.lbl_prev_interes)
        pago_form.addRow("→ Aplicado a Capital:", self.lbl_prev_capital)
        pago_form.addRow("→ Saldo Resultante:", self.lbl_prev_nuevo_saldo)

        right_layout.addWidget(group_pago)

        # Botón de Procesar Pago
        self.btn_procesar = QPushButton("💳 Confirmar Pago y Generar Comprobante PDF", self)
        self.btn_procesar.setEnabled(False)
        self.btn_procesar.setStyleSheet(
            "background-color: #2563eb; color: white; padding: 12px; font-weight: bold; font-size: 13px; border-radius: 4px;"
        )
        self.btn_procesar.clicked.connect(self._procesar_pago)
        right_layout.addWidget(self.btn_procesar)

        right_layout.addStretch()
        splitter.addWidget(right_panel)
        splitter.setSizes([450, 550])

        main_layout.addWidget(splitter)

    def cargar_prestamos_activos(self):
        """Carga préstamos en estado ACTIVO o EN_MORA."""
        try:
            conn = db_manager.get_connection()
            cur = conn.execute(
                """
                SELECT p.id, p.monto_solicitado, p.saldo_capital_actual, p.estado,
                       p.plazo_cuotas, cl.id as cliente_id, cl.tipo_documento, cl.numero_documento,
                       cl.nombres, cl.apellidos
                FROM prestamos p
                JOIN clientes cl ON p.cliente_id = cl.id
                WHERE p.estado IN ('ACTIVO', 'EN_MORA')
                ORDER BY p.id DESC
                """
            )
            rows = cur.fetchall()
            conn.close()

            self.tabla_prestamos.setRowCount(len(rows))
            for i, r in enumerate(rows):
                self.tabla_prestamos.setItem(i, 0, QTableWidgetItem(str(r["id"])))
                self.tabla_prestamos.setItem(i, 1, QTableWidgetItem(f"{r['nombres']} {r['apellidos']}"))
                self.tabla_prestamos.setItem(i, 2, QTableWidgetItem(f"${float(r['saldo_capital_actual']):,.2f}"))
                self.tabla_prestamos.setItem(i, 3, QTableWidgetItem(r["estado"]))
                self.tabla_prestamos.setItem(i, 4, QTableWidgetItem(str(r["plazo_cuotas"])))
                self.tabla_prestamos.item(i, 0).setData(Qt.ItemDataRole.UserRole, dict(r))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error cargando préstamos: {e}")

    def _al_seleccionar_prestamo(self):
        items = self.tabla_prestamos.selectedItems()
        if not items:
            self.prestamo_seleccionado = None
            self.btn_procesar.setEnabled(False)
            return

        row = items[0].row()
        self.prestamo_seleccionado = self.tabla_prestamos.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self._actualizar_detalle_prestamo()

    def _actualizar_detalle_prestamo(self):
        if not self.prestamo_seleccionado:
            return

        p = self.prestamo_seleccionado
        prestamo_id = p["id"]
        saldo_capital = Decimal(str(p["saldo_capital_actual"]))

        self.lbl_info_cliente.setText(f"{p['nombres']} {p['apellidos']} ({p['tipo_documento']} {p['numero_documento']})")
        self.lbl_info_saldo.setText(f"${saldo_capital:,.2f}")

        # Consultar cuotas pendientes
        try:
            conn = db_manager.get_connection()
            cur = conn.execute(
                """
                SELECT id, numero_cuota, fecha_vencimiento, interes_corriente, cargo_adicional, saldo_pendiente_cuota
                FROM cuotas_amortizacion
                WHERE prestamo_id = ? AND estado IN ('PENDIENTE', 'EN_MORA')
                ORDER BY fecha_vencimiento ASC
                LIMIT 1
                """,
                (prestamo_id,)
            )
            primera_cuota = cur.fetchone()
            conn.close()

            tasa_mora = Decimal(str(config_app.config_data.get("parametros_prestamo", {}).get("tasa_mora_anual_defecto", 28.0)))
            hoy = date.today()

            mora_calculada = Decimal("0.00")
            dias_retraso = 0

            if primera_cuota:
                y, m, d = map(int, str(primera_cuota["fecha_vencimiento"]).split("-"))
                f_venc = date(y, m, d)
                if hoy > f_venc:
                    dias_retraso = (hoy - f_venc).days
                    cuota_saldo = Decimal(str(primera_cuota["saldo_pendiente_cuota"]))
                    mora_calculada = LoanEngine.calcular_interes_moratorio_diario(cuota_saldo, tasa_mora, dias_retraso)

                self.lbl_info_proxima.setText(f"Cuota #{primera_cuota['numero_cuota']} - Vence: {primera_cuota['fecha_vencimiento']} (${float(primera_cuota['saldo_pendiente_cuota']):,.2f})")
                self.sp_monto_pago.setValue(float(Decimal(str(primera_cuota['saldo_pendiente_cuota'])) + mora_calculada))
            else:
                self.lbl_info_proxima.setText("No hay cuotas pendientes")
                self.sp_monto_pago.setValue(float(saldo_capital))

            self.lbl_info_mora.setText(f"${mora_calculada:,.2f} ({dias_retraso} días de mora)")

            self.mora_actual = mora_calculada
            self.interes_actual = Decimal(str(primera_cuota["interes_corriente"])) if primera_cuota else Decimal("0.00")
            self.primera_cuota_id = primera_cuota["id"] if primera_cuota else None

            self.btn_procesar.setEnabled(True)
            self._recalcular_previa_pago()

        except Exception as e:
            print(f"[ERROR CUOTAS] {e}")

    def _recalcular_previa_pago(self):
        """Muestra en tiempo real cómo se distribuirá el pago."""
        if not self.prestamo_seleccionado:
            return

        monto = Decimal(str(self.sp_monto_pago.value()))
        saldo_cap = Decimal(str(self.prestamo_seleccionado["saldo_capital_actual"]))

        desglose = LoanEngine.aplicar_pago(
            monto_pago=monto,
            mora_pendiente=getattr(self, "mora_actual", Decimal("0.00")),
            interes_pendiente=getattr(self, "interes_actual", Decimal("0.00")),
            saldo_capital=saldo_cap,
        )

        self.lbl_prev_mora.setText(f"${desglose.mora_cubierta:,.2f}")
        self.lbl_prev_interes.setText(f"${desglose.interes_cubierto:,.2f}")
        self.lbl_prev_capital.setText(f"${desglose.capital_cubierto:,.2f}")
        self.lbl_prev_nuevo_saldo.setText(f"${desglose.nuevo_saldo_capital:,.2f}")

    def _procesar_pago(self):
        if not self.prestamo_seleccionado:
            return

        monto_pago = round_money(Decimal(str(self.sp_monto_pago.value())))
        metodo = self.cb_metodo.currentText()
        p = self.prestamo_seleccionado
        prestamo_id = p["id"]
        saldo_cap = Decimal(str(p["saldo_capital_actual"]))

        desglose = LoanEngine.aplicar_pago(
            monto_pago=monto_pago,
            mora_pendiente=getattr(self, "mora_actual", Decimal("0.00")),
            interes_pendiente=getattr(self, "interes_actual", Decimal("0.00")),
            saldo_capital=saldo_cap,
        )

        recibo_num = f"REC-{prestamo_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        fecha_ahora = datetime.now()

        try:
            with db_manager.transaction() as conn:
                # 1. Registrar el pago
                cur = conn.execute(
                    """
                    INSERT INTO pagos (
                        prestamo_id, usuario_id, fecha_pago, monto_recibido, metodo_pago,
                        numero_recibo, aplicado_mora, aplicado_interes, aplicado_capital
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        prestamo_id, self.user_session["id"], fecha_ahora.strftime("%Y-%m-%d %H:%M:%S"),
                        str(monto_pago), metodo, recibo_num, str(desglose.mora_cubierta),
                        str(desglose.interes_cubierto), str(desglose.capital_cubierto)
                    )
                )
                pago_id = cur.lastrowid

                # 2. Imputar a la cuota si aplica
                if hasattr(self, "primera_cuota_id") and self.primera_cuota_id:
                    conn.execute(
                        """
                        INSERT INTO detalle_pago_cuota (pago_id, cuota_id, monto_aplicado)
                        VALUES (?, ?, ?)
                        """,
                        (pago_id, self.primera_cuota_id, str(monto_pago))
                    )
                    # Si el abono cubrió la cuota, marcarla como PAGADA
                    conn.execute(
                        """
                        UPDATE cuotas_amortizacion
                        SET estado = 'PAGADA', saldo_pendiente_cuota = 0.00
                        WHERE id = ? AND saldo_pendiente_cuota <= ?
                        """,
                        (self.primera_cuota_id, str(monto_pago))
                    )

                # 3. Actualizar saldo del préstamo
                nuevo_estado = "CANCELADO" if desglose.nuevo_saldo_capital <= Decimal("0.00") else "ACTIVO"
                conn.execute(
                    """
                    UPDATE prestamos
                    SET saldo_capital_actual = ?, estado = ?
                    WHERE id = ?
                    """,
                    (str(desglose.nuevo_saldo_capital), nuevo_estado, prestamo_id)
                )

            # 4. Generar Comprobante PDF (PR-20)
            pdf_path = PDFService.generar_comprobante_pago(
                recibo_num=recibo_num,
                fecha_pago=fecha_ahora,
                cliente_nombre=f"{p['nombres']} {p['apellidos']}",
                cliente_doc=f"{p['tipo_documento']} {p['numero_documento']}",
                prestamo_id=prestamo_id,
                monto_recibido=monto_pago,
                desglose_mora=desglose.mora_cubierta,
                desglose_interes=desglose.interes_cubierto,
                desglose_capital=desglose.capital_cubierto,
                nuevo_saldo=desglose.nuevo_saldo_capital,
                metodo_pago=metodo,
                usuario_cajero=self.user_session.get("nombre_completo", "Cajero"),
            )

            # Guardar la ruta en la tabla de pagos
            with db_manager.transaction() as conn:
                conn.execute("UPDATE pagos SET ruta_pdf_comprobante = ? WHERE id = ?", (str(pdf_path), pago_id))

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setWindowTitle("Pago Registrado")
            msg_box.setText(f"Pago por ${monto_pago:,.2f} procesado exitosamente.\nRecibo: {recibo_num}")
            btn_abrir_pdf = msg_box.addButton("Abrir Comprobante PDF", QMessageBox.ButtonRole.ActionRole)
            msg_box.addButton(QMessageBox.StandardButton.Ok)

            msg_box.exec()

            if msg_box.clickedButton() == btn_abrir_pdf:
                # Abrir PDF con el visor predeterminado del sistema (xdg-open en Linux)
                if sys.platform.startswith("linux"):
                    subprocess.Popen(["xdg-open", str(pdf_path)])
                elif sys.platform == "win32":
                    os.startfile(str(pdf_path))

            self.cargar_prestamos_activos()
            self._actualizar_detalle_prestamo()

        except Exception as e:
            QMessageBox.critical(self, "Error Procesando Pago", f"No se pudo registrar el pago: {e}")
