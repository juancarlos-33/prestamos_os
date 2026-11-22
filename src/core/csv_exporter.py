"""
Módulo de Exportación de Datos a Formato CSV (PR-24).
Genera archivos delimitados por comas con codificación UTF-8 y permisos restrictivos.
"""

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any

from src.config import config_app
from src.database.db_manager import db_manager


class CSVExporter:
    """Exportador de datos tabulares a archivos CSV."""

    @staticmethod
    def _obtener_carpeta_csv() -> Path:
        p = config_app.data_dir / "exportaciones_csv"
        p.mkdir(parents=True, exist_ok=True)
        config_app._aplicar_permisos(p, 0o700)
        return p

    @classmethod
    def exportar_cartera_vigente(cls) -> Path:
        """Exporta la cartera activa a CSV (PR-24)."""
        carpeta = cls._obtener_carpeta_csv()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archivo_path = carpeta / f"cartera_vigente_{ts}.csv"

        conn = db_manager.get_connection()
        cur = conn.execute(
            """
            SELECT p.id as prestamo_id, cl.tipo_documento, cl.numero_documento,
                   cl.nombres, cl.apellidos, cl.telefono, p.monto_solicitado,
                   p.saldo_capital_actual, p.tasa_interes, p.tipo_tasa,
                   p.sistema_amortizacion, p.plazo_cuotas, p.periodicidad, p.fecha_desembolso
            FROM prestamos p
            JOIN clientes cl ON p.cliente_id = cl.id
            WHERE p.estado = 'ACTIVO'
            ORDER BY p.id ASC
            """
        )
        rows = cur.fetchall()
        conn.close()

        with open(archivo_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID Prestamo", "Tipo Doc", "Numero Documento", "Nombres", "Apellidos",
                "Telefono", "Monto Otorgado", "Saldo Capital", "Tasa Interes", "Tipo Tasa",
                "Metodo Amortizacion", "Plazo Cuotas", "Periodicidad", "Fecha Desembolso"
            ])
            for r in rows:
                writer.writerow([
                    r["prestamo_id"], r["tipo_documento"], r["numero_documento"],
                    r["nombres"], r["apellidos"], r["telefono"], r["monto_solicitado"],
                    r["saldo_capital_actual"], r["tasa_interes"], r["tipo_tasa"],
                    r["sistema_amortizacion"], r["plazo_cuotas"], r["periodicidad"],
                    r["fecha_desembolso"]
                ])

        config_app._aplicar_permisos(archivo_path, 0o600)
        return archivo_path

    @classmethod
    def exportar_cartera_en_mora(cls) -> Path:
        """Exporta la cartera vencida con cálculo de días de atraso a CSV."""
        carpeta = cls._obtener_carpeta_csv()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archivo_path = carpeta / f"cartera_en_mora_{ts}.csv"

        hoy = date.today()
        from src.core.loan_engine import LoanEngine
        tasa_mora = Decimal(str(config_app.config_data.get("parametros_prestamo", {}).get("tasa_mora_anual_defecto", 28.0)))

        conn = db_manager.get_connection()
        cur = conn.execute(
            """
            SELECT p.id as prestamo_id, cl.numero_documento, cl.nombres, cl.apellidos, cl.telefono,
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

        with open(archivo_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID Prestamo", "Documento", "Nombres", "Apellidos", "Telefono",
                "Numero Cuota", "Fecha Vencimiento", "Dias Atraso", "Saldo Cuota", "Mora Proyectada"
            ])
            for r in rows:
                y, m, d = map(int, str(r["fecha_vencimiento"]).split("-"))
                dias = (hoy - date(y, m, d)).days
                saldo = Decimal(str(r["saldo_pendiente_cuota"]))
                mora = LoanEngine.calcular_interes_moratorio_diario(saldo, tasa_mora, dias)

                writer.writerow([
                    r["prestamo_id"], r["numero_documento"], r["nombres"], r["apellidos"],
                    r["telefono"], r["numero_cuota"], r["fecha_vencimiento"],
                    dias, str(saldo), str(mora)
                ])

        config_app._aplicar_permisos(archivo_path, 0o600)
        return archivo_path

    @classmethod
    def exportar_recaudo_rango(cls, f_inicio: date, f_fin: date) -> Path:
        """Exporta los pagos de un rango de fechas a CSV."""
        carpeta = cls._obtener_carpeta_csv()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archivo_path = carpeta / f"recaudo_{ts}.csv"

        conn = db_manager.get_connection()
        cur = conn.execute(
            """
            SELECT p.numero_recibo, p.fecha_pago, p.prestamo_id, cl.numero_documento,
                   cl.nombres, cl.apellidos, p.metodo_pago, p.aplicado_mora,
                   p.aplicado_interes, p.aplicado_capital, p.monto_recibido
            FROM pagos p
            JOIN prestamos pr ON p.prestamo_id = pr.id
            JOIN clientes cl ON pr.cliente_id = cl.id
            WHERE date(p.fecha_pago) BETWEEN ? AND ?
            ORDER BY p.fecha_pago ASC
            """,
            (f_inicio.isoformat(), f_fin.isoformat())
        )
        rows = cur.fetchall()
        conn.close()

        with open(archivo_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Numero Recibo", "Fecha y Hora", "ID Prestamo", "Documento Cliente",
                "Nombres", "Apellidos", "Metodo Pago", "Mora Cubierta", "Interes Cubierto",
                "Capital Cubierto", "Total Pagado"
            ])
            for r in rows:
                writer.writerow([
                    r["numero_recibo"], r["fecha_pago"], r["prestamo_id"],
                    r["numero_documento"], r["nombres"], r["apellidos"],
                    r["metodo_pago"], r["aplicado_mora"], r["aplicado_interes"],
                    r["aplicado_capital"], r["monto_recibido"]
                ])

        config_app._aplicar_permisos(archivo_path, 0o600)
        return archivo_path
