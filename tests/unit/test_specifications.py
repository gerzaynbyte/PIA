from decimal import Decimal

from src.domain.entities.order import Order
from src.domain.operacion_state_machine import (EstadoOperacion, TransicionInvalidaError,
                                                transicionar)
from src.domain.shared.calendario import dias_habiles_entre, es_dia_habil
from src.domain.shared.entity import Identifier
from src.domain.specifications import (LimiteUnidadesPorSkuSpecification,
                                       RequiereRevisionAntifraudeSpecification,
                                       Specification)
from src.domain.specifications_warehouse import (CandidatoAlmacen, PreferenciaAlmacenSpecification,
                                                 StockSuficienteSpecification)
from src.domain.value_objects.money import Money
from src.domain.value_objects.order_item import SKU, OrderItem
from src.domain.value_objects.warehouse import DistanciaKm, WarehouseId
from datetime import date
import pytest


class _Siempre(Specification):
    def is_satisfied_by(self, c): return True


class _Nunca(Specification):
    def is_satisfied_by(self, c): return False


def test_composicion_and_or_not_como_metodos_de_la_clase_base():
    assert _Siempre().and_(_Nunca()).is_satisfied_by(1) is False
    assert _Siempre().or_(_Nunca()).is_satisfied_by(1) is True
    assert _Nunca().or_(_Nunca()).is_satisfied_by(1) is False
    assert _Nunca().not_().is_satisfied_by(1) is True
    assert _Siempre().and_(_Nunca().not_()).is_satisfied_by(1) is True


def _it(sku, qty):
    return OrderItem(SKU(sku), qty, Money(Decimal("10")))


def test_limite_por_sku_suma_las_lineas():
    spec = LimiteUnidadesPorSkuSpecification()
    assert spec.is_satisfied_by([_it("AAA", 50), _it("BBB", 50)])
    assert not spec.is_satisfied_by([_it("AAA", 30), _it("AAA", 30)])
    assert spec.excedentes([_it("AAA", 30), _it("AAA", 30)]) == {"AAA": 60}


def test_antifraude_usa_decimal_y_es_estrictamente_mayor():
    o = Order.create(Identifier("c"), [OrderItem(SKU("AAA"), 50, Money(Decimal("300")))]).value
    assert o.total_amount.amount == Decimal("15000.00")
    assert not RequiereRevisionAntifraudeSpecification().is_satisfied_by(o)   # = 15,000 no excede
    o2 = Order.create(Identifier("c"), [OrderItem(SKU("AAA"), 50, Money(Decimal("300.01")))]).value
    assert RequiereRevisionAntifraudeSpecification().is_satisfied_by(o2)


def test_specifications_de_almacen():
    norte = CandidatoAlmacen(WarehouseId.ALMACEN_NORTE, 5.0, 1, {"A": 3})
    sur = CandidatoAlmacen(WarehouseId.ALMACEN_SUR, 5.0, 4, {"A": 1})
    assert StockSuficienteSpecification([("A", 2), ("A", 1)]).is_satisfied_by(norte)
    assert not StockSuficienteSpecification([("A", 2)]).is_satisfied_by(sur)
    pref = PreferenciaAlmacenSpecification()
    assert pref.es_preferido_sobre(norte, sur) and not pref.es_preferido_sobre(sur, norte)
    assert pref.is_satisfied_by(norte)


def test_distancia_km():
    assert DistanciaKm(1.0) < DistanciaKm(2.0) and DistanciaKm(2.0) == DistanciaKm(2.0)
    assert DistanciaKm(1.0) != 1.0
    with pytest.raises(ValueError):
        DistanciaKm(-1)


def test_maquina_de_estados_del_paquete():
    assert transicionar(EstadoOperacion.CREADO, EstadoOperacion.PAGADO) == EstadoOperacion.PAGADO
    with pytest.raises(TransicionInvalidaError):
        transicionar(EstadoOperacion.CREADO, EstadoOperacion.ENTREGADO)


def test_calendario_habil():
    assert es_dia_habil(date(2026, 11, 6)) and not es_dia_habil(date(2026, 11, 7))
    assert dias_habiles_entre(date(2026, 11, 9), date(2026, 11, 6)) == 0
