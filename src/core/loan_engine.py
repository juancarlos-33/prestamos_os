"""
Motor de Cálculos Financieros y Amortización para el Sistema de Gestión de Préstamos.

Cumple con:
- Precisión decimal exacta mediante `decimal.Decimal` (sin tipos float para dinero).
- Sistemas de amortización: Francés (cuota fija), Alemán (abono constante) e Interés Simple.
- Ajuste de fechas de vencimiento omitiendo fines de semana y feriados configurables.
- Ajuste del último periodo para garantizar que sum(capital) == monto desembolsado.
- Liquidación de pagos priorizando: Mora -> Intereses -> Capital.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Set, Optional


CENT = Decimal("0.01")


def round_money(val: Decimal) -> Decimal:
    """Redondea un valor monetario a 2 cifras decimales usando ROUND_HALF_UP."""
    return val.quantize(CENT, rounding=ROUND_HALF_UP)


class SistemaAmortizacion(str, Enum):
    FRANCES = "FRANCES"   # Cuota periódica constante
    ALEMAN = "ALEMAN"     # Abono a capital constante
    SIMPLE = "SIMPLE"     # Interés simple sobre capital inicial


class TipoTasa(str, Enum):
    ANUAL = "ANUAL"
    MENSUAL = "MENSUAL"


class Periodicidad(str, Enum):
    MENSUAL = "MENSUAL"
    QUINCENAL = "QUINCENAL"
    SEMANAL = "SEMANAL"


class TipoSeguro(str, Enum):
    FIJO = "FIJO"
    PORCENTAJE = "PORCENTAJE"


@dataclass
class CuotaAmortizacion:
    numero_cuota: int
    fecha_vencimiento: date
    abono_capital: Decimal
    interes_corriente: Decimal
    cargo_adicional: Decimal
    cuota_total: Decimal
    saldo_restante: Decimal


@dataclass
class ResumenPrestamo:
    monto_solicitado: Decimal
    tasa_efectiva_periodo: Decimal
    num_cuotas: int
    sistema: SistemaAmortizacion
    periodicidad: Periodicidad
    cuotas: List[CuotaAmortizacion]
    total_capital: Decimal
    total_intereses: Decimal
    total_cargos: Decimal
    total_a_pagar: Decimal
    cuota_fija_referencial: Optional[Decimal] = None


@dataclass
class DesglosePago:
    monto_recibido: Decimal
    mora_cubierta: Decimal
    interes_cubierto: Decimal
    capital_cubierto: Decimal
    remanente_a_favor: Decimal
    nuevo_saldo_capital: Decimal


class LoanEngine:
    """Motor de cálculo financiero para préstamos cooperativos."""

    @staticmethod
    def es_dia_habil(dia: date, feriados: Optional[Set[date]] = None) -> bool:
        """Determina si una fecha es día hábil (lunes a viernes y no feriado)."""
        if dia.weekday() >= 5:  # 5 = Sábado, 6 = Domingo
            return False
        if feriados and dia in feriados:
            return False
        return True

    @classmethod
    def siguiente_dia_habil(cls, dia: date, feriados: Optional[Set[date]] = None) -> date:
        """Si la fecha cae en fin de semana o feriado, avanza al siguiente día hábil."""
        actual = dia
        while not cls.es_dia_habil(actual, feriados):
            actual += timedelta(days=1)
        return actual

    @classmethod
    def sumar_periodo(
        cls,
        fecha_base: date,
        periodo_idx: int,
        periodicidad: Periodicidad,
        feriados: Optional[Set[date]] = None,
    ) -> date:
        """Calcula la fecha de vencimiento sumando períodos calendario y ajustando días hábiles."""
        if periodicidad == Periodicidad.SEMANAL:
            tentativa = fecha_base + timedelta(weeks=periodo_idx)
        elif periodicidad == Periodicidad.QUINCENAL:
            tentativa = fecha_base + timedelta(days=15 * periodo_idx)
        elif periodicidad == Periodicidad.MENSUAL:
            # Manejo del incremento mensual preservando el día del mes
            mes = fecha_base.month - 1 + periodo_idx
            anio = fecha_base.year + (mes // 12)
            mes = (mes % 12) + 1
            # Evita desbordamiento de fin de mes (e.g. 31 en febrero o abril)
            import calendar
            max_dias = calendar.monthrange(anio, mes)[1]
            dia_ajustado = min(fecha_base.day, max_dias)
            tentativa = date(anio, mes, dia_ajustado)
        else:
            tentativa = fecha_base + timedelta(days=30 * periodo_idx)

        return cls.siguiente_dia_habil(tentativa, feriados)

    @classmethod
    def calcular_tasa_periodica(
        cls,
        tasa_valor: Decimal,
        tipo_tasa: TipoTasa,
        periodicidad: Periodicidad,
    ) -> Decimal:
        """
        Calcula la tasa de interés efectiva/nominal correspondiente a cada período de pago.
        `tasa_valor` se ingresa en porcentaje (ej: 18 para 18%).
        """
        tasa_dec = tasa_valor / Decimal("100")

        if tipo_tasa == TipoTasa.ANUAL:
            if periodicidad == Periodicidad.MENSUAL:
                return tasa_dec / Decimal("12")
            elif periodicidad == Periodicidad.QUINCENAL:
                return tasa_dec / Decimal("24")
            elif periodicidad == Periodicidad.SEMANAL:
                return tasa_dec / Decimal("52")
        elif tipo_tasa == TipoTasa.MENSUAL:
            if periodicidad == Periodicidad.MENSUAL:
                return tasa_dec
            elif periodicidad == Periodicidad.QUINCENAL:
                return tasa_dec / Decimal("2")
            elif periodicidad == Periodicidad.SEMANAL:
                return tasa_dec / Decimal("4")

        return tasa_dec

    @classmethod
    def generar_tabla_amortizacion(
        cls,
        monto: Decimal,
        tasa_interes: Decimal,
        tipo_tasa: TipoTasa,
        num_cuotas: int,
        periodicidad: Periodicidad,
        sistema: SistemaAmortizacion,
        fecha_desembolso: date,
        seguro_comision: Decimal = Decimal("0.00"),
        tipo_seguro: TipoSeguro = TipoSeguro.FIJO,
        feriados: Optional[Set[date]] = None,
    ) -> ResumenPrestamo:
        """
        Genera la tabla de amortización detallada asegurando consistencia matemática exacta.
        """
        if monto <= Decimal("0"):
            raise ValueError("El monto del préstamo debe ser mayor a 0.")
        if num_cuotas <= 0:
            raise ValueError("El número de cuotas debe ser mayor a 0.")
        if tasa_interes < Decimal("0"):
            raise ValueError("La tasa de interés no puede ser negativa.")

        monto = round_money(monto)
        r = cls.calcular_tasa_periodica(tasa_interes, tipo_tasa, periodicidad)

        # Cálculo de cargos adicionales por cuota (seguro / comisiones)
        if tipo_seguro == TipoSeguro.PORCENTAJE:
            cargo_por_cuota = round_money(monto * (seguro_comision / Decimal("100")))
        else:
            cargo_por_cuota = round_money(seguro_comision)

        cuotas: List[CuotaAmortizacion] = []
        saldo_actual = monto
        cuota_fija_ref: Optional[Decimal] = None

        if sistema == SistemaAmortizacion.FRANCES:
            # Cuota fija teórica: C = P * [ r*(1+r)^n / ((1+r)^n - 1) ]
            if r > Decimal("0"):
                factor = (Decimal("1") + r) ** num_cuotas
                cuota_pura = monto * (r * factor) / (factor - Decimal("1"))
            else:
                cuota_pura = monto / Decimal(num_cuotas)

            cuota_fija_redondeada = round_money(cuota_pura)
            cuota_fija_ref = cuota_fija_redondeada + cargo_por_cuota

            for i in range(1, num_cuotas + 1):
                fecha_venc = cls.sumar_periodo(fecha_desembolso, i, periodicidad, feriados)
                interes = round_money(saldo_actual * r)

                if i == num_cuotas:
                    # En la última cuota se amortiza exactamente el saldo remanente
                    abono_cap = saldo_actual
                    saldo_actual = Decimal("0.00")
                else:
                    abono_cap = cuota_fija_redondeada - interes
                    if abono_cap > saldo_actual:
                        abono_cap = saldo_actual
                    saldo_actual = round_money(saldo_actual - abono_cap)

                total_cuota = abono_cap + interes + cargo_por_cuota
                cuotas.append(
                    CuotaAmortizacion(
                        numero_cuota=i,
                        fecha_vencimiento=fecha_venc,
                        abono_capital=abono_cap,
                        interes_corriente=interes,
                        cargo_adicional=cargo_por_cuota,
                        cuota_total=total_cuota,
                        saldo_restante=saldo_actual,
                    )
                )

        elif sistema == SistemaAmortizacion.ALEMAN:
            # Abono constante a capital: A = P / n
            abono_base = round_money(monto / Decimal(num_cuotas))

            for i in range(1, num_cuotas + 1):
                fecha_venc = cls.sumar_periodo(fecha_desembolso, i, periodicidad, feriados)
                interes = round_money(saldo_actual * r)

                if i == num_cuotas:
                    abono_cap = saldo_actual
                    saldo_actual = Decimal("0.00")
                else:
                    abono_cap = abono_base
                    saldo_actual = round_money(saldo_actual - abono_cap)

                total_cuota = abono_cap + interes + cargo_por_cuota
                cuotas.append(
                    CuotaAmortizacion(
                        numero_cuota=i,
                        fecha_vencimiento=fecha_venc,
                        abono_capital=abono_cap,
                        interes_corriente=interes,
                        cargo_adicional=cargo_por_cuota,
                        cuota_total=total_cuota,
                        saldo_restante=saldo_actual,
                    )
                )

        elif sistema == SistemaAmortizacion.SIMPLE:
            # Interés simple: interés constante sobre capital inicial en cada periodo
            interes_fijo = round_money(monto * r)
            abono_base = round_money(monto / Decimal(num_cuotas))

            for i in range(1, num_cuotas + 1):
                fecha_venc = cls.sumar_periodo(fecha_desembolso, i, periodicidad, feriados)
                if i == num_cuotas:
                    abono_cap = saldo_actual
                    saldo_actual = Decimal("0.00")
                else:
                    abono_cap = abono_base
                    saldo_actual = round_money(saldo_actual - abono_cap)

                total_cuota = abono_cap + interes_fijo + cargo_por_cuota
                cuotas.append(
                    CuotaAmortizacion(
                        numero_cuota=i,
                        fecha_vencimiento=fecha_venc,
                        abono_capital=abono_cap,
                        interes_corriente=interes_fijo,
                        cargo_adicional=cargo_por_cuota,
                        cuota_total=total_cuota,
                        saldo_restante=saldo_actual,
                    )
                )

        total_cap = sum((c.abono_capital for c in cuotas), Decimal("0.00"))
        total_int = sum((c.interes_corriente for c in cuotas), Decimal("0.00"))
        total_carg = sum((c.cargo_adicional for c in cuotas), Decimal("0.00"))
        total_pagar = total_cap + total_int + total_carg

        return ResumenPrestamo(
            monto_solicitado=monto,
            tasa_efectiva_periodo=r,
            num_cuotas=num_cuotas,
            sistema=sistema,
            periodicidad=periodicidad,
            cuotas=cuotas,
            total_capital=total_cap,
            total_intereses=total_int,
            total_cargos=total_carg,
            total_a_pagar=total_pagar,
            cuota_fija_referencial=cuota_fija_ref,
        )

    @classmethod
    def calcular_interes_moratorio_diario(
        cls,
        saldo_vencido: Decimal,
        tasa_mora_anual: Decimal,
        dias_atraso: int,
    ) -> Decimal:
        """
        Calcula el interés moratorio diario acumulado según los días de mora.
        `tasa_mora_anual` se ingresa en porcentaje (ej: 24 para 24% anual).
        """
        if dias_atraso <= 0 or saldo_vencido <= Decimal("0"):
            return Decimal("0.00")

        # Tasa diaria basada en año comercial (360 días) o civil (365 días)
        tasa_diaria = (tasa_mora_anual / Decimal("100")) / Decimal("365")
        mora = saldo_vencido * tasa_diaria * Decimal(dias_atraso)
        return round_money(mora)

    @classmethod
    def aplicar_pago(
        cls,
        monto_pago: Decimal,
        mora_pendiente: Decimal,
        interes_pendiente: Decimal,
        saldo_capital: Decimal,
    ) -> DesglosePago:
        """
        Aplica un abono o pago siguiendo el orden legal y financiero:
        1. Mora
        2. Intereses corrientes
        3. Capital
        Cualquier excedente queda registrado como saldo a favor / remanente.
        """
        disponible = round_money(monto_pago)

        # 1. Cubrir mora
        mora_cubierta = min(disponible, mora_pendiente)
        disponible -= mora_cubierta

        # 2. Cubrir interés
        interes_cubierto = min(disponible, interes_pendiente)
        disponible -= interes_cubierto

        # 3. Cubrir capital
        capital_cubierto = min(disponible, saldo_capital)
        disponible -= capital_cubierto

        nuevo_saldo = round_money(saldo_capital - capital_cubierto)
        remanente = disponible

        return DesglosePago(
            monto_recibido=round_money(monto_pago),
            mora_cubierta=mora_cubierta,
            interes_cubierto=interes_cubierto,
            capital_cubierto=capital_cubierto,
            remanente_a_favor=remanente,
            nuevo_saldo_capital=nuevo_saldo,
        )
