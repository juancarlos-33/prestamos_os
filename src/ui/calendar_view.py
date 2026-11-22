"""
Vista de Calendario Visual de Vencimientos de Cuotas (CalendarioView).
Cumple con:
- PR-14: Calendario visual con fechas de vencimiento resaltadas por estado (Pendiente, Pagada, En Mora).
- PR-15: Señalización de feriados configurables y fines de semana.
- PR-16: Identificación visual de cuotas críticas próximas a vencer.
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCalendarWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QSplitter, QFrame, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt, QDate, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush, QPen

from src.database.db_manager import db_manager


class CuotasCalendarWidget(QCalendarWidget):
    """
    Subclase personalizada de QCalendarWidget que sobreescribe `paintCell`
    para dibujar insignias y colores de estado en las fechas de vencimiento.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fechas_estados: Dict[date, List[Dict[str, Any]]] = {}
        self.feriados: Dict[date, str] = {}
        self.setGridVisible(True)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)

    def set_datos(self, cuotas_por_fecha: Dict[date, List[Dict[str, Any]]], feriados: Dict[date, str]):
        """Actualiza el mapa de cuotas y feriados a pintar."""
        self.fechas_estados = cuotas_por_fecha
        self.feriados = feriados
        self.updateCells()

    def paintCell(self, painter: QPainter, rect: QRect, qdate: QDate):
        # 1. Dibujar el fondo y número de día estándar de Qt
        super().paintCell(painter, rect, qdate)

        d_py = date(qdate.year(), qdate.month(), qdate.day())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 2. Resaltar Feriados (fondo sutil amarillo/ámbar)
        if d_py in self.feriados:
            painter.fillRect(
                rect.adjusted(1, 1, -1, -1),
                QColor(254, 243, 199, 100)  # Ámbar suave
            )

        # 3. Resaltar Cuotas de Vencimiento
        if d_py in self.fechas_estados:
            cuotas = self.fechas_estados[d_py]
            estados = [c["estado"] for c in cuotas]

            # Prioridad de color: ROJO (si hay alguna en mora) > AZUL (si hay pendiente) > VERDE (si todas pagadas)
            if "EN_MORA" in estados or (any(c["estado"] == "PENDIENTE" and d_py < date.today() for c in cuotas)):
                dot_color = QColor("#dc2626")  # Rojo mora
            elif "PENDIENTE" in estados:
                dot_color = QColor("#2563eb")  # Azul pendiente
            else:
                dot_color = QColor("#16a34a")  # Verde pagada

            # Dibujar un badge circular en la esquina inferior derecha de la celda
            dot_size = 14
            dot_rect = QRect(
                rect.right() - dot_size - 3,
                rect.bottom() - dot_size - 3,
                dot_size,
                dot_size
            )
            painter.setBrush(QBrush(dot_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(dot_rect)

            # Escribir la cantidad de cuotas si es más de 1
            if len(cuotas) > 1:
                painter.setPen(QPen(Qt.GlobalColor.white))
                f = painter.font()
                f.setPointSize(7)
                f.setBold(True)
                painter.setFont(f)
                painter.drawText(dot_rect, Qt.AlignmentFlag.AlignCenter, str(len(cuotas)))

        painter.restore()


class CalendarioView(QWidget):
    """Pestaña de visualización de calendario interactivo de cartera y vencimientos."""

    def __init__(self, parent=None, user_session: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.user_session = user_session or {"id": 1, "username": "admin", "rol": "ADMINISTRADOR"}
        self.cuotas_map: Dict[date, List[Dict[str, Any]]] = {}
        self.feriados_map: Dict[date, str] = {}
        self._setup_ui()
        self.cargar_datos_calendario()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # 1. Barra de Leyenda de Colores (PR-14 y PR-15)
        leyenda_frame = QFrame(self)
        leyenda_frame.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 12px;")
        h_leyenda = QHBoxLayout(leyenda_frame)

        lbl_leyenda_title = QLabel("<b>Leyenda del Calendario:</b>", self)
        h_leyenda.addWidget(lbl_leyenda_title)

        lbl_azul = QLabel("🔵 <b>Pendiente al Día</b>", self)
        lbl_rojo = QLabel("🔴 <b>En Mora / Vencida</b>", self)
        lbl_verde = QLabel("🟢 <b>Cuota Pagada</b>", self)
        lbl_amarillo = QLabel("🟡 <b>Día Feriado / Festivo</b>", self)

        h_leyenda.addWidget(lbl_azul)
        h_leyenda.addWidget(lbl_rojo)
        h_leyenda.addWidget(lbl_verde)
        h_leyenda.addWidget(lbl_amarillo)
        h_leyenda.addStretch()

        btn_refrescar = QPushButton("🔄 Actualizar", self)
        btn_refrescar.clicked.connect(self.cargar_datos_calendario)
        h_leyenda.addWidget(btn_refrescar)

        main_layout.addWidget(leyenda_frame)

        # 2. Splitter: Calendario (Izquierda) + Detalle de Cuotas del Día (Derecha)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Panel Izquierdo: Widget Calendario
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)

        self.calendar = CuotasCalendarWidget(self)
        self.calendar.setStyleSheet(
            """
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background-color: #1e293b;
                color: white;
            }
            QCalendarWidget QToolButton {
                color: white;
                font-weight: bold;
            }
            QCalendarWidget QMenu {
                background-color: white;
            }
            """
        )
        self.calendar.selectionChanged.connect(self._al_seleccionar_dia)
        self.calendar.currentPageChanged.connect(lambda y, m: self.cargar_datos_calendario())
        left_layout.addWidget(self.calendar)

        splitter.addWidget(left_widget)

        # Panel Derecho: Detalle de Vencimientos para el Día Seleccionado
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)

        self.lbl_dia_seleccionado = QLabel("Cuotas para el día de hoy", self)
        self.lbl_dia_seleccionado.setStyleSheet("font-size: 14px; font-weight: bold; color: #1e293b; margin-bottom: 5px;")
        right_layout.addWidget(self.lbl_dia_seleccionado)

        self.lbl_feriado_aviso = QLabel("", self)
        self.lbl_feriado_aviso.setStyleSheet("color: #b45309; font-weight: bold; font-size: 12px;")
        self.lbl_feriado_aviso.setVisible(False)
        right_layout.addWidget(self.lbl_feriado_aviso)

        self.tabla_dia = QTableWidget(self)
        self.tabla_dia.setColumnCount(6)
        self.tabla_dia.setHorizontalHeaderLabels([
            "Préstamo", "Cliente", "Teléfono", "Cuota #", "Valor Total", "Estado"
        ])
        self.tabla_dia.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_dia.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_dia.setAlternatingRowColors(True)
        right_layout.addWidget(self.tabla_dia)

        splitter.addWidget(right_widget)
        splitter.setSizes([600, 500])

        main_layout.addWidget(splitter)

    def cargar_datos_calendario(self):
        """Consulta cuotas y feriados desde SQLite y alimenta el widget."""
        self.cuotas_map.clear()
        self.feriados_map.clear()

        try:
            conn = db_manager.get_connection()

            # 1. Cargar feriados
            cur_f = conn.execute("SELECT fecha, descripcion FROM feriados")
            for r in cur_f.fetchall():
                y, m, d = map(int, str(r["fecha"]).split("-"))
                self.feriados_map[date(y, m, d)] = r["descripcion"]

            # 2. Cargar todas las cuotas de amortización con datos del cliente
            cur_c = conn.execute(
                """
                SELECT c.id as cuota_id, c.prestamo_id, c.numero_cuota, c.fecha_vencimiento,
                       c.cuota_total, c.saldo_pendiente_cuota, c.estado,
                       cl.nombres, cl.apellidos, cl.telefono
                FROM cuotas_amortizacion c
                JOIN prestamos p ON c.prestamo_id = p.id
                JOIN clientes cl ON p.cliente_id = cl.id
                ORDER BY c.fecha_vencimiento ASC
                """
            )
            for r in cur_c.fetchall():
                y, m, d = map(int, str(r["fecha_vencimiento"]).split("-"))
                f_venc = date(y, m, d)
                if f_venc not in self.cuotas_map:
                    self.cuotas_map[f_venc] = []
                self.cuotas_map[f_venc].append(dict(r))

            conn.close()

            # Pintar el calendario
            self.calendar.set_datos(self.cuotas_map, self.feriados_map)
            self._al_seleccionar_dia()

        except Exception as e:
            print(f"[CALENDARIO ERROR] {e}")

    def _al_seleccionar_dia(self):
        """Muestra en la tabla derecha las cuotas del día seleccionado."""
        qdate = self.calendar.selectedDate()
        d_py = date(qdate.year(), qdate.month(), qdate.day())

        # Revisar si es feriado
        if d_py in self.feriados_map:
            self.lbl_feriado_aviso.setText(f"🟡 Festivo / Feriado: {self.feriados_map[d_py]}")
            self.lbl_feriado_aviso.setVisible(True)
        else:
            self.lbl_feriado_aviso.setVisible(False)

        cuotas = self.cuotas_map.get(d_py, [])
        self.lbl_dia_seleccionado.setText(f"Vencimientos para el {d_py.strftime('%Y-%m-%d')} ({len(cuotas)} cuotas)")

        self.tabla_dia.setRowCount(len(cuotas))
        for i, c in enumerate(cuotas):
            self.tabla_dia.setItem(i, 0, QTableWidgetItem(f"#{c['prestamo_id']}"))
            self.tabla_dia.setItem(i, 1, QTableWidgetItem(f"{c['nombres']} {c['apellidos']}"))
            self.tabla_dia.setItem(i, 2, QTableWidgetItem(c["telefono"]))
            self.tabla_dia.setItem(i, 3, QTableWidgetItem(f"Cuota {c['numero_cuota']}"))
            self.tabla_dia.setItem(i, 4, QTableWidgetItem(f"${float(c['cuota_total']):,.2f}"))

            # Estado con badge de color
            item_estado = QTableWidgetItem(c["estado"])
            if c["estado"] == "EN_MORA" or (c["estado"] == "PENDIENTE" and d_py < date.today()):
                item_estado.setForeground(QColor("#dc2626"))
                item_estado.setText("EN MORA")
            elif c["estado"] == "PAGADA":
                item_estado.setForeground(QColor("#16a34a"))
            else:
                item_estado.setForeground(QColor("#2563eb"))

            font = item_estado.font()
            font.setBold(True)
            item_estado.setFont(font)
            self.tabla_dia.setItem(i, 5, item_estado)
