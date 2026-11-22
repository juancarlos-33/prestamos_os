"""
Suite de pruebas unitarias para la lógica de negocio y cálculos financieros del Sistema de Préstamos.
Requerimiento: Al menos 10 pruebas unitarias con tipos decimales exactos.
Compatible tanto con `pytest` como con el módulo estándar `unittest`.
"""

import unittest
from datetime import date
from decimal import Decimal

from src.core.loan_engine import (
    LoanEngine,
    SistemaAmortizacion,
    TipoTasa,
    Periodicidad,
    TipoSeguro,
)


class TestLoanEngine(unittest.TestCase):

    def test_01_criterio_aceptacion_1_prestamo_diez_millones_frances(self):
        """
        Criterio de aceptación 1 del documento oficial:
        Un préstamo de 10.000.000, tasa del 18 % anual, 12 cuotas mensuales por el método
        francés produce una cuota constante, y la suma del capital de la tabla es exactamente
        igual al monto prestado.
        """
        monto = Decimal("10000000.00")
        tasa = Decimal("18.00")
        cuotas = 12
        desembolso = date(2026, 1, 15)

        resumen = LoanEngine.generar_tabla_amortizacion(
            monto=monto,
            tasa_interes=tasa,
            tipo_tasa=TipoTasa.ANUAL,
            num_cuotas=cuotas,
            periodicidad=Periodicidad.MENSUAL,
            sistema=SistemaAmortizacion.FRANCES,
            fecha_desembolso=desembolso,
        )

        # 1. Verificar número de cuotas generadas
        self.assertEqual(len(resumen.cuotas), 12)

        # 2. La suma exacta de los abonos a capital debe ser igual a 10.000.000,00
        self.assertEqual(resumen.total_capital, monto)
        self.assertEqual(sum(c.abono_capital for c in resumen.cuotas), monto)

        # 3. El saldo final tras la última cuota debe ser 0.00
        self.assertEqual(resumen.cuotas[-1].saldo_restante, Decimal("0.00"))

        # 4. Las cuotas son constantes (con posible ajuste de centavos en la última cuota)
        cuota_primera = resumen.cuotas[0].cuota_total
        for c in resumen.cuotas[:-1]:
            self.assertEqual(c.cuota_total, cuota_primera)

        # 5. La diferencia en la última cuota respecto a la constante no excede 5 centavos
        diferencia_centavos = abs(resumen.cuotas[-1].cuota_total - cuota_primera)
        self.assertLessEqual(diferencia_centavos, Decimal("0.05"))

    def test_02_sistema_aleman_abono_constante(self):
        """Verifica que el sistema Alemán mantenga un abono a capital constante."""
        monto = Decimal("6000000.00")
        tasa = Decimal("12.00")
        cuotas = 6
        desembolso = date(2026, 3, 1)

        resumen = LoanEngine.generar_tabla_amortizacion(
            monto=monto,
            tasa_interes=tasa,
            tipo_tasa=TipoTasa.ANUAL,
            num_cuotas=cuotas,
            periodicidad=Periodicidad.MENSUAL,
            sistema=SistemaAmortizacion.ALEMAN,
            fecha_desembolso=desembolso,
        )

        abono_esperado = Decimal("1000000.00")
        for c in resumen.cuotas:
            self.assertEqual(c.abono_capital, abono_esperado)

        self.assertEqual(resumen.total_capital, monto)
        self.assertEqual(resumen.cuotas[-1].saldo_restante, Decimal("0.00"))
        # En sistema Alemán las cuotas son decrecientes
        self.assertGreater(resumen.cuotas[0].cuota_total, resumen.cuotas[-1].cuota_total)

    def test_03_tasa_cero_sin_division_por_cero(self):
        """Verifica que con tasa de 0% se divida exactamente el capital sin error de división."""
        monto = Decimal("1200000.00")
        resumen = LoanEngine.generar_tabla_amortizacion(
            monto=monto,
            tasa_interes=Decimal("0.00"),
            tipo_tasa=TipoTasa.ANUAL,
            num_cuotas=12,
            periodicidad=Periodicidad.MENSUAL,
            sistema=SistemaAmortizacion.FRANCES,
            fecha_desembolso=date(2026, 1, 1),
        )

        self.assertEqual(resumen.total_intereses, Decimal("0.00"))
        self.assertEqual(resumen.total_capital, monto)
        self.assertEqual(resumen.cuotas[0].cuota_total, Decimal("100000.00"))

    def test_04_sistema_interes_simple(self):
        """Verifica el cálculo de interés simple sobre capital inicial."""
        monto = Decimal("5000000.00")
        tasa_mensual = Decimal("2.00")
        cuotas = 5

        resumen = LoanEngine.generar_tabla_amortizacion(
            monto=monto,
            tasa_interes=tasa_mensual,
            tipo_tasa=TipoTasa.MENSUAL,
            num_cuotas=cuotas,
            periodicidad=Periodicidad.MENSUAL,
            sistema=SistemaAmortizacion.SIMPLE,
            fecha_desembolso=date(2026, 2, 10),
        )

        interes_esperado = Decimal("100000.00")  # 5,000,000 * 2% = 100,000 por cuota
        for c in resumen.cuotas:
            self.assertEqual(c.interes_corriente, interes_esperado)
        self.assertEqual(resumen.total_intereses, Decimal("500000.00"))

    def test_05_periodicidad_quincenal_y_semanal(self):
        """Valida que las periodicidades semanal y quincenal calculen la tasa proporcional correcta."""
        # Quincenal con tasa anual del 24% -> Tasa quincenal = 24 / 24 = 1%
        tasa_q = LoanEngine.calcular_tasa_periodica(Decimal("24.00"), TipoTasa.ANUAL, Periodicidad.QUINCENAL)
        self.assertEqual(tasa_q, Decimal("0.01"))

        # Semanal con tasa anual del 52% -> Tasa semanal = 52 / 52 = 1%
        tasa_s = LoanEngine.calcular_tasa_periodica(Decimal("52.00"), TipoTasa.ANUAL, Periodicidad.SEMANAL)
        self.assertEqual(tasa_s, Decimal("0.01"))

    def test_06_ajuste_fechas_fin_de_semana(self):
        """Si la fecha tentativa cae sábado o domingo, debe correrse al lunes siguiente."""
        sabado = date(2026, 5, 2)
        siguiente_habil = LoanEngine.siguiente_dia_habil(sabado)
        self.assertEqual(siguiente_habil, date(2026, 5, 4))  # Lunes siguiente
        self.assertEqual(siguiente_habil.weekday(), 0)

    def test_07_ajuste_fechas_feriado(self):
        """Si la fecha tentativa cae en un feriado configurado, se mueve al siguiente día hábil."""
        lunes_festivo = date(2026, 5, 18)
        feriados = {lunes_festivo}

        siguiente = LoanEngine.siguiente_dia_habil(lunes_festivo, feriados)
        self.assertEqual(siguiente, date(2026, 5, 19))  # Martes

    def test_08_cargos_adicionales_seguro_fijo_y_porcentaje(self):
        """Verifica que el seguro fijo se sume a cada cuota."""
        monto = Decimal("1000000.00")
        resumen_fijo = LoanEngine.generar_tabla_amortizacion(
            monto=monto,
            tasa_interes=Decimal("12.00"),
            tipo_tasa=TipoTasa.ANUAL,
            num_cuotas=4,
            periodicidad=Periodicidad.MENSUAL,
            sistema=SistemaAmortizacion.FRANCES,
            fecha_desembolso=date(2026, 1, 1),
            seguro_comision=Decimal("5000.00"),
            tipo_seguro=TipoSeguro.FIJO,
        )
        for c in resumen_fijo.cuotas:
            self.assertEqual(c.cargo_adicional, Decimal("5000.00"))
        self.assertEqual(resumen_fijo.total_cargos, Decimal("20000.00"))

    def test_09_calculo_interes_moratorio_diario(self):
        """Verifica el cálculo del interés moratorio diario."""
        saldo_vencido = Decimal("1000000.00")
        tasa_mora_anual = Decimal("36.50")  # Tasa diaria = 0.1% = 1,000 por día
        dias_atraso = 10

        mora = LoanEngine.calcular_interes_moratorio_diario(saldo_vencido, tasa_mora_anual, dias_atraso)
        self.assertEqual(mora, Decimal("10000.00"))

        # Si no hay atraso, mora es 0.00
        self.assertEqual(
            LoanEngine.calcular_interes_moratorio_diario(saldo_vencido, tasa_mora_anual, 0),
            Decimal("0.00"),
        )

    def test_10_aplicar_pago_orden_mora_interes_capital(self):
        """
        Verifica que los pagos se apliquen estrictamente en el orden:
        1. Mora -> 2. Interés -> 3. Capital
        """
        monto_pago = Decimal("150000.00")
        mora_pendiente = Decimal("20000.00")
        interes_pendiente = Decimal("50000.00")
        saldo_capital = Decimal("500000.00")

        desglose = LoanEngine.aplicar_pago(
            monto_pago=monto_pago,
            mora_pendiente=mora_pendiente,
            interes_pendiente=interes_pendiente,
            saldo_capital=saldo_capital,
        )

        self.assertEqual(desglose.mora_cubierta, Decimal("20000.00"))
        self.assertEqual(desglose.interes_cubierto, Decimal("50000.00"))
        self.assertEqual(desglose.capital_cubierto, Decimal("80000.00"))
        self.assertEqual(desglose.nuevo_saldo_capital, Decimal("420000.00"))
        self.assertEqual(desglose.remanente_a_favor, Decimal("0.00"))

    def test_11_aplicar_pago_parcial_insuficiente(self):
        """Valida un pago parcial que solo alcanza a cubrir la mora y parte del interés."""
        monto_pago = Decimal("30000.00")
        mora = Decimal("20000.00")
        interes = Decimal("50000.00")
        capital = Decimal("1000000.00")

        desglose = LoanEngine.aplicar_pago(monto_pago, mora, interes, capital)

        self.assertEqual(desglose.mora_cubierta, Decimal("20000.00"))
        self.assertEqual(desglose.interes_cubierto, Decimal("10000.00"))
        self.assertEqual(desglose.capital_cubierto, Decimal("0.00"))
        self.assertEqual(desglose.nuevo_saldo_capital, capital)

    def test_12_validaciones_monto_y_cuotas_invalidas(self):
        """Valida que entradas financieras inválidas generen excepciones ValueError."""
        with self.assertRaises(ValueError):
            LoanEngine.generar_tabla_amortizacion(
                monto=Decimal("-500"),
                tasa_interes=Decimal("10"),
                tipo_tasa=TipoTasa.ANUAL,
                num_cuotas=10,
                periodicidad=Periodicidad.MENSUAL,
                sistema=SistemaAmortizacion.FRANCES,
                fecha_desembolso=date.today(),
            )

        with self.assertRaises(ValueError):
            LoanEngine.generar_tabla_amortizacion(
                monto=Decimal("10000"),
                tasa_interes=Decimal("10"),
                tipo_tasa=TipoTasa.ANUAL,
                num_cuotas=0,
                periodicidad=Periodicidad.MENSUAL,
                sistema=SistemaAmortizacion.FRANCES,
                fecha_desembolso=date.today(),
            )


if __name__ == "__main__":
    unittest.main()
