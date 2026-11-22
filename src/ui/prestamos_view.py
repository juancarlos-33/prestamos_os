"""
Vista de Gestión y Simulación de Préstamos (PrestamosView).
Cumple con:
- PR-07: Registro de préstamos con monto, tasa, cuotas, periodicidad y desembolso.
- PR-08: Métodos de amortización Francés, Alemán y Simple.
- PR-09: Simulador interactivo previo al desembolso (cuota, intereses, total a pagar).
- PR-10: Comisiones o seguros opcionales (fijo o porcentaje).
- PR-11: Impedir préstamo si el cliente supera el umbral de mora.
- PR-12: Estados del préstamo (Simulado, Activo, En Mora, Cancelado).
- PR-13: Generación y visualización automática de la tabla de amortización.
"""

from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox, QGroupBox,
    QFormLayout, QSplitter
)
from PyQt6.QtCore import Qt, QDate

from src.core.loan_engine import (
    LoanEngine, SistemaAmortizacion, TipoTasa, Periodicidad, TipoSeguro, ResumenPrestamo
)
from src.database.db_manager import db_manager
from src.config import config_app


class PrestamosView(QWidget):
    """Pestaña de simulación, aprobación y desembolso de préstamos."""

    def __init__(self, parent=None, user_session: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.user_session = user_session or {"id": 1, "username": "admin", "rol": "ADMINISTRADOR"}
        self.resumen_actual: Optional[ResumenPrestamo] = None
        self._setup_ui()
        self.actualizar_lista_clientes()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Panel Izquierdo: Formulario de Parámetros y Simulación
        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)

        group_params = QGroupBox("Parámetros del Crédito", self)
        form = QFormLayout(group_params)
        form.setSpacing(10)

        # Selector de Cliente
        self.cb_cliente = QComboBox(self)
        form.addRow("Cliente (*):", self.cb_cliente)

        # Monto
        self.sp_monto = QDoubleSpinBox(self)
        self.sp_monto.setRange(100000.0, 500000000.0)
        self.sp_monto.setValue(10000000.0)
        self.sp_monto.setSingleStep(500000.0)
        self.sp_monto.setPrefix("$ ")
        form.addRow("Monto a Prestar (*):", self.sp_monto)

        # Sistema de Amortización
        self.cb_sistema = QComboBox(self)
        self.cb_sistema.addItem("Francés (Cuota Fija)", SistemaAmortizacion.FRANCES)
        self.cb_sistema.addItem("Alemán (Abono Constante)", SistemaAmortizacion.ALEMAN)
        self.cb_sistema.addItem("Interés Simple", SistemaAmortizacion.SIMPLE)
        form.addRow("Método Amortización (*):", self.cb_sistema)

        # Tasa de Interés y Tipo
        h_tasa = QHBoxLayout()
        self.sp_tasa = QDoubleSpinBox(self)
        self.sp_tasa.setRange(0.0, 100.0)
        self.sp_tasa.setValue(18.0)
        self.sp_tasa.setSuffix(" %")
        self.cb_tipo_tasa = QComboBox(self)
        self.cb_tipo_tasa.addItem("Anual", TipoTasa.ANUAL)
        self.cb_tipo_tasa.addItem("Mensual", TipoTasa.MENSUAL)
        h_tasa.addWidget(self.sp_tasa)
        h_tasa.addWidget(self.cb_tipo_tasa)
        form.addRow("Tasa de Interés (*):", h_tasa)

        # Plazo / Cuotas
        self.sp_cuotas = QSpinBox(self)
        self.sp_cuotas.setRange(1, 120)
        self.sp_cuotas.setValue(12)
        form.addRow("Número de Cuotas (*):", self.sp_cuotas)

        # Periodicidad
        self.cb_periodicidad = QComboBox(self)
        self.cb_periodicidad.addItem("Mensual", Periodicidad.MENSUAL)
        self.cb_periodicidad.addItem("Quincenal", Periodicidad.QUINCENAL)
        self.cb_periodicidad.addItem("Semanal", Periodicidad.SEMANAL)
        form.addRow("Periodicidad (*):", self.cb_periodicidad)

        # Seguro o Comisión Adicional
        h_seguro = QHBoxLayout()
        self.sp_seguro = QDoubleSpinBox(self)
        self.sp_seguro.setRange(0.0, 1000000.0)
        self.sp_seguro.setValue(0.0)
        self.cb_tipo_seguro = QComboBox(self)
        self.cb_tipo_seguro.addItem("Valor Fijo ($)", TipoSeguro.FIJO)
        self.cb_tipo_seguro.addItem("Porcentaje (%)", TipoSeguro.PORCENTAJE)
        h_seguro.addWidget(self.sp_seguro)
        h_seguro.addWidget(self.cb_tipo_seguro)
        form.addRow("Seguro / Comisión:", h_seguro)

        # Fecha Desembolso
        self.dt_desembolso = QDateEdit(self)
        self.dt_desembolso.setCalendarPopup(True)
        self.dt_desembolso.setDate(QDate.currentDate())
        form.addRow("Fecha Desembolso:", self.dt_desembolso)

        left_layout.addWidget(group_params)

        # Botón Simular (PR-09)
        self.btn_simular = QPushButton("▶ Calcular y Simular Tabla", self)
        self.btn_simular.setStyleSheet("background-color: #0284c7; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")
        self.btn_simular.clicked.connect(self._calcular_simulacion)
        left_layout.addWidget(self.btn_simular)

        # Tarjeta de Resumen Financiero
        self.group_resumen = QGroupBox("Resumen de Simulación", self)
        res_layout = QFormLayout(self.group_resumen)
        self.lbl_cuota_ref = QLabel("$ 0.00", self)
        self.lbl_cuota_ref.setStyleSheet("font-size: 15px; font-weight: bold; color: #2563eb;")
        self.lbl_total_int = QLabel("$ 0.00", self)
        self.lbl_total_cargos = QLabel("$ 0.00", self)
        self.lbl_total_pagar = QLabel("$ 0.00", self)
        self.lbl_total_pagar.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f172a;")

        res_layout.addRow("Cuota Estimada:", self.lbl_cuota_ref)
        res_layout.addRow("Total Intereses:", self.lbl_total_int)
        res_layout.addRow("Total Seguros/Cargos:", self.lbl_total_cargos)
        res_layout.addRow("Total a Liquidar:", self.lbl_total_pagar)

        left_layout.addWidget(self.group_resumen)

        # Botón Desembolsar
        self.btn_desembolsar = QPushButton("✓ Aprobar y Desembolsar Crédito", self)
        self.btn_desembolsar.setEnabled(False)
        self.btn_desembolsar.setStyleSheet("background-color: #16a34a; color: white; padding: 12px; font-weight: bold; font-size: 13px; border-radius: 4px;")
        self.btn_desembolsar.clicked.connect(self._aprobar_desembolso)
        left_layout.addWidget(self.btn_desembolsar)

        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # Panel Derecho: Tabla Visual de Amortización
        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)

        lbl_tabla_title = QLabel("Calendario y Tabla de Amortización", self)
        lbl_tabla_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #334155; margin-bottom: 5px;")
        right_layout.addWidget(lbl_tabla_title)

        self.tabla_amort = QTableWidget(self)
        self.tabla_amort.setColumnCount(7)
        self.tabla_amort.setHorizontalHeaderLabels([
            "Cuota #", "Vencimiento", "Abono Capital", "Interés", "Cargos", "Cuota Total", "Saldo Restante"
        ])
        self.tabla_amort.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla_amort.setAlternatingRowColors(True)
        right_layout.addWidget(self.tabla_amort)

        splitter.addWidget(right_panel)
        splitter.setSizes([380, 620])

        main_layout.addWidget(splitter)

    def actualizar_lista_clientes(self):
        """Llena el combo de clientes activos."""
        self.cb_cliente.clear()
        try:
            conn = db_manager.get_connection()
            cur = conn.execute("SELECT id, tipo_documento, numero_documento, nombres, apellidos FROM clientes WHERE activo = 1 ORDER BY nombres ASC")
            for r in cur.fetchall():
                texto = f"{r['nombres']} {r['apellidos']} ({r['tipo_documento']} {r['numero_documento']})"
                self.cb_cliente.addItem(texto, r["id"])
            conn.close()
        except Exception as e:
            print(f"[ERROR PRESTAMOS] Error listando clientes: {e}")

    def _calcular_simulacion(self):
        """Ejecuta el cálculo en el motor financiero y renderiza la tabla (PR-09)."""
        monto = Decimal(str(self.sp_monto.value()))
        tasa = Decimal(str(self.sp_tasa.value()))
        tipo_tasa = self.cb_tipo_tasa.currentData()
        cuotas = self.sp_cuotas.value()
        periodicidad = self.cb_periodicidad.currentData()
        sistema = self.cb_sistema.currentData()
        seguro = Decimal(str(self.sp_seguro.value()))
        tipo_seguro = self.cb_tipo_seguro.currentData()

        qdate = self.dt_desembolso.date()
        fecha_desemb = date(qdate.year(), qdate.month(), qdate.day())

        # Cargar feriados configurados desde BD
        feriados = set()
        try:
            conn = db_manager.get_connection()
            cur = conn.execute("SELECT fecha FROM feriados")
            for r in cur.fetchall():
                y, m, d = map(int, str(r["fecha"]).split("-"))
                feriados.add(date(y, m, d))
            conn.close()
        except Exception:
            pass

        try:
            self.resumen_actual = LoanEngine.generar_tabla_amortizacion(
                monto=monto,
                tasa_interes=tasa,
                tipo_tasa=tipo_tasa,
                num_cuotas=cuotas,
                periodicidad=periodicidad,
                sistema=sistema,
                fecha_desembolso=fecha_desemb,
                seguro_comision=seguro,
                tipo_seguro=tipo_seguro,
                feriados=feriados,
            )

            # Actualizar tarjetas de resumen
            cuota_txt = f"${self.resumen_actual.cuota_fija_referencial:,.2f}" if self.resumen_actual.cuota_fija_referencial else "Variable"
            self.lbl_cuota_ref.setText(cuota_txt)
            self.lbl_total_int.setText(f"${self.resumen_actual.total_intereses:,.2f}")
            self.lbl_total_cargos.setText(f"${self.resumen_actual.total_cargos:,.2f}")
            self.lbl_total_pagar.setText(f"${self.resumen_actual.total_a_pagar:,.2f}")

            # Poblar tabla de amortización
            self.tabla_amort.setRowCount(len(self.resumen_actual.cuotas))
            for i, c in enumerate(self.resumen_actual.cuotas):
                self.tabla_amort.setItem(i, 0, QTableWidgetItem(str(c.numero_cuota)))
                self.tabla_amort.setItem(i, 1, QTableWidgetItem(c.fecha_vencimiento.strftime("%Y-%m-%d")))
                self.tabla_amort.setItem(i, 2, QTableWidgetItem(f"${c.abono_capital:,.2f}"))
                self.tabla_amort.setItem(i, 3, QTableWidgetItem(f"${c.interes_corriente:,.2f}"))
                self.tabla_amort.setItem(i, 4, QTableWidgetItem(f"${c.cargo_adicional:,.2f}"))
                self.tabla_amort.setItem(i, 5, QTableWidgetItem(f"${c.cuota_total:,.2f}"))
                self.tabla_amort.setItem(i, 6, QTableWidgetItem(f"${c.saldo_restante:,.2f}"))

            self.btn_desembolsar.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "Error en Simulación", f"No se pudo generar la tabla: {e}")
            self.btn_desembolsar.setEnabled(False)

    def _verificar_mora_cliente(self, cliente_id: int) -> bool:
        """Verifica que el cliente no tenga mora superior al umbral (PR-11)."""
        umbral_dias = config_app.config_data.get("parametros_prestamo", {}).get("umbral_dias_mora_bloqueo", 30)
        hoy = date.today()

        try:
            conn = db_manager.get_connection()
            cur = conn.execute(
                """
                SELECT c.fecha_vencimiento
                FROM cuotas_amortizacion c
                JOIN prestamos p ON c.prestamo_id = p.id
                WHERE p.cliente_id = ? AND c.estado IN ('PENDIENTE', 'EN_MORA') AND c.fecha_vencimiento < ?
                ORDER BY c.fecha_vencimiento ASC
                LIMIT 1
                """,
                (cliente_id, hoy.isoformat())
            )
            row = cur.fetchone()
            conn.close()

            if row:
                y, m, d = map(int, str(row["fecha_vencimiento"]).split("-"))
                venc = date(y, m, d)
                dias_mora = (hoy - venc).days
                if dias_mora > umbral_dias:
                    QMessageBox.warning(
                        self,
                        "Crédito Denegado (PR-11)",
                        f"El cliente presenta una cuota en mora con {dias_mora} días de retraso "
                        f"(Umbral máximo permitido: {umbral_dias} días). Debe ponerse al día antes de solicitar un nuevo préstamo."
                    )
                    return False
            return True
        except Exception as e:
            print(f"[PR-11] Error verificando mora: {e}")
            return True

    def _aprobar_desembolso(self):
        """Persiste el préstamo y su calendario en la base de datos."""
        if not self.resumen_actual:
            return

        cliente_id = self.cb_cliente.currentData()
        if not cliente_id:
            QMessageBox.warning(self, "Validación", "Debe seleccionar un cliente.")
            return

        # PR-11: Verificar mora
        if not self._verificar_mora_cliente(cliente_id):
            return

        confirm = QMessageBox.question(
            self,
            "Confirmar Desembolso",
            f"¿Desea aprobar y desembolsar el préstamo por ${self.resumen_actual.monto_solicitado:,.2f}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        monto = self.resumen_actual.monto_solicitado
        tasa = Decimal(str(self.sp_tasa.value()))
        tipo_tasa = self.cb_tipo_tasa.currentData().value
        plazo = self.sp_cuotas.value()
        periodicidad = self.cb_periodicidad.currentData().value
        sistema = self.cb_sistema.currentData().value
        seguro = Decimal(str(self.sp_seguro.value()))
        tipo_seguro = self.cb_tipo_seguro.currentData().value
        desembolso_str = self.dt_desembolso.date().toString("yyyy-MM-dd")

        try:
            with db_manager.transaction() as conn:
                # 1. Insertar préstamo en estado ACTIVO
                cur = conn.execute(
                    """
                    INSERT INTO prestamos (
                        cliente_id, usuario_id, monto_solicitado, tasa_interes, tipo_tasa,
                        plazo_cuotas, periodicidad, sistema_amortizacion, seguro_comision,
                        tipo_seguro, fecha_desembolso, estado, saldo_capital_actual
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVO', ?)
                    """,
                    (
                        cliente_id, self.user_session["id"], str(monto), str(tasa), tipo_tasa,
                        plazo, periodicidad, sistema, str(seguro), tipo_seguro, desembolso_str, str(monto)
                    )
                )
                prestamo_id = cur.lastrowid

                # 2. Insertar cada una de las cuotas de amortización
                for c in self.resumen_actual.cuotas:
                    conn.execute(
                        """
                        INSERT INTO cuotas_amortizacion (
                            prestamo_id, numero_cuota, fecha_vencimiento, abono_capital,
                            interes_corriente, cargo_adicional, cuota_total, saldo_restante,
                            estado, saldo_pendiente_cuota
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE', ?)
                        """,
                        (
                            prestamo_id, c.numero_cuota, c.fecha_vencimiento.isoformat(),
                            str(c.abono_capital), str(c.interes_corriente), str(c.cargo_adicional),
                            str(c.cuota_total), str(c.saldo_restante), str(c.cuota_total)
                        )
                    )

            QMessageBox.information(
                self,
                "Desembolso Exitoso",
                f"El préstamo #{prestamo_id} ha sido aprobado y desembolsado exitosamente con sus {plazo} cuotas."
            )
            self.btn_desembolsar.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(self, "Error en Desembolso", f"Fallo al registrar desembolso: {e}")
