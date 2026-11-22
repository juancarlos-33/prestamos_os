"""
Vista de Generación de Reportes Gerenciales y Exportación Multiformato (ReportesView).
Cumple con:
- SO-02 / Criterio 5: Operación asíncrona mediante QThread (evita congelar la UI ante reportes extensos).
- PR-21: Generación de plan de pagos y amortización en PDF.
- PR-22: Reportes gerenciales (cartera vigente, mora y recaudo por fechas).
- PR-23: Encabezado institucional con fecha, emisor y numeración de página.
- PR-24: Exportación a archivos CSV.
"""

import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QGroupBox, QFormLayout, QMessageBox,
    QProgressBar, QSpinBox, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QDate

from src.core.pdf_service import PDFService
from src.core.csv_exporter import CSVExporter
from src.database.db_manager import db_manager


class ReporteWorker(QObject):
    """
    Trabajador asíncrono para generación de reportes y exportaciones en segundo plano.
    Garantiza que la interfaz gráfica no sufra bloqueos (SO-02).
    """
    finished = pyqtSignal(str, str)  # (ruta_archivo, tipo_formato)
    error = pyqtSignal(str)

    def __init__(self, tipo_reporte: str, formato: str, params: Dict[str, Any]):
        super().__init__()
        self.tipo_reporte = tipo_reporte
        self.formato = formato
        self.params = params

    def ejecutar(self):
        try:
            emisor = self.params.get("usuario_emisor", "Administrador")
            archivo_generado: Optional[Path] = None

            if self.formato == "PDF":
                if self.tipo_reporte == "CARTERA_VIGENTE":
                    archivo_generado = PDFService.generar_reporte_cartera_vigente(emisor)
                elif self.tipo_reporte == "CARTERA_MORA":
                    archivo_generado = PDFService.generar_reporte_cartera_en_mora(emisor)
                elif self.tipo_reporte == "RECAUDO_FECHAS":
                    f_ini = self.params["fecha_inicio"]
                    f_fin = self.params["fecha_fin"]
                    archivo_generado = PDFService.generar_reporte_recaudo_rango(f_ini, f_fin, emisor)
                elif self.tipo_reporte == "AMORTIZACION_PRESTAMO":
                    prestamo_id = self.params["prestamo_id"]
                    archivo_generado = PDFService.generar_pdf_tabla_amortizacion_prestamo(prestamo_id, emisor)

            elif self.formato == "CSV":
                if self.tipo_reporte == "CARTERA_VIGENTE":
                    archivo_generado = CSVExporter.exportar_cartera_vigente()
                elif self.tipo_reporte == "CARTERA_MORA":
                    archivo_generado = CSVExporter.exportar_cartera_en_mora()
                elif self.tipo_reporte == "RECAUDO_FECHAS":
                    f_ini = self.params["fecha_inicio"]
                    f_fin = self.params["fecha_fin"]
                    archivo_generado = CSVExporter.exportar_recaudo_rango(f_ini, f_fin)

            if archivo_generado:
                self.finished.emit(str(archivo_generado), self.formato)
            else:
                self.error.emit("No se pudo determinar el tipo de reporte solicitado.")

        except Exception as e:
            self.error.emit(str(e))


class ReportesView(QWidget):
    """Pestaña de emisión de reportes contables y exportación."""

    def __init__(self, parent=None, user_session: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.user_session = user_session or {"id": 1, "username": "admin", "rol": "ADMINISTRADOR", "nombre_completo": "Administrador"}
        self.thread: Optional[QThread] = None
        self.worker: Optional[ReporteWorker] = None
        self.ultimo_archivo: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Encabezado
        lbl_titulo = QLabel("Emisión de Reportes Gerenciales y Exportación de Datos", self)
        lbl_titulo.setStyleSheet("font-size: 16px; font-weight: bold; color: #1e293b;")
        layout.addWidget(lbl_titulo)

        lbl_desc = QLabel(
            "Genere informes oficiales en PDF con formato institucional o exporte datos a CSV "
            "procesados en segundo plano sin congelar la aplicación.",
            self
        )
        lbl_desc.setStyleSheet("color: #64748b; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(lbl_desc)

        # Panel de Opciones
        box_opciones = QGroupBox("Parámetros del Reporte", self)
        form = QFormLayout(box_opciones)
        form.setSpacing(12)

        # Selector de Tipo de Reporte
        self.cb_reporte = QComboBox(self)
        self.cb_reporte.addItem("Cartera Vigente (Préstamos Activos)", "CARTERA_VIGENTE")
        self.cb_reporte.addItem("Cartera en Mora y Liquidación Diaria", "CARTERA_MORA")
        self.cb_reporte.addItem("Recaudo Consolidado por Rango de Fechas", "RECAUDO_FECHAS")
        self.cb_reporte.addItem("Tabla de Amortización Oficial de un Préstamo", "AMORTIZACION_PRESTAMO")
        self.cb_reporte.currentIndexChanged.connect(self._al_cambiar_tipo_reporte)
        form.addRow("Tipo de Reporte (*):", self.cb_reporte)

        # Controles de Fechas (para recaudo)
        self.widget_fechas = QWidget(self)
        h_fechas = QHBoxLayout(self.widget_fechas)
        h_fechas.setContentsMargins(0, 0, 0, 0)
        self.dt_inicio = QDateEdit(self)
        self.dt_inicio.setCalendarPopup(True)
        self.dt_inicio.setDate(QDate.currentDate().addDays(-30))
        self.dt_fin = QDateEdit(self)
        self.dt_fin.setCalendarPopup(True)
        self.dt_fin.setDate(QDate.currentDate())
        h_fechas.addWidget(QLabel("Desde:"))
        h_fechas.addWidget(self.dt_inicio)
        h_fechas.addWidget(QLabel("Hasta:"))
        h_fechas.addWidget(self.dt_fin)
        form.addRow("Rango de Fechas:", self.widget_fechas)
        self.widget_fechas.setVisible(False)

        # Control de Préstamo Específico
        self.widget_prestamo = QWidget(self)
        h_prestamo = QHBoxLayout(self.widget_prestamo)
        h_prestamo.setContentsMargins(0, 0, 0, 0)
        self.sp_prestamo_id = QSpinBox(self)
        self.sp_prestamo_id.setRange(1, 999999)
        self.sp_prestamo_id.setValue(1)
        h_prestamo.addWidget(self.sp_prestamo_id)
        form.addRow("ID del Préstamo:", self.widget_prestamo)
        self.widget_prestamo.setVisible(False)

        layout.addWidget(box_opciones)

        # Barra de progreso y estado
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)  # Modo indeterminado durante la ejecución del hilo
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_estado = QLabel("", self)
        self.lbl_estado.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(self.lbl_estado)

        # Botones de Acción
        btn_layout = QHBoxLayout()

        self.btn_generar_pdf = QPushButton("📄 Generar Reporte PDF (ReportLab)", self)
        self.btn_generar_pdf.setStyleSheet(
            "background-color: #2563eb; color: white; padding: 10px 18px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_generar_pdf.clicked.connect(lambda: self._iniciar_generacion("PDF"))

        self.btn_exportar_csv = QPushButton("📊 Exportar a CSV", self)
        self.btn_exportar_csv.setStyleSheet(
            "background-color: #059669; color: white; padding: 10px 18px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_exportar_csv.clicked.connect(lambda: self._iniciar_generacion("CSV"))

        self.btn_abrir_archivo = QPushButton("📂 Abrir Archivo Generado", self)
        self.btn_abrir_archivo.setEnabled(False)
        self.btn_abrir_archivo.clicked.connect(self._abrir_archivo_generado)

        btn_layout.addWidget(self.btn_generar_pdf)
        btn_layout.addWidget(self.btn_exportar_csv)
        btn_layout.addWidget(self.btn_abrir_archivo)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)
        layout.addStretch()

    def _al_cambiar_tipo_reporte(self, index: int):
        data = self.cb_reporte.currentData()
        self.widget_fechas.setVisible(data == "RECAUDO_FECHAS")
        self.widget_prestamo.setVisible(data == "AMORTIZACION_PRESTAMO")
        self.btn_exportar_csv.setEnabled(data != "AMORTIZACION_PRESTAMO")

    def _iniciar_generacion(self, formato: str):
        tipo = self.cb_reporte.currentData()
        params = {
            "usuario_emisor": self.user_session.get("nombre_completo", "Administrador"),
            "prestamo_id": self.sp_prestamo_id.value(),
        }

        if tipo == "RECAUDO_FECHAS":
            q_ini = self.dt_inicio.date()
            q_fin = self.dt_fin.date()
            params["fecha_inicio"] = date(q_ini.year(), q_ini.month(), q_ini.day())
            params["fecha_fin"] = date(q_fin.year(), q_fin.month(), q_fin.day())

        # Bloquear botones para evitar múltiples clics concurrentes
        self.btn_generar_pdf.setEnabled(False)
        self.btn_exportar_csv.setEnabled(False)
        self.btn_abrir_archivo.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_estado.setText(f"⏳ Procesando {tipo} en formato {formato} mediante hilo secundario...")
        self.lbl_estado.setStyleSheet("color: #2563eb;")

        # Ejecución en hilo secundario QThread (SO-02)
        self.thread = QThread(self)
        self.worker = ReporteWorker(tipo, formato, params)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.ejecutar)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.error.connect(self._on_worker_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)

        self.thread.start()

    def _on_worker_finished(self, archivo_path: str, formato: str):
        self.progress_bar.setVisible(False)
        self.btn_generar_pdf.setEnabled(True)
        self.btn_exportar_csv.setEnabled(self.cb_reporte.currentData() != "AMORTIZACION_PRESTAMO")
        self.btn_abrir_archivo.setEnabled(True)
        self.ultimo_archivo = archivo_path

        p = Path(archivo_path)
        self.lbl_estado.setText(f"✓ Archivo {formato} generado exitosamente: {p.name}")
        self.lbl_estado.setStyleSheet("color: #16a34a;")

        QMessageBox.information(
            self,
            "Reporte Generado",
            f"El archivo {formato} se guardó correctamente en:\n{archivo_path}"
        )

    def _on_worker_error(self, err_msg: str):
        self.progress_bar.setVisible(False)
        self.btn_generar_pdf.setEnabled(True)
        self.btn_exportar_csv.setEnabled(True)
        self.lbl_estado.setText(f"✕ Error en la generación: {err_msg}")
        self.lbl_estado.setStyleSheet("color: #dc2626;")
        QMessageBox.critical(self, "Error Generando Reporte", f"Ocurrió un error: {err_msg}")

    def _abrir_archivo_generado(self):
        if not self.ultimo_archivo or not Path(self.ultimo_archivo).exists():
            return

        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", self.ultimo_archivo])
        elif sys.platform == "win32":
            os.startfile(self.ultimo_archivo)
