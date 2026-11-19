"""Puente Delivery -> Order (RN-17/18): los estados del pedido padre ahora
son alcanzables desde el ciclo de entrega del sub-envío."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.application.delivery_application_service import DeliveryApplicationService
from src.application.order_application_service import OrderApplicationService
from src.domain.entities.sub_order import EstadoSubEnvio
from src.domain.services.order_splitting_service import AsignacionAlmacenLineas
from src.domain.value_objects.order_status import OrderStatus
from src.infrastructure.in_memory_delivery_repository import InMemoryDeliveryRepository
from src.infrastructure.in_memory_inventory_repository import InMemoryInventoryRepository
from src.infrastructure.in_memory_order_repository import InMemoryOrderRepository

ITEMS = [("ALIM-DOG-01", 2, Decimal("100.00"))]
GUIA = "GUIA-1"   # la paquetería incluye la guía en su primer reporte (pedidos indivisos)


def _servicios():
    order_repo = InMemoryOrderRepository()
    order_svc = OrderApplicationService(
        order_repo, InMemoryInventoryRepository({"ALIM-DOG-01": 100}))
    return order_svc, DeliveryApplicationService(order_repo, InMemoryDeliveryRepository())


async def _en_transito(order_svc, dividido=False):
    r = await order_svc.process_order_creation("cliente-1", ITEMS)
    oid = r.value["orderId"]
    o = await order_svc._order_repo.find_by_id(oid)
    if dividido:
        o._set_status(OrderStatus.PAGO_CONFIRMADO)
        o.asignar_almacen("ALMACEN_NORTE")
        o.dividir_en_sub_envios([AsignacionAlmacenLineas("ALMACEN_NORTE", [("ALIM-DOG-01", 1)]),
                                 AsignacionAlmacenLineas("ALMACEN_SUR", [("ALIM-DOG-01", 1)])])
        for i, sub in enumerate(o.sub_orders, start=1):
            sub.asignar_guia(f"GUIA-{i}")
            sub.transicionar(EstadoSubEnvio.EN_TRANSITO)
    o._set_status(OrderStatus.EN_TRANSITO)
    await order_svc._order_repo.save(o)
    return oid

# ---------- pedido indiviso ----------
async def test_doble_fallo_retorna_y_sincroniza_el_pedido_rn17():
    order_svc, svc = _servicios()
    oid = await _en_transito(order_svc)
    r1 = await svc.reportar_intento(oid, oid, False, "Cliente ausente", GUIA)
    assert not r1.is_failure and r1.value["deliveryStatus"] == "EN_TRANSITO"
    assert r1.value["orderStatus"] == "EN_TRANSITO"          # 1er fallo: sigue en ruta
    r2 = await svc.reportar_intento(oid, oid, False, "Ausente de nuevo", GUIA)
    assert r2.value["deliveryStatus"] == "REGRESO_ALMACEN"
    assert r2.value["orderStatus"] == "REGRESO_ALMACEN"      # estado de pedido ahora alcanzable

async def test_contacto_y_reembolso_automatico_rn18_sincronizan_el_pedido():
    order_svc, svc = _servicios()
    oid = await _en_transito(order_svc)
    await svc.reportar_intento(oid, oid, False, "ausente", GUIA)
    await svc.reportar_intento(oid, oid, False, "ausente", GUIA)
    r = await svc.contactar_cliente(oid, oid, fecha=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc))
    assert r.value["orderStatus"] == "CONTACTO_CLIENTE"

    # job RN-18 con fecha fuera del plazo de 5 hábiles
    r = await svc.resolver_por_inactividad(oid, oid, datetime(2026, 11, 10, tzinfo=timezone.utc))
    assert r.value["deliveryStatus"] == "REEMBOLSADO_AUTOMATICO"
    assert r.value["orderStatus"] == "REEMBOLSADO_AUTOMATICO"
    r2 = await svc.resolver_por_inactividad(oid, oid, datetime(2026, 11, 11, tzinfo=timezone.utc))
    assert not r2.is_failure                                  # idempotente de punta a punta

async def test_cliente_responde_a_tiempo_y_el_pedido_vuelve_a_transito():
    order_svc, svc = _servicios()
    oid = await _en_transito(order_svc)
    await svc.reportar_intento(oid, oid, False, "ausente", GUIA)
    await svc.reportar_intento(oid, oid, False, "ausente", GUIA)
    contacto = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    await svc.contactar_cliente(oid, oid, fecha=contacto)
    r = await svc.reprogramar(oid, oid, fecha_respuesta=contacto + timedelta(days=2))
    assert r.value["deliveryStatus"] == "REPROGRAMADA"
    assert r.value["orderStatus"] == "EN_TRANSITO"            # reingresa a ruta (matriz)

async def test_respuesta_tardia_reembolsa_en_ambos_niveles():
    order_svc, svc = _servicios()
    oid = await _en_transito(order_svc)
    await svc.reportar_intento(oid, oid, False, "ausente", GUIA)
    await svc.reportar_intento(oid, oid, False, "ausente", GUIA)
    contacto = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    await svc.contactar_cliente(oid, oid, fecha=contacto)
    r = await svc.reprogramar(oid, oid, fecha_respuesta=contacto + timedelta(days=10))
    assert "RN-18" in r.error
    assert (await order_svc.get_order_details(oid)).value["status"] == "CONTACTO_CLIENTE"

async def test_primer_intento_exitoso_entrega_y_fija_delivered_at():
    order_svc, svc = _servicios()
    oid = await _en_transito(order_svc)
    r = await svc.reportar_intento(oid, oid, True, "", GUIA)
    assert r.value["orderStatus"] == "ENTREGADO"
    o = await order_svc._order_repo.find_by_id(oid)
    assert o.delivered_at is not None                          # ventana RN-20 disponible

async def test_tercer_intento_y_folios_ajenos_fallan():
    order_svc, svc = _servicios()
    oid = await _en_transito(order_svc)
    r = await svc.reportar_intento(oid, "FOLIO-DE-OTRO-PEDIDO", False, "x")
    assert "no pertenece" in r.error
    r = await svc.reportar_intento("no-existe", oid, False, "x")
    assert "no encontrado" in r.error

# ---------- pedido dividido (RN-16 + puente) ----------
async def test_padre_espera_la_unanimidad_de_sus_envios():
    order_svc, svc = _servicios()
    oid = await _en_transito(order_svc, dividido=True)
    f1, f2 = [s.folio for s in (await order_svc._order_repo.find_by_id(oid)).sub_orders]

    await svc.reportar_intento(oid, f1, False, "ausente")
    await svc.reportar_intento(oid, f1, False, "ausente")     # f1 regresa
    assert (await order_svc.get_order_details(oid)).value["status"] == "EN_TRANSITO"
    # f2 sigue en ruta: mezcla de estados -> el padre no se mueve

    await svc.reportar_intento(oid, f2, False, "ausente")
    await svc.reportar_intento(oid, f2, False, "ausente")     # f2 regresa también
    assert (await order_svc.get_order_details(oid)).value["status"] == "REGRESO_ALMACEN"

async def test_entrega_individual_del_subenvio_no_entrega_el_padre():
    order_svc, svc = _servicios()
    oid = await _en_transito(order_svc, dividido=True)
    o = await order_svc._order_repo.find_by_id(oid)
    f1, f2 = [s.folio for s in o.sub_orders]
    r = await svc.reportar_intento(oid, f1, True)
    assert r.value["deliveryStatus"] == "ENTREGADO"
    assert r.value["orderStatus"] == "EN_TRANSITO"            # falta f2 (RN-16)
    r2 = await svc.reportar_intento(oid, f2, True)
    assert r2.value["orderStatus"] == "ENTREGADO"             # todos llegaron -> padre ENTREGADO