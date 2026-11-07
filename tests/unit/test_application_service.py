"""Casos de uso de la capa de aplicación con el repositorio InMemory (sin BD)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.application.order_application_service import OrderApplicationService
from src.domain.value_objects.order_status import OrderStatus
from src.infrastructure.in_memory_order_repository import InMemoryOrderRepository

ITEMS = [("ALIM-DOG-01", 2, Decimal("100.00"))]


@pytest.fixture
def svc():
    return OrderApplicationService(InMemoryOrderRepository())


async def _pedido(svc, items=ITEMS):
    r = await svc.process_order_creation("cliente-1", items)
    assert not r.is_failure
    return r.value["orderId"]


async def _forzar(svc, order_id, estado, **props):
    o = await svc._order_repo.find_by_id(order_id)
    o._set_status(estado)
    for k, v in props.items():
        setattr(o._props, k, v)
    await svc._order_repo.save(o)
    return o


# ---------- alta y consulta ----------
async def test_crea_y_consulta_pedido(svc):
    oid = await _pedido(svc)
    d = (await svc.get_order_details(oid)).value
    assert d["status"] == "PENDIENTE_PAGO" and d["totalAmount"] == Decimal("200.00")
    assert d["isSplit"] is False and d["subOrders"] == [] and d["customerId"] == "cliente-1"


async def test_consulta_inexistente(svc):
    assert "no encontrado" in (await svc.get_order_details("zzz")).error


async def test_alta_rechaza_sin_items_rn01_y_mas_de_50_rn07(svc):
    assert "al menos un producto" in (await svc.process_order_creation("c", [])).error
    assert "RN-07" in (await svc.process_order_creation("c", [("ALIM-DOG-01", 51, Decimal("1"))])).error
    suma = [("ALIM-DOG-01", 50, Decimal("1")), ("ALIM-DOG-01", 1, Decimal("1"))]
    assert "RN-07" in (await svc.process_order_creation("c", suma)).error
    assert "inválido" in (await svc.process_order_creation("c", [("x", 1, Decimal("1"))])).error
    assert "customerId" in (await svc.process_order_creation("", ITEMS)).error


async def test_detalle_incluye_subenvios(svc):
    oid = await _pedido(svc)
    o = await svc._order_repo.find_by_id(oid)
    from src.domain.services.order_splitting_service import AsignacionAlmacenLineas
    o.dividir_en_sub_envios([AsignacionAlmacenLineas("ALMACEN_NORTE", [("ALIM-DOG-01", 1)]),
                             AsignacionAlmacenLineas("ALMACEN_SUR", [("ALIM-DOG-01", 1)])])
    d = (await svc.get_order_details(oid)).value
    assert d["isSplit"] and len(d["subOrders"]) == 2 and d["subOrders"][0]["folio"].startswith(oid)


async def test_transition_order_status(svc):
    ahora = datetime.now(timezone.utc)
    ok = await svc.transition_order_status(OrderStatus.PAGO_CONFIRMADO, OrderStatus.EN_PREPARACION,
                                           "SISTEMA", ahora)
    assert not ok.is_failure
    mal = await svc.transition_order_status(OrderStatus.ENTREGADO, OrderStatus.EN_PREPARACION,
                                            "SISTEMA", ahora)
    assert mal.is_failure


# ---------- reserva y pago (RN-04, 05, 08, 09, 10) ----------
async def test_reserva_y_pago_exitoso_persisten_el_pedido(svc):
    r = (await svc.reserve_stock("cliente-1", ITEMS)).value
    assert r["reservedItems"] == [{"sku": "ALIM-DOG-01", "quantity": 2, "unitPrice": 100.0}]
    p = await svc.process_payment(r["reservationId"], Decimal("200.00"))
    assert p.value["status"] == "PAGO_CONFIRMADO" and p.value["attemptsRemaining"] == 2
    assert (await svc.get_order_details(p.value["orderId"])).value["status"] == "PAGO_CONFIRMADO"
    assert "inexistente" in (await svc.process_payment(r["reservationId"], Decimal("200"))).error


async def test_reserva_valida_items(svc):
    assert "RN-07" in (await svc.reserve_stock("c", [("ALIM-DOG-01", 60, Decimal("1"))])).error
    assert (await svc.reserve_stock("c", [])).is_failure
    assert (await svc.reserve_stock("", ITEMS)).is_failure


async def test_rn08_tres_pagos_incorrectos_cancelan_y_persisten(svc):
    rid = (await svc.reserve_stock("c", ITEMS)).value["reservationId"]
    e1 = await svc.process_payment(rid, Decimal("1"))
    assert "Intentos restantes: 2" in e1.error
    e2 = await svc.process_payment(rid, Decimal("1"))
    assert "Intentos restantes: 1" in e2.error
    e3 = await svc.process_payment(rid, Decimal("1"))
    assert "RN-08" in e3.error
    assert "inexistente" in (await svc.process_payment(rid, Decimal("200"))).error
    cancelados = [o for o in svc._order_repo._store.values()
                  if o.status == OrderStatus.CANCELADO_PAGO_EXPIRADO]
    assert len(cancelados) == 1 and cancelados[0].payment_attempts == 3


async def test_pago_exitoso_tras_un_intento_fallido_descuenta_intentos(svc):
    rid = (await svc.reserve_stock("c", ITEMS)).value["reservationId"]
    assert (await svc.process_payment(rid, Decimal("5"))).is_failure
    ok = await svc.process_payment(rid, Decimal("200"))
    assert ok.value["attemptsRemaining"] == 1


async def test_rn09_pago_grande_va_a_revision_antifraude(svc):
    rid = (await svc.reserve_stock("c", [("ALIM-DOG-01", 50, Decimal("400"))])).value["reservationId"]
    assert (await svc.process_payment(rid, Decimal("20000"))).value["status"] == "EN_REVISION_ANTIFRAUDE"


async def test_rn10_reserva_expirada_cancela_el_pedido(svc):
    rid = (await svc.reserve_stock("c", ITEMS)).value["reservationId"]
    svc._reservas[rid]["expires"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    r = await svc.process_payment(rid, Decimal("200"))
    assert "RN-05" in r.error and rid not in svc._reservas
    assert [o.status for o in svc._order_repo._store.values()] == [OrderStatus.CANCELADO_PAGO_EXPIRADO]


async def test_monto_negativo_se_rechaza(svc):
    rid = (await svc.reserve_stock("c", ITEMS)).value["reservationId"]
    assert "inválido" in (await svc.process_payment(rid, Decimal("-5"))).error


# ---------- cancelación (RN-11/12/13) ----------
async def test_cancelacion_por_cliente_y_pedido_inexistente(svc):
    oid = await _pedido(svc)
    assert (await svc.cancel_order(oid, "CLIENTE", "")).value["status"] == "CANCELADO"
    assert "no encontrado" in (await svc.cancel_order("zzz", "CLIENTE", "")).error
    assert (await svc.cancel_order(oid, "CLIENTE", "")).is_failure        # ya cancelado


async def test_cancelacion_en_transito_requiere_supervisor(svc):
    oid = await _pedido(svc)
    await _forzar(svc, oid, OrderStatus.EN_TRANSITO)
    assert "RN-13" in (await svc.cancel_order(oid, "AGENTE", "x", "INVENTARIO")).error
    r = await svc.cancel_order(oid, "SUPERVISOR", "excepción")
    assert r.value["status"] == "CANCELADO_EXCEPCIONAL"


# ---------- devoluciones (RN-20/21) ----------
async def _entregado(svc, hace_dias=0):
    oid = await _pedido(svc)
    o = await _forzar(svc, oid, OrderStatus.EN_TRANSITO)
    o.avanzar(OrderStatus.ENTREGADO)
    o._props.delivered_at = datetime.now(timezone.utc) - timedelta(days=hace_dias)
    await svc._order_repo.save(o)
    return oid


async def test_rn20_devolucion_estandar_aprobada_mueve_el_pedido(svc):
    oid = await _entregado(svc)
    r = await svc.create_return(oid, "ALIM-DOG-01", "CLIENTE", "NUEVO_SIN_USAR", None)
    assert r.value["status"] == "APROBADA" and r.value["returnLabelUrl"].endswith(".pdf")
    assert (await svc.get_order_details(oid)).value["status"] == "EN_PROCESO_DEVOLUCION"


async def test_rn21_fuera_de_ventana_solo_supervisor_con_evidencia(svc):
    oid = await _entregado(svc, hace_dias=30)
    args = (oid, "ALIM-DOG-01")
    assert "RN-21" in (await svc.create_return(*args, "CLIENTE", "NUEVO_SIN_USAR", None)).error
    assert "RN-21" in (await svc.create_return(*args, "AGENTE_ATENCION", "DANADO", "u")).error
    assert "evidencia" in (await svc.create_return(*args, "SUPERVISOR", "DANADO", None)).error
    ok = await svc.create_return(*args, "SUPERVISOR_ATENCION", "DANADO", "https://foto")
    assert ok.value["status"] == "APROBADA_POR_EXCEPCION"


async def test_devolucion_valida_pedido_sku_estado_y_rol(svc):
    assert "no encontrado" in (await svc.create_return("zzz", "A", "CLIENTE", "x", None)).error
    sin_entregar = await _pedido(svc)
    assert "RN-20" in (await svc.create_return(sin_entregar, "ALIM-DOG-01", "CLIENTE",
                                               "NUEVO_SIN_USAR", None)).error
    oid = await _entregado(svc)
    assert "no pertenece" in (await svc.create_return(oid, "OTRO-SKU", "CLIENTE",
                                                      "NUEVO_SIN_USAR", None)).error
    assert "Rol no válido" in (await svc.create_return(oid, "ALIM-DOG-01", "AGENTE_ALMACEN",
                                                       "NUEVO_SIN_USAR", None)).error


async def test_devolucion_con_fecha_naive_de_bd(svc):
    """MySQL devuelve datetimes sin zona: no debe provocar TypeError."""
    oid = await _entregado(svc)
    o = await svc._order_repo.find_by_id(oid)
    o._props.delivered_at = datetime.utcnow()
    r = await svc.create_return(oid, "ALIM-DOG-01", "CLIENTE", "NUEVO_SIN_USAR", None)
    assert not r.is_failure
