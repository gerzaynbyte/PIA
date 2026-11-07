"""Reglas del agregado Order: RN-07 (por SKU), RN-08/10, RN-11/12/13, RN-19/20,
rehidratación y Value Objects de soporte."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.domain.entities.order import Order, OrderProps
from src.domain.shared.entity import Entity, Identifier
from src.domain.value_objects.money import Money
from src.domain.value_objects.order_item import SKU, OrderItem
from src.domain.value_objects.order_status import OrderStatus
from src.domain.value_objects.role import Rol, normalizar_rol

CLIENTE = Identifier("c1e4b10a-1111-4aaa-8bbb-2ccc333d4444")


def _it(sku="ALIM-DOG-01", qty=1, price="100"):
    return OrderItem(SKU(sku), qty, Money(Decimal(price)))


def _order(items=None):
    return Order.create(CLIENTE, items or [_it(qty=2)]).value


def _pagado():
    o = _order()
    assert not o.confirm_payment(o.total_amount).is_failure
    return o


# ---------- RN-07: el límite es por SKU, no por línea ----------
def test_rn07_dos_lineas_del_mismo_sku_se_suman():
    r = Order.create(CLIENTE, [_it(qty=50), _it(qty=50)])
    assert r.is_failure and "RN-07" in r.error


def test_lineas_repetidas_dentro_del_limite_se_consolidan():
    o = Order.create(CLIENTE, [_it(qty=20), _it(qty=10)]).value
    assert len(o.items) == 1 and o.items[0].quantity == 30
    assert o.total_amount.amount == Decimal("3000.00")


def test_mismo_sku_con_precios_distintos_se_rechaza():
    r = Order.create(CLIENTE, [_it(qty=1, price="100"), _it(qty=1, price="120")])
    assert r.is_failure and "precios" in r.error


# ---------- RN-08 / RN-10 ----------
def test_tercer_intento_con_monto_incorrecto_cancela_el_pedido():
    o = _order()
    mal = Money(Decimal("1"))
    assert "no coincide" in o.confirm_payment(mal).error and o.status == OrderStatus.PENDIENTE_PAGO
    assert o.confirm_payment(mal).is_failure and o.status == OrderStatus.PENDIENTE_PAGO
    r = o.confirm_payment(mal)
    assert r.is_failure and "RN-08" in r.error
    assert o.status == OrderStatus.CANCELADO_PAGO_EXPIRADO and o.payment_attempts == 3


def test_solo_se_paga_un_pedido_pendiente_y_expira_si_no_se_paga():
    o = _pagado()
    assert o.confirm_payment(o.total_amount).is_failure
    assert o.expirar_pago().is_failure
    p = _order()
    assert not p.expirar_pago().is_failure and p.status == OrderStatus.CANCELADO_PAGO_EXPIRADO


def test_pago_confirmado_registra_la_referencia_de_rn11():
    assert _pagado().payment_confirmed_at is not None


def test_antifraude_se_aprueba_con_avanzar_y_fija_la_referencia_rn11():
    o = Order.create(CLIENTE, [_it(qty=50, price="400")]).value
    o.confirm_payment(o.total_amount)
    assert o.status == OrderStatus.EN_REVISION_ANTIFRAUDE and o.payment_confirmed_at is None
    assert not o.avanzar(OrderStatus.PAGO_CONFIRMADO).is_failure
    assert o.payment_confirmed_at is not None
    assert o.avanzar(OrderStatus.ENTREGADO).is_failure        # salto ilegal


# ---------- RN-11 ----------
def test_rn11_la_ventana_cuenta_desde_el_pago_no_desde_la_creacion():
    o = _order()
    o._props.created_at = datetime.now(timezone.utc) - timedelta(hours=5)   # creado hace 5 h
    o.confirm_payment(o.total_amount)                                       # pagado ahora
    assert not o.cancel("CLIENTE", "me equivoqué").is_failure
    assert o.status == OrderStatus.CANCELADO


def test_rn11_fuera_de_ventana_se_rechaza():
    o = _pagado()
    o._props.payment_confirmed_at = datetime.now(timezone.utc) - timedelta(hours=3)
    r = o.cancel("CLIENTE", "x")
    assert r.is_failure and "RN-11" in r.error and o.status == OrderStatus.PAGO_CONFIRMADO


def test_rn11_cliente_no_autocancela_en_estados_posteriores():
    o = _pagado()
    o._set_status(OrderStatus.EMPACADO)
    r = o.cancel("CLIENTE", "x")
    assert r.is_failure and "RN-11" in r.error


def test_cliente_cancela_pedido_sin_pagar():
    assert not _order().cancel("CLIENTE", "").is_failure


# ---------- RN-12 ----------
def test_rn12_agente_cancela_pre_transito_con_motivo_y_destino():
    o = _pagado()
    o._set_status(OrderStatus.EMPACADO)
    assert o.cancel("AGENTE_ATENCION", "cliente llamó", "INVENTARIO").is_failure is False
    assert o.status == OrderStatus.CANCELADO
    ev = o.domain_events[-1]
    assert ev.destino_producto == "INVENTARIO" and ev.requested_by_role == "AGENTE_ATENCION"


def test_rn12_exige_destino_y_motivo():
    assert "inventario" in _pagado().cancel("AGENTE", "motivo", "").error
    assert "motivo" in _pagado().cancel("AGENTE", "  ", "MERMA_EMPAQUE").error


# ---------- RN-13 ----------
def test_rn13_en_transito_solo_supervisor_y_queda_cancelado_excepcional():
    o = _pagado()
    o._set_status(OrderStatus.EN_TRANSITO)
    assert "RN-13" in o.cancel("AGENTE", "x", "INVENTARIO").error
    assert "RN-13" in o.cancel("CLIENTE", "x").error
    assert not o.cancel("SUPERVISOR", "autorizado por excepción").is_failure
    assert o.status == OrderStatus.CANCELADO_EXCEPCIONAL


@pytest.mark.parametrize("estado", [OrderStatus.ENTREGADO, OrderStatus.CANCELADO,
                                    OrderStatus.FINALIZADO_EXITOSO])
def test_no_se_cancela_un_pedido_ya_cerrado_o_entregado(estado):
    o = _pagado()
    o._set_status(estado)
    r = o.cancel("SUPERVISOR", "x")
    assert r.is_failure and "no permitida" in r.error.lower()
    assert o.status == estado


def test_rol_desconocido_no_puede_cancelar():
    assert "no autorizado" in _pagado().cancel("AGENTE_ALMACEN", "x").error


# ---------- RN-19 / RN-20 ----------
def test_rn19_rechazo_en_sitio_solo_en_transito():
    o = _pagado()
    assert o.registrar_rechazo_en_sitio().is_failure
    o._set_status(OrderStatus.EN_TRANSITO)
    assert not o.registrar_rechazo_en_sitio().is_failure
    assert o.status == OrderStatus.DEVOLUCION_INMEDIATA_RECHAZO
    assert o.domain_events[-1].reason == "RECHAZO_EN_SITIO"


def test_devolucion_solo_desde_entregado():
    o = _pagado()
    assert o.iniciar_devolucion().is_failure
    o._set_status(OrderStatus.EN_TRANSITO)
    o.avanzar(OrderStatus.ENTREGADO)
    assert not o.iniciar_devolucion().is_failure and o.status == OrderStatus.EN_PROCESO_DEVOLUCION


def test_asignar_almacen():
    o = _order()
    assert o.asignar_almacen("").is_failure
    assert not o.asignar_almacen("ALMACEN_NORTE").is_failure and o.warehouse_id == "ALMACEN_NORTE"


# ---------- rehidratación (bug: faltaba _domain_events) ----------
def test_pedido_hidratado_puede_cancelarse_y_no_trae_eventos():
    ahora = datetime.now(timezone.utc)
    props = OrderProps(CLIENTE, [_it()], OrderStatus.PAGO_CONFIRMADO, Money(Decimal("100")),
                       ahora, ahora, payment_confirmed_at=ahora)
    o = Order.rehydrate("abc-123", props)
    assert o.domain_events == []
    assert not o.cancel("CLIENTE", "x").is_failure
    assert len(o.domain_events) == 1


# ---------- Value Objects y base ----------
def test_money_acepta_float_e_int_como_decimal():
    assert Money(100.5).amount == Decimal("100.5")
    assert Money(3).amount == Decimal("3")
    with pytest.raises(ValueError):
        Money(-1)
    assert Money(Decimal("5")).is_greater_than(4)
    with pytest.raises(ValueError):
        Money.zero("MXN").add(Money(Decimal("1"), "USD"))
    assert Money.zero("USD").currency == "USD"


def test_sku_y_cantidad_invalidos():
    with pytest.raises(ValueError):
        SKU("ab")
    with pytest.raises(ValueError):
        OrderItem(SKU("ALIM-DOG-01"), 0, Money(Decimal("1")))


def test_identifier_y_entity():
    with pytest.raises(ValueError):
        Identifier("")
    with pytest.raises(ValueError):
        Entity(None)
    a, b = Entity({"x": 1}, Identifier("1")), Entity({"x": 2}, Identifier("1"))
    assert a == b and hash(a) == hash(b) and a != "otro"
    assert Identifier("1") == Identifier("1") and Identifier("1") != "1"
    a.add_domain_event("e")
    assert a.domain_events == ["e"]
    a.clear_events()
    assert a.domain_events == [] and Entity({"x": 3}).id is not None


def test_normalizar_rol_acepta_alias():
    assert normalizar_rol("agente") == Rol.AGENTE_ATENCION
    assert normalizar_rol("SUPERVISOR") == Rol.SUPERVISOR_ATENCION
    assert normalizar_rol("SUPERVISOR_ALMACEN") == Rol.SUPERVISOR_ALMACEN
    assert normalizar_rol("hacker") is None and normalizar_rol("") is None


def test_str_del_identificador_es_el_valor_y_cabe_en_la_bd():
    """Regresión: str(order.id) devolvía 'Identifier(value=...)' (no cabía en VARCHAR(36))."""
    o = _order()
    assert str(Identifier("abc")) == "abc"
    assert len(str(o.id)) == 36 and "Identifier" not in str(o.id)


def test_rn02_entregado_puede_finalizarse_por_la_matriz():
    """RN-02: la transición existe; el plazo de 5 días hábiles sin reclamo lo debe
    disparar un job programado (trabajo futuro)."""
    o = _pagado()
    o._set_status(OrderStatus.EN_TRANSITO)
    assert not o.avanzar(OrderStatus.ENTREGADO).is_failure
    assert not o.avanzar(OrderStatus.FINALIZADO_EXITOSO).is_failure
    assert o.avanzar(OrderStatus.EN_PROCESO_DEVOLUCION).is_failure     # estado terminal
