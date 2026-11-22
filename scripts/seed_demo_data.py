"""
Script generador de datos masivos de prueba para sustentación.
Cumple con:
- Criterio 5: Validación de rendimiento de la UI con más de 500 registros sin bloqueos.
- Sembrado de feriados oficiales para verificación de PR-15 en el calendario.
"""

from datetime import date, timedelta
from decimal import Decimal
import random

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.db_manager import db_manager
from src.core.loan_engine import LoanEngine, SistemaAmortizacion, TipoTasa, Periodicidad, TipoSeguro


def sembrar_feriados():
    """Siembra los principales días festivos del año para probar PR-15."""
    feriados = [
        ("2026-01-01", "Año Nuevo"),
        ("2026-01-12", "Día de los Reyes Magos"),
        ("2026-03-23", "Día de San José"),
        ("2026-04-02", "Jueves Santo"),
        ("2026-04-03", "Viernes Santo"),
        ("2026-05-01", "Día del Trabajo"),
        ("2026-05-18", "Día de la Ascensión"),
        ("2026-06-08", "Corpus Christi"),
        ("2026-07-20", "Día de la Independencia"),
        ("2026-08-07", "Batalla de Boyacá"),
        ("2026-10-12", "Día de la Raza"),
        ("2026-11-02", "Todos los Santos"),
        ("2026-12-08", "Inmaculada Concepción"),
        ("2026-12-25", "Navidad"),
    ]
    with db_manager.transaction() as conn:
        for f, desc in feriados:
            conn.execute("INSERT OR IGNORE INTO feriados (fecha, descripcion) VALUES (?, ?)", (f, desc))
    print(f"[OK] {len(feriados)} feriados registrados en la base de datos.")


def sembrar_datos_masivos(num_prestamos: int = 50):
    """
    Siembra clientes y préstamos suficientes para superar los 500 registros de cuotas
    y validar el Criterio 5 de la rúbrica.
    """
    nombres_pool = ["Carlos", "María", "Andrés", "Luisa", "Juan", "Diana", "Yeferson", "Yeffry", "Luis", "Ana"]
    apellidos_pool = ["De la Hoz", "Julio", "Mogrovejo", "Rodríguez", "González", "Moreno", "Garay", "Ozahl", "Martínez"]

    print(f"Generando datos de prueba masivos...")

    with db_manager.transaction() as conn:
        cliente_ids = []
        for i in range(25):
            nom = random.choice(nombres_pool)
            ape = random.choice(apellidos_pool)
            doc = str(1000000000 + random.randint(100000, 999999))
            tel = f"300{random.randint(1000000, 9999999)}"
            correo = f"cliente_{i}_{doc[-4:]}@coop.com"
            ingresos = str(random.randint(2000000, 8000000))

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO clientes (
                    tipo_documento, numero_documento, nombres, apellidos,
                    fecha_nacimiento, telefono, correo, direccion, ocupacion,
                    ingresos_mensuales, activo
                ) VALUES ('CC', ?, ?, ?, '1990-05-15', ?, ?, 'Calle 10 # 20-30', 'Independiente', ?, 1)
                """,
                (doc, nom, ape, tel, correo, ingresos)
            )
            c_id = cur.lastrowid or conn.execute("SELECT id FROM clientes WHERE numero_documento = ?", (doc,)).fetchone()[0]
            cliente_ids.append(c_id)

    total_cuotas_generadas = 0

    # Crear préstamos con 12 a 24 cuotas cada uno
    for i in range(num_prestamos):
        c_id = random.choice(cliente_ids)
        monto = Decimal(str(random.randint(2000000, 20000000)))
        tasa = Decimal("18.00")
        cuotas_num = random.choice([12, 18, 24])
        sistema = random.choice([SistemaAmortizacion.FRANCES, SistemaAmortizacion.ALEMAN])
        desembolso = date.today() - timedelta(days=random.randint(30, 180))

        resumen = LoanEngine.generar_tabla_amortizacion(
            monto=monto,
            tasa_interes=tasa,
            tipo_tasa=TipoTasa.ANUAL,
            num_cuotas=cuotas_num,
            periodicidad=Periodicidad.MENSUAL,
            sistema=sistema,
            fecha_desembolso=desembolso,
        )

        with db_manager.transaction() as conn:
            cur_p = conn.execute(
                """
                INSERT INTO prestamos (
                    cliente_id, usuario_id, monto_solicitado, tasa_interes, tipo_tasa,
                    plazo_cuotas, periodicidad, sistema_amortizacion, seguro_comision,
                    tipo_seguro, fecha_desembolso, estado, saldo_capital_actual
                ) VALUES (?, 1, ?, ?, 'ANUAL', ?, 'MENSUAL', ?, 0, 'FIJO', ?, 'ACTIVO', ?)
                """,
                (c_id, str(monto), str(tasa), cuotas_num, sistema.value, desembolso.isoformat(), str(monto))
            )
            p_id = cur_p.lastrowid

            for c in resumen.cuotas:
                # Simular algunas cuotas pagadas en el pasado
                estado_cuota = "PENDIENTE"
                saldo_cuota = c.cuota_total
                if c.fecha_vencimiento < date.today() - timedelta(days=45):
                    estado_cuota = "PAGADA"
                    saldo_cuota = Decimal("0.00")
                elif c.fecha_vencimiento < date.today():
                    estado_cuota = "EN_MORA"

                conn.execute(
                    """
                    INSERT INTO cuotas_amortizacion (
                        prestamo_id, numero_cuota, fecha_vencimiento, abono_capital,
                        interes_corriente, cargo_adicional, cuota_total, saldo_restante,
                        estado, saldo_pendiente_cuota
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p_id, c.numero_cuota, c.fecha_vencimiento.isoformat(),
                        str(c.abono_capital), str(c.interes_corriente), str(c.cargo_adicional),
                        str(c.cuota_total), str(c.saldo_restante), estado_cuota, str(saldo_cuota)
                    )
                )
                total_cuotas_generadas += 1

    print(f"[OK] Carga masiva completada exitosamente:")
    print(f"     - Préstamos creados: {num_prestamos}")
    print(f"     - Total de cuotas en base de datos: {total_cuotas_generadas} registros (Supera los 500 requeridos para el Criterio 5).")


if __name__ == "__main__":
    sembrar_feriados()
    sembrar_datos_masivos(50)
