"""RN-16 — División en sub-envíos cuando ningún almacén cubre el 100%."""
from decimal import Decimal

from src.domain.entities.order import Order, OrderProps
from src.domain.entities.sub_order import EstadoSubEnvio, SubEnvio
from src.domain.services.order_splitting_service import (AsignacionAlmacenLineas,
                                                         OrderSplittingService)
from src.domain.shared.entity import Identifier
from src.domain.specifications_warehouse import CandidatoAlmacen
from src.domain.value_objects.money import Money
from src.domain.value_objects.order_item import OrderItem, SKU
from src.domain.value_objects.order_status import OrderStatus
from src.domain.value_objects.warehouse import WarehouseId

# ---------- SplittingService ----------

def test_divide_en_dos_almacenes_cuando_ninguno_cubre_100():
    svc = OrderSplittingService()
    norte = CandidatoAlmacen(WarehouseId.ALMACEN_NORTE, 5.0, 2, {"SKU-A": 2})
    sur = CandidatoAlmacen(WarehouseId.ALMACEN_SUR, 9.0, 1, {"SKU-A": 3})

    r = svc.dividir([("SKU-A", 4)], [norte, sur])

    assert not r.is_failure
    asign = {a.warehouse_id: dict(a.items) for a in r.value}
    assert asign[WarehouseId.ALMACEN_NORTE.value] == {"SKU-A": 2}
    assert asign[WarehouseId.ALMACEN_SUR.value] == {"SKU-A": 2}

def test_preferencia_rn14_respetada_en_division():
    """Aunque el lejano tenga TODO el stock, el cercano aporta primero."""
    svc = OrderSplittingService()
    cercano = CandidatoAlmacen(WarehouseId.ALMACEN_NORTE, 2.0, 9, {"SKU-B": 1})
    lejano = CandidatoAlmacen(WarehouseId.ALMACEN_SUR, 30.0, 0, {"SKU-B": 3})

    r = svc.dividir([("SKU-B", 4)], [lejano, cercano])

    asign = {a.warehouse_id: dict(a.items) for a in r.value}
    assert asign[WarehouseId.ALMACEN_NORTE.value] == {"SKU-B": 1}   # cercano primero
    assert asign[WarehouseId.ALMACEN_SUR.value] == {"SKU-B": 3}

def test_stock_global_insuficiente_no_divide():
    svc = OrderSplittingService()
    r = svc.dividir(
        [("SKU-C", 5)],
        [CandidatoAlmacen(WarehouseId.ALMACEN_NORTE, 1.0, 0, {"SKU-C": 2}),
         CandidatoAlmacen(WarehouseId.ALMACEN_SUR, 2.0, 0, {"SKU-C": 2})],
    )
    assert r.is_failure and "SKU-C" in r.error

def test_un_solo_almacen_cubre_todo_sin_division():
    svc = OrderSplittingService()
    norte = CandidatoAlmacen(WarehouseId.ALMACEN_NORTE, 3.0, 1, {"SKU-D": 10})
    r = svc.dividir([("SKU-D", 4)], [norte])
    assert not r.is_failure and len(r.value) == 1

# ---------- Agregado Order ----------

def _pedido():
    r = Order.create(Identifier("9f"), [OrderItem(SKU("SKU-A"), 4, Money(Decimal("100")))])
    return r.value

def test_folios_derivados_y_padre_marcado_dividido():
    order = _pedido()
    asigs = [AsignacionAlmacenLineas("ALMACEN_NORTE", [("SKU-A", 2)]),
             AsignacionAlmacenLineas("ALMACEN_SUR", [("SKU-A", 2)])]

    r = order.dividir_en_sub_envios(asigs)

    assert not r.is_failure and r.value == 2
    assert order.is_split
    folios = [s.folio for s in order.sub_orders]
    assert len(set(folios)) == 2
    assert all(f.startswith(str(order.id)) for f in folios)  # folios derivados del padre

def test_division_doble_es_rechazada():
    order = _pedido()
    asigs = [AsignacionAlmacenLineas("ALMACEN_NORTE", [("SKU-A", 2)]),
             AsignacionAlmacenLineas("ALMACEN_SUR", [("SKU-A", 2)])]
    order.dividir_en_sub_envios(asigs)
    r = order.dividir_en_sub_envios(asigs)
    assert r.is_failure

def test_padre_entregado_solo_cuando_todos_los_sub_envios_llegan():
    """Cierre del BPMN: el estado del pedido padre condicionado a los hijos."""
    order = _pedido()
    order._set_status(OrderStatus.EN_TRANSITO)
    asigs = [AsignacionAlmacenLineas("ALMACEN_NORTE", [("SKU-A", 2)]),
             AsignacionAlmacenLineas("ALMACEN_SUR", [("SKU-A", 2)])]
    order.dividir_en_sub_envios(asigs)
    f1, f2 = [s.folio for s in order.sub_orders]
    for i, sub in enumerate(order.sub_orders, start=1):   # despacho: guía + EN_TRANSITO
        assert not sub.asignar_guia(f"GUIA-{i}").is_failure
        assert not sub.transicionar(EstadoSubEnvio.EN_TRANSITO).is_failure

    order.registrar_entrega_sub_envio(f1)
    assert order.status == OrderStatus.EN_TRANSITO      # aún falta uno

    r = order.registrar_entrega_sub_envio(f2)
    assert r.value == OrderStatus.ENTREGADO
    assert order.status == OrderStatus.ENTREGADO        # RN-16 satisfecha
    assert order.delivered_at is not None               # base de la ventana RN-20

def test_sub_envio_no_despacha_sin_guia():
    sub = SubEnvio(folio="X-S1", warehouse_id="ALMACEN_NORTE", items=[("SKU-A", 1)])
    r = sub.transicionar(EstadoSubEnvio.EN_TRANSITO)
    assert r.is_failure and "guía" in r.error.lower()

    assert not sub.asignar_guia("GAIA-0001").is_failure
    r = sub.transicionar(EstadoSubEnvio.EN_TRANSITO)
    assert not r.is_failure

def test_un_almacen_que_cubre_todo_gana_aunque_el_cercano_cubra_solo_parte():
    """RN-16: si UN almacén cubre el 100 %, no hay división (aunque el cercano cubra una línea)."""
    svc = OrderSplittingService()
    cercano = CandidatoAlmacen(WarehouseId.ALMACEN_NORTE, 2.0, 0, {"SKU-A": 5})
    lejano = CandidatoAlmacen(WarehouseId.ALMACEN_SUR, 30.0, 0, {"SKU-A": 5, "SKU-B": 5})
    r = svc.dividir([("SKU-A", 1), ("SKU-B", 1)], [cercano, lejano])
    assert not r.is_failure and len(r.value) == 1
    assert r.value[0].warehouse_id == WarehouseId.ALMACEN_SUR.value


def test_division_sin_items_o_sin_almacenes_falla():
    svc = OrderSplittingService()
    assert svc.dividir([], [CandidatoAlmacen(WarehouseId.ALMACEN_NORTE, 1.0, 0, {})]).is_failure
    assert svc.dividir([("SKU-A", 1)], []).is_failure


def test_entrega_de_subenvio_ajeno_o_sin_despachar_falla():
    order = _pedido()
    order._set_status(OrderStatus.EN_TRANSITO)
    assert order.registrar_entrega_sub_envio("NO-EXISTE").is_failure
    asigs = [AsignacionAlmacenLineas("ALMACEN_NORTE", [("SKU-A", 2)]),
             AsignacionAlmacenLineas("ALMACEN_SUR", [("SKU-A", 2)])]
    order.dividir_en_sub_envios(asigs)
    assert order.registrar_entrega_sub_envio(order.sub_orders[0].folio).is_failure


def test_dividir_exige_al_menos_dos_asignaciones():
    assert _pedido().dividir_en_sub_envios(
        [AsignacionAlmacenLineas("ALMACEN_NORTE", [("SKU-A", 4)])]).is_failure
