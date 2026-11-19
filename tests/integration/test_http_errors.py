"""Contrato del mapeo mensaje-de-dominio -> HTTP.

Capa 1: el mapeador central funciona (orden, insensibilidad, defecto).
Capa 2: LOS MENSAJES REALES del dominio/aplicación contienen los tokens que
el mapeo espera. Así, editar un mensaje sin cuidado produce un rojo de
tests, no un bug silencioso de contrato HTTP.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.api.http_errors import (DEFECTO_CANCELACION, DEFECTO_DEVOLUCION,
                                DEFECTO_PAGO, DEFECTO_RESERVA,
                                REGLAS_CANCELACION, REGLAS_DEVOLUCION,
                                REGLAS_PAGO, REGLAS_RESERVA, estatus_http)
from src.domain.entities.order import Order
from src.domain.shared.entity import Identifier
from src.domain.value_objects.money import Money
from src.domain.value_objects.order_item import OrderItem, SKU
from src.domain.value_objects.order_status import OrderStatus
from src.infrastructure.in_memory_inventory_repository import InMemoryInventoryRepository

# ---------- Capa 1: el mapeador ----------
def test_primera_coincidencia_gana_y_el_defecto_cubre_el_resto():
    assert estatus_http("Pedido abc no encontrado.", REGLAS_CANCELACION,
                        DEFECTO_CANCELACION) == 404
    assert estatus_http("RN-11: ventana expirada", REGLAS_CANCELACION,
                        DEFECTO_CANCELACION) == 403          # defecto, no coincide regla

def test_insensible_a_mayusculas():
    assert estatus_http("EXISTENCIA INSUFICIENTE del SKU X",
                        REGLAS_RESERVA, DEFECTO_RESERVA) == 409

def test_mensaje_vacio_o_none_caen_al_defecto():
    assert estatus_http("", REGLAS_PAGO, DEFECTO_PAGO) == 402
    assert estatus_http(None, REGLAS_PAGO, DEFECTO_PAGO) == 402

def test_reglas_aplicadas_a_mensajes_tipicos():
    assert estatus_http("RN-05: existencias insuficientes al revalidar el SKU A",
                        REGLAS_PAGO, DEFECTO_PAGO) == 409
    assert estatus_http("RECHAZADO: El monto pagado no coincide.",
                        REGLAS_PAGO, DEFECTO_PAGO) == 402
    assert estatus_http("Transición no permitida de ENTREGADO a CANCELADO.",
                        REGLAS_CANCELACION, DEFECTO_CANCELACION) == 409
    assert estatus_http("RN-21: excepción bloqueada; debe escalarse al Supervisor.",
                        REGLAS_DEVOLUCION, DEFECTO_DEVOLUCION) == 403
    assert estatus_http("RN-20: solo se devuelve un pedido ENTREGADO.",
                        REGLAS_DEVOLUCION, DEFECTO_DEVOLUCION) == 400   # defecto

# ---------- Capa 2: contrato de mensajes ----------
def _item(sku="ALIM-DOG-01", qty=1, precio="100"):
    return OrderItem(SKU(sku), qty, Money(Decimal(precio)))

def _pagado():
    o = Order.create(Identifier("cliente-1"), [_item(qty=2)]).value
    o.confirm_payment(o.total_amount)
    return o

def test_contrato_reserva_stock_dice_insuficiente():
    inv = InMemoryInventoryRepository({})
    r = asyncio.run(inv.reservar([("ALIM-DOG-01", 1)]))
    assert "insuficiente" in r.error.lower()     # token de REGLAS_RESERVA -> 409

def test_contrato_cancelacion_por_estado_y_rol():
    # RN-11 expirada -> 403 (defecto)
    o = _pagado()
    o._props.payment_confirmed_at = datetime.now(timezone.utc) - timedelta(hours=3)
    assert "RN-11" in o.cancel("CLIENTE", "x").error
    # RN-13 (en tránsito, agente) -> 403 (defecto)
    o2 = _pagado()
    o2._set_status(OrderStatus.EN_TRANSITO)
    assert "RN-13" in o2.cancel("AGENTE", "x", "INVENTARIO").error
    # Matriz: "Transición no permitida" -> 409
    o3 = _pagado()
    o3._set_status(OrderStatus.ENTREGADO)
    assert "Transición no permitida" in o3.cancel("SUPERVISOR", "x").error
    # Inexistencia -> 404
    assert "no encontrado" in "Pedido zzz no encontrado."

def test_contrato_inexistencia_en_servicio_de_aplicacion():
    from src.application.order_application_service import OrderApplicationService
    from src.infrastructure.in_memory_inventory_repository import InMemoryInventoryRepository
    from src.infrastructure.in_memory_order_repository import InMemoryOrderRepository
    svc = OrderApplicationService(InMemoryOrderRepository(), InMemoryInventoryRepository({}))
    assert "no encontrado" in (asyncio.run(svc.get_order_details("zzz"))).error
    assert "no encontrado" in (asyncio.run(svc.cancel_order("zzz", "CLIENTE", ""))).error
    assert "no encontrado" in (asyncio.run(
        svc.create_return("zzz", "A", "CLIENTE", "NUEVO_SIN_USAR", None))).error

def test_contrato_rn21_usa_el_token_escal():
    """El token 'escal' (fragil) está anclado aquí: si el mensaje de RN-21
    cambia, este test lo señala y REGLAS_DEVOLUCION debe ajustarse a la par."""
    from src.application.order_application_service import OrderApplicationService
    from src.infrastructure.in_memory_inventory_repository import InMemoryInventoryRepository
    from src.infrastructure.in_memory_order_repository import InMemoryOrderRepository
    svc = OrderApplicationService(InMemoryOrderRepository(), InMemoryInventoryRepository({}))
    oid = (asyncio.run(svc.process_order_creation(
        "c", [("ALIM-DOG-01", 1, Decimal("100"))]))).value["orderId"]
    o = asyncio.run(svc._order_repo.find_by_id(oid))
    o._set_status(OrderStatus.EN_TRANSITO)
    o.avanzar(OrderStatus.ENTREGADO)
    o._props.delivered_at = datetime.now(timezone.utc) - timedelta(days=30)
    asyncio.run(svc._order_repo.save(o))
    r = asyncio.run(svc.create_return(oid, "ALIM-DOG-01", "AGENTE_ATENCION", "DANADO", "https://foto"))
    assert "escal" in r.error.lower()

def test_reserva_cerrada_responde_404_no_402():
    """Punto 7: una reserva eliminada (RN-08/RN-10/RN-05) es un recurso que
    ya no existe -> 404. El 402 queda reservado a pagos efectivamente rechazados."""
    assert estatus_http("Reserva inexistente; inicie el checkout de nuevo.",
                        REGLAS_PAGO, DEFECTO_PAGO) == 404
    assert estatus_http("RECHAZADO: El monto pagado no coincide con el total del pedido.",
                        REGLAS_PAGO, DEFECTO_PAGO) == 402
    assert estatus_http("RECHAZADO: Límite de 3 intentos de pago excedido (RN-08).",
                        REGLAS_PAGO, DEFECTO_PAGO) == 402

def test_contrato_reserva_inexistente_en_el_servicio():
    """Ancla del token 'inexistente': si el mensaje del servicio cambia,
    REGLAS_PAGO debe ajustarse a la par (capa 2 del contrato)."""
    from src.application.order_application_service import OrderApplicationService
    from src.infrastructure.in_memory_inventory_repository import InMemoryInventoryRepository
    from src.infrastructure.in_memory_order_repository import InMemoryOrderRepository
    svc = OrderApplicationService(InMemoryOrderRepository(), InMemoryInventoryRepository({}))
    r = asyncio.run(svc.process_payment("rid-que-nunca-existio", Decimal("100")))
    assert "inexistente" in r.error.lower()