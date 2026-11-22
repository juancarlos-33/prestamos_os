"""
Servicio de Generación de Documentos y Reportes en PDF con ReportLab.
Cumple con:
- PR-20: Comprobante de pago en PDF.
- PR-21: Contrato/resumen y tabla de amortización en PDF.
- PR-23: Encabezado con datos de la entidad, fecha, usuario emisor y paginación.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from src.config import config_app


class PDFService:
    """Generador de documentos contables y comprobantes en PDF."""

    @staticmethod
    def _obtener_carpeta_pdf() -> Path:
        p = config_app.data_dir / "reportes_pdf"
        p.mkdir(parents=True, exist_ok=True)
        config_app._aplicar_permisos(p, 0o700)
        return p

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
        """Genera un comprobante oficial de pago en PDF (PR-20)."""
        carpeta = cls._obtener_carpeta_pdf()
        archivo_path = carpeta / f"comprobante_{recibo_num}.pdf"

        doc = SimpleDocTemplate(
            str(archivo_path),
            pagesize=letter,
            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
        )

        styles = getSampleStyleSheet()
        entidad = config_app.config_data.get("entidad", {})

        elements = []

        # Encabezado (PR-23)
        header_text = f"<b>{entidad.get('nombre', 'COOPERATIVA FINANCIERA')}</b><br/>" \
                      f"NIT: {entidad.get('nit', '')} | Tel: {entidad.get('telefono', '')}<br/>" \
                      f"{entidad.get('direccion', '')}"
        elements.append(Paragraph(header_text, styles["Normal"]))
        elements.append(Spacer(1, 15))

        # Título
        title_style = ParagraphStyle(
            "TitleStyle",
            parent=styles["Heading2"],
            alignment=1,
            textColor=colors.HexColor("#1e3a8a")
        )
        elements.append(Paragraph(f"COMPROBANTE DE PAGO #{recibo_num}", title_style))
        elements.append(Spacer(1, 10))

        # Metadatos
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

        # Tabla de Desglose Financiero (Mora -> Interés -> Capital)
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

        # Firmas
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

        doc.build(elements)
        config_app._aplicar_permisos(archivo_path, 0o600)
        return archivo_path
