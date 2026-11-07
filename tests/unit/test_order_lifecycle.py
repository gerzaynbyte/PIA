from datetime import datetime, timedelta, timezone

import pytest

from src.domain.entities.order import Order
from src.domain.shared.entity import Identifier
from src.domain.state_machine import validate_transition_with_rules
from src.domain.value_objects.money import Money
from src.domain.value_objects.order_item import OrderItem, SKU
from src.domain.value_objects.order_status import OrderStatus


def _item(qty=1, price=100.0):
    return OrderItem(sku=SKU("ALIM-DOG-01"), quantity=qty, unit_price=Money(price))


def _order(attempts=0):
    result = Order.create(Identifier("c1e4b10a-1111-4aaa-8bbb-2ccc333d4444"), [_item(2)])
    assert not result.is_failure
    return result.value


# ---------- RN-11 ----------
def test_cliente_puede_autocancelar_dentro_de_2_horas():
    created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    v = validate_transition_with_rules(OrderStatus.PAGO_CONFIRMADO, OrderStatus.CANCELADO, "CLIENTE", created_at)
    assert v.allowed


def test_rechaza_autocancelacion_despues_de_2_horas_rn11():
    created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    v = validate_transition_with_rules(OrderStatus.PAGO_CONFIRMADO, OrderStatus.CANCELADO, "CLIENTE", created_at)
    assert not v.allowed
    assert "RN-11" in v.reason


# ---------- RN-13 ----------
def test_supervisor_requerido_para_cancelar_en_transito_rn13():
    v = validate_transition_with_rules(OrderStatus.EN_TRANSITO, OrderStatus.CANCELADO_EXCEPCIONAL, "AGENTE", datetime.now(timezone.utc))
    assert not v.allowed
    assert "RN-13" in v.reason


def test_supervisor_si_puede_cancelar_en_transito_rn13():
    v = validate_transition_with_rules(OrderStatus.EN_TRANSITO, OrderStatus.CANCELADO_EXCEPCIONAL, "SUPERVISOR", datetime.now(timezone.utc))
    assert v.allowed


# ---------- RN-07 / RN-08 / RN-09 (agregado Order) ----------
def test_create_rechaza_pedido_sin_items():
    r = Order.create(Identifier("x"), [])
    assert r.is_failure


def test_create_rechaza_mas_de_50_unidades_por_sku_rn07():
    with pytest.raises(ValueError, match="RN-07"):
        _item(qty=51)


def test_pago_con_exceso_de_intentos_cancela_rn08():
    order = _order()
    order.confirm_payment(order.total_amount)  # 1
    order._props.status = OrderStatus.PENDIENTE_PAGO
    order.confirm_payment(order.total_amount)  # 2
    order._props.status = OrderStatus.PENDIENTE_PAGO
    order.confirm_payment(order.total_amount)  # 3
    order._props.status = OrderStatus.PENDIENTE_PAGO
    r = order.confirm_payment(order.total_amount)  # 4 -> cancelado
    assert r.is_failure
    assert order.status == OrderStatus.CANCELADO_PAGO_EXPIRADO


def test_pedido_grande_va_a_antifraude_rn09():
    # 50 uds x $400 = $20,000 (RN-07 limita a 50 unidades por SKU)
    order = Order.create(Identifier("x"), [_item(qty=50, price=400)]).value
    r = order.confirm_payment(order.total_amount)
    assert not r.is_failure
    assert order.status == OrderStatus.EN_REVISION_ANTIFRAUDE