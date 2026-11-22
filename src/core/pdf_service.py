"""
Servicio de Generación de Documentos y Reportes en PDF con ReportLab.
Cumple con:
- PR-20: Comprobante de pago en PDF.
- PR-21: Contrato/resumen, tabla de amortización y estado de cuenta.
- PR-22: Reportes gerenciales (cartera vigente, cartera en mora, recaudo por fechas e intereses proyectados).
- PR-23: Encabezado institucional, fecha de emisión, usuario emisor y numeración 'Página X de Y'.
"""

from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from src.config import config_app
from src.database.db_manager import db_manager


class NumberedCanvas(canvas.Canvas):
    """
    Lienzo de ReportLab de dos pasadas para calcular el número total de páginas
    e imprimir 'Página X de Y' junto con el pie de página institucional (PR-23).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Línea separadora de pie de página
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(40, 30, letter[0] - 40, 30)

        # Texto del pie
        fecha_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.drawString(40, 18, f"PrestamoOS — Generado el {fecha_str}")
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(letter[0] - 40, 18, page_text)
        self.restoreState()


class PDFService:
    """Generador integral de comprobantes y reportes gerenciales en PDF."""

    @staticmethod
    def _obtener_carpeta_pdf() -> Path:
        p = config_app.data_dir / "reportes_pdf"
        p.mkdir(parents=True, exist_ok=True)
        config_app._aplicar_permisos(p, 0o700)
        return p

    @classmethod
    def _crear_encabezado(cls, titulo: str, usuario_emisor: str) -> List[Any]:
        """Crea el bloque de membrete con logotipo/nombre de la entidad, fecha y emisor (PR-23)."""
        styles = getSampleStyleSheet()
        entidad = config_app.config_data.get("entidad", {})

        elements = []
        header_text = (
            f"<b>{entidad.get('nombre', 'COOPERATIVA FINANCIERA')}</b><br/>"
            f"NIT: {entidad.get('nit', '')} | Tel: {entidad.get('telefono', '')}<br/>"
            f"{entidad.get('direccion', '')}"
        )
        elements.append(Paragraph(header_text, styles["Normal"]))
        elements.append(Spacer(1, 10))

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading2"],
            alignment=1,
            textColor=colors.HexColor("#1e3a8a"),
            spaceAfter=6,
        )
        elements.append(Paragraph(titulo, title_style))

        meta_text = (
            f"<font size='8' color='#64748b'>"
            f"Fecha de Emisión: <b>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</b> | "
            f"Generado por: <b>{usuario_emisor}</b>"
            f"</font>"
        )
        meta_style = ParagraphStyle("MetaStyle", parent=styles["Normal"], alignment=1)
        elements.append(Paragraph(meta_text, meta_style))
        elements.append(Spacer(1, 15))

        return elements

    @classmethod
    def generar_comprobante_pago(
        cls,
        recibo_num: str,
        fecha_pago: datetime,
        cliente_nombre: str,
        cliente_doc: str,
        prestamo_id: int,
        monto_recibido: Decimal,
        desglose_mora: Decimal,
        desglose_interes: Decimal,
        desglose_capital: Decimal,
        nuevo_saldo: Decimal,
        metodo_pago: str,
        usuario_cajero: str,
    ) -> Path:
        """Genera comprobante de pago oficial en PDF (PR-20)."""
        carpeta = cls._obtener_carpeta_pdf()
        archivo_path = carpeta / f"comprobante_{recibo_num}.pdf"

        doc = SimpleDocTemplate(
            str(archivo_path),
            pagesize=letter,
            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
        )

        elements = cls._crear_encabezado(f"COMPROBANTE DE PAGO #{recibo_num}", usuario_cajero)

        info_data = [
            ["Fecha y Hora:", fecha_pago.strftime("%Y-%m-%d %H:%M:%S"), "Préstamo No:", f"#{prestamo_id}"],
            ["Cliente:", cliente_nombre, "Documento:", cliente_doc],
            ["Método de Pago:", metodo_pago, "Atendido por:", usuario_cajero],
        ]
        t_info = Table(info_data, colWidths=[110, 160, 110, 150])
        t_info.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#475569")),
            ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor("#475569")),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_info)
        elements.append(Spacer(1, 15))

        desglose_data = [
            ["Concepto Liquidado", "Monto Aplicado"],
            ["Interés Moratorio", f"${desglose_mora:,.2f}"],
            ["Interés Corriente", f"${desglose_interes:,.2f}"],
            ["Abono a Capital", f"${desglose_capital:,.2f}"],
            ["TOTAL PAGADO", f"${monto_recibido:,.2f}"],
            ["Nuevo Saldo de Capital Restante", f"${nuevo_saldo:,.2f}"],
        ]
        t_desglose = Table(desglose_data, colWidths=[330, 200])
        t_desglose.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2563eb")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor("#f1f5f9")),
            ('FONTNAME', (0, 4), (-1, 5), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t_desglose)
        elements.append(Spacer(1, 30))

        firmas_data = [
            ["_____________________________________", "_____________________________________"],
            ["Firma del Cajero Responsable", "Firma del Cliente"],
        ]
        t_firmas = Table(firmas_data, colWidths=[265, 265])
        t_firmas.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor("#64748b")),
        ]))
        elements.append(t_firmas)

        doc.build(elements, canvasmaker=NumberedCanvas)
        config_app._aplicar_permisos(archivo_path, 0o600)
        return archivo_path

    @classmethod
    def generar_reporte_cartera_vigente(cls, usuario_emisor: str) -> Path:
        """Genera el reporte de cartera activa/vigente (PR-22)."""
        carpeta = cls._obtener_carpeta_pdf()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archivo_path = carpeta / f"reporte_cartera_vigente_{ts}.pdf"

        doc = SimpleDocTemplate(
            str(archivo_path),
            pagesize=letter,
            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
        )

        elements = cls._crear_encabezado("REPORTE GERENCIAL: CARTERA VIGENTE", usuario_emisor)

        # Consultar préstamos activos
        conn = db_manager.get_connection()
        cur = conn.execute(
            """
            SELECT p.id, cl.nombres, cl.apellidos, cl.numero_documento,
                   p.monto_solicitado, p.saldo_capital_actual, p.tasa_interes,
                   p.sistema_amortizacion, p.plazo_cuotas, p.fecha_desembolso
            FROM prestamos p
            JOIN clientes cl ON p.cliente_id = cl.id
            WHERE p.estado = 'ACTIVO'
            ORDER BY p.id ASC
            """
        )
        rows = cur.fetchall()
        conn.close()

        tabla_datos = [
            ["ID", "Cliente", "Documento", "Monto Otorgado", "Saldo Capital", "Tasa", "Plazo", "Desembolso"]
        ]

        total_otorgado = Decimal("0.00")
        total_saldo = Decimal("0.00")

        for r in rows:
            m_otorg = Decimal(str(r["monto_solicitado"]))
            m_saldo = Decimal(str(r["saldo_capital_actual"]))
            total_otorgado += m_otorg
            total_saldo += m_saldo

            tabla_datos.append([
                f"#{r['id']}",
                f"{r['nombres']} {r['apellidos']}",
                str(r["numero_documento"]),
                f"${m_otorg:,.2f}",
                f"${m_saldo:,.2f}",
                f"{r['tasa_interes']}%",
                f"{r['plazo_cuotas']}c",
                str(r["fecha_desembolso"]),
            ])

        # Fila de totales
        tabla_datos.append([
            "TOTALES", f"{len(rows)} préstamos", "",
            f"${total_otorgado:,.2f}", f"${total_saldo:,.2f}", "", "", ""
        ])

        t_rep = Table(tabla_datos, colWidths=[35, 125, 75, 80, 80, 45, 45, 55])
        t_rep.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (3, 0), (4, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor("#cbd5e1")),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor("#1e3a8a")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_rep)

        doc.build(elements, canvasmaker=NumberedCanvas)
        config_app._aplicar_permisos(archivo_path, 0o600)
        return archivo_path

    @classmethod
    def generar_reporte_cartera_en_mora(cls, usuario_emisor: str) -> Path:
        """Genera el reporte de cartera en mora con días y cargos moratorios (PR-22)."""
        carpeta = cls._obtener_carpeta_pdf()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archivo_path = carpeta / f"reporte_cartera_mora_{ts}.pdf"

        doc = SimpleDocTemplate(
            str(archivo_path),
            pagesize=letter,
            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
        )

        elements = cls._crear_encabezado("REPORTE GERENCIAL: CARTERA EN MORA", usuario_emisor)

        hoy = date.today()
        tasa_mora = Decimal(str(config_app.config_data.get("parametros_prestamo", {}).get("tasa_mora_anual_defecto", 28.0)))

        conn = db_manager.get_connection()
        cur = conn.execute(
            """
            SELECT p.id as prestamo_id, cl.nombres, cl.apellidos, cl.telefono,
                   c.numero_cuota, c.fecha_vencimiento, c.saldo_pendiente_cuota
            FROM cuotas_amortizacion c
            JOIN prestamos p ON c.prestamo_id = p.id
            JOIN clientes cl ON p.cliente_id = cl.id
            WHERE c.estado IN ('PENDIENTE', 'EN_MORA') AND c.fecha_vencimiento < ?
            ORDER BY c.fecha_vencimiento ASC
            """,
            (hoy.isoformat(),)
        )
        rows = cur.fetchall()
        conn.close()

        tabla_datos = [
            ["Préstamo", "Cliente", "Teléfono", "Cuota #", "Vencimiento", "Días Mora", "Capital Vencido", "Mora Proyectada"]
        ]

        total_capital_mora = Decimal("0.00")
        total_mora_liq = Decimal("0.00")

        from src.core.loan_engine import LoanEngine

        for r in rows:
            y, m, d = map(int, str(r["fecha_vencimiento"]).split("-"))
            f_venc = date(y, m, d)
            dias_atraso = (hoy - f_venc).days
            saldo_cuota = Decimal(str(r["saldo_pendiente_cuota"]))
            mora_diaria = LoanEngine.calcular_interes_moratorio_diario(saldo_cuota, tasa_mora, dias_atraso)

            total_capital_mora += saldo_cuota
            total_mora_liq += mora_diaria

            tabla_datos.append([
                f"#{r['prestamo_id']}",
                f"{r['nombres']} {r['apellidos']}",
                str(r["telefono"]),
                f"#{r['numero_cuota']}",
                str(r["fecha_vencimiento"]),
                f"{dias_atraso} d",
                f"${saldo_cuota:,.2f}",
                f"${mora_diaria:,.2f}",
            ])

        tabla_datos.append([
            "TOTALES", f"{len(rows)} cuotas en mora", "", "", "", "",
            f"${total_capital_mora:,.2f}", f"${total_mora_liq:,.2f}"
        ])

        t_rep = Table(tabla_datos, colWidths=[50, 130, 65, 45, 60, 50, 70, 70])
        t_rep.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#b91c1c")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (6, 0), (7, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor("#fca5a5")),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#fee2e2")),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor("#b91c1c")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_rep)

        doc.build(elements, canvasmaker=NumberedCanvas)
        config_app._aplicar_permisos(archivo_path, 0o600)
        return archivo_path

    @classmethod
    def generar_reporte_recaudo_rango(
        cls, fecha_inicio: date, fecha_fin: date, usuario_emisor: str
    ) -> Path:
        """Genera el reporte de recaudo por rango de fechas (PR-22)."""
        carpeta = cls._obtener_carpeta_pdf()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archivo_path = carpeta / f"reporte_recaudo_{ts}.pdf"

        doc = SimpleDocTemplate(
            str(archivo_path),
            pagesize=letter,
            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
        )

        subt = f"REPORTE GERENCIAL: RECAUDO DEL {fecha_inicio} AL {fecha_fin}"
        elements = cls._crear_encabezado(subt, usuario_emisor)

        conn = db_manager.get_connection()
        cur = conn.execute(
            """
            SELECT p.numero_recibo, p.fecha_pago, p.prestamo_id, cl.nombres, cl.apellidos,
                   p.metodo_pago, p.aplicado_mora, p.aplicado_interes, p.aplicado_capital, p.monto_recibido
            FROM pagos p
            JOIN prestamos pr ON p.prestamo_id = pr.id
            JOIN clientes cl ON pr.cliente_id = cl.id
            WHERE date(p.fecha_pago) BETWEEN ? AND ?
            ORDER BY p.fecha_pago ASC
            """,
            (fecha_inicio.isoformat(), fecha_fin.isoformat())
        )
        rows = cur.fetchall()
        conn.close()

        tabla_datos = [
            ["Recibo #", "Fecha y Hora", "Cliente", "Método", "Mora", "Interés", "Capital", "Total Recaudado"]
        ]

        tot_mora = Decimal("0.00")
        tot_int = Decimal("0.00")
        tot_cap = Decimal("0.00")
        tot_general = Decimal("0.00")

        for r in rows:
            mora = Decimal(str(r["aplicado_mora"]))
            inte = Decimal(str(r["aplicado_interes"]))
            capi = Decimal(str(r["aplicado_capital"]))
            tota = Decimal(str(r["monto_recibido"]))

            tot_mora += mora
            tot_int += inte
            tot_cap += capi
            tot_general += tota

            tabla_datos.append([
                str(r["numero_recibo"]),
                str(r["fecha_pago"])[:16],
                f"{r['nombres']} {r['apellidos']}",
                str(r["metodo_pago"]),
                f"${mora:,.2f}",
                f"${inte:,.2f}",
                f"${capi:,.2f}",
                f"${tota:,.2f}",
            ])

        tabla_datos.append([
            "TOTALES", f"{len(rows)} pagos", "", "",
            f"${tot_mora:,.2f}", f"${tot_int:,.2f}", f"${tot_cap:,.2f}", f"${tot_general:,.2f}"
        ])

        t_rep = Table(tabla_datos, colWidths=[95, 75, 110, 60, 50, 50, 50, 50])
        t_rep.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#047857")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor("#a7f3d0")),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#ecfdf5")),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor("#047857")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_rep)

        doc.build(elements, canvasmaker=NumberedCanvas)
        config_app._aplicar_permisos(archivo_path, 0o600)
        return archivo_path

    @classmethod
    def generar_pdf_tabla_amortizacion_prestamo(cls, prestamo_id: int, usuario_emisor: str) -> Path:
        """Genera el PDF con la tabla oficial de amortización de un préstamo (PR-21)."""
        carpeta = cls._obtener_carpeta_pdf()
        archivo_path = carpeta / f"tabla_amortizacion_prestamo_{prestamo_id}.pdf"

        doc = SimpleDocTemplate(
            str(archivo_path),
            pagesize=letter,
            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
        )

        elements = cls._crear_encabezado(f"PLAN DE PAGOS Y TABLA DE AMORTIZACIÓN #{prestamo_id}", usuario_emisor)

        conn = db_manager.get_connection()
        p_row = conn.execute(
            """
            SELECT p.*, cl.nombres, cl.apellidos, cl.tipo_documento, cl.numero_documento, cl.telefono
            FROM prestamos p
            JOIN clientes cl ON p.cliente_id = cl.id
            WHERE p.id = ?
            """,
            (prestamo_id,)
        ).fetchone()

        c_rows = conn.execute(
            """
            SELECT * FROM cuotas_amortizacion
            WHERE prestamo_id = ?
            ORDER BY numero_cuota ASC
            """,
            (prestamo_id,)
        ).fetchall()
        conn.close()

        if not p_row:
            raise ValueError(f"Préstamo #{prestamo_id} no encontrado")

        # Ficha del préstamo
        ficha = [
            ["Titular:", f"{p_row['nombres']} {p_row['apellidos']}", "Documento:", f"{p_row['tipo_documento']} {p_row['numero_documento']}"],
            ["Monto Desembolsado:", f"${float(p_row['monto_solicitado']):,.2f}", "Método:", p_row["sistema_amortizacion"]],
            ["Tasa de Interés:", f"{p_row['tasa_interes']}% {p_row['tipo_tasa']}", "Periodicidad:", p_row["periodicidad"]],
            ["Plazo:", f"{p_row['plazo_cuotas']} cuotas", "Fecha Desembolso:", str(p_row["fecha_desembolso"])],
        ]
        t_ficha = Table(ficha, colWidths=[120, 150, 110, 160])
        t_ficha.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_ficha)
        elements.append(Spacer(1, 15))

        # Tabla de cuotas
        tabla_cuotas = [
            ["Cuota #", "Vencimiento", "Abono Capital", "Interés", "Cargos", "Cuota Total", "Saldo Restante", "Estado"]
        ]
        tot_cap = Decimal("0.00")
        tot_int = Decimal("0.00")
        tot_carg = Decimal("0.00")
        tot_cuot = Decimal("0.00")

        for c in c_rows:
            cap = Decimal(str(c["abono_capital"]))
            inte = Decimal(str(c["interes_corriente"]))
            carg = Decimal(str(c["cargo_adicional"]))
            tot = Decimal(str(c["cuota_total"]))
            sal = Decimal(str(c["saldo_restante"]))

            tot_cap += cap
            tot_int += inte
            tot_carg += carg
            tot_cuot += tot

            tabla_cuotas.append([
                str(c["numero_cuota"]),
                str(c["fecha_vencimiento"]),
                f"${cap:,.2f}",
                f"${inte:,.2f}",
                f"${carg:,.2f}",
                f"${tot:,.2f}",
                f"${sal:,.2f}",
                c["estado"]
            ])

        tabla_cuotas.append([
            "TOTALES", "", f"${tot_cap:,.2f}", f"${tot_int:,.2f}",
            f"${tot_carg:,.2f}", f"${tot_cuot:,.2f}", "", ""
        ])

        t_cuotas = Table(tabla_cuotas, colWidths=[45, 65, 75, 70, 55, 75, 80, 75])
        t_cuotas.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2563eb")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (2, 0), (6, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor("#cbd5e1")),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor("#2563eb")),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_cuotas)

        doc.build(elements, canvasmaker=NumberedCanvas)
        config_app._aplicar_permisos(archivo_path, 0o600)
        return archivo_path
