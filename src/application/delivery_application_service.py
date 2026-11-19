"""Capa de Aplicación: ciclo de vida de la entrega (RN-17, RN-18) y puente
Delivery -> Order. Hace alcanzables los estados del pedido REGRESO_ALMACEN,
CONTACTO_CLIENTE y REEMBOLSADO_AUTOMATICO, que la matriz ya contemplaba.

Reglas del puente (espejo de RN-16):
- Cada sub-envío tiene su Delivery (clave = folio); un pedido indivisible
  usa el propio orderId como folio.
- El pedido padre solo se mueve cuando TODOS sus envíos unanimen un estado:
    REGRESO_ALMACEN      -> Order.REGRESO_ALMACEN
    CONTACTO_CLIENTE     -> Order.CONTACTO_CLIENTE
    REPROGRAMADA         -> Order.EN_TRANSITO (vuelve a ruta)
    REEMBOLSADO_AUTOMATICO -> Order.REEMBOLSADO_AUTOMATICO
- La entrega exitosa reutiliza order.registrar_entrega_sub_envio (RN-16),
  que además fija delivered_at (base de la ventana RN-20).
"""
from datetime import datetime
from typing import Dict, List, Optional, Protocol

from ..domain.entities.delivery import Delivery
from ..domain.entities.order import Order
from ..domain.shared.result import Result
from ..domain.value_objects.delivery_status import DeliveryStatus
from ..domain.value_objects.order_status import OrderStatus


class OrderRepository(Protocol):
    async def find_by_id(self, order_id: str) -> Optional[Order]: ...
    async def save(self, order: Order) -> None: ...

class DeliveryRepository(Protocol):
    async def save(self, delivery: Delivery) -> None: ...
    async def find_by_folio(self, folio: str) -> Optional[Delivery]: ...


_PUENTE: Dict[DeliveryStatus, OrderStatus] = {
    DeliveryStatus.REGRESO_ALMACEN: OrderStatus.REGRESO_ALMACEN,
    DeliveryStatus.CONTACTO_CLIENTE: OrderStatus.CONTACTO_CLIENTE,
    DeliveryStatus.REPROGRAMADA: OrderStatus.EN_TRANSITO,
    DeliveryStatus.REEMBOLSADO_AUTOMATICO: OrderStatus.REEMBOLSADO_AUTOMATICO,
}


class DeliveryApplicationService:

    def __init__(self, order_repo: OrderRepository, delivery_repo: DeliveryRepository) -> None:
        self._order_repo = order_repo
        self._delivery_repo = delivery_repo

    # ---------- interno ----------
    @staticmethod
    def _folios_de(order: Order) -> List[str]:
        return [s.folio for s in order.sub_orders] if order.is_split else [str(order.id)]

    async def _delivery_de(self, order: Order, folio: str, tracking: str) -> Result[Delivery]:
        """Obtiene o abre la entrega del folio. En pedidos divididos la guía
        viene del sub-envío; en indivisos, del reporte de la paquetería."""
        if folio not in self._folios_de(order):
            return Result.fail(f"Sub-envío {folio} no pertenece al pedido.")
        d = await self._delivery_repo.find_by_folio(folio)
        if d is not None:
            return Result.ok(d)
        if order.is_split:
            sub = next(s for s in order.sub_orders if s.folio == folio)
            tracking = sub.guia_rastreo
        if not tracking:
            return Result.fail("Se requiere guía de rastreo para abrir la entrega.")
        return Delivery.create(folio, tracking)

    async def _sincronizar_padre(self, order: Order) -> None:
        """Mueve al pedido padre si TODOS sus envíos unanimen un estado puente."""
        entregas = [await self._delivery_repo.find_by_folio(f)
                    for f in self._folios_de(order)]
        if not entregas or any(e is None for e in entregas):
            return
        estados = {e.status for e in entregas}
        if len(estados) != 1:
            return                      # mezcla de estados: el padre espera
        objetivo = _PUENTE.get(next(iter(estados)))
        if objetivo is None or order.status == objetivo:
            return                      # nada que hacer (o avanzar idempotente)
        order.avanzar(objetivo)         # la matriz garantiza que es legal

    async def _guardar_y_responder(self, order: Order, folio: str, delivery: Delivery) -> Result[dict]:
        await self._order_repo.save(order)
        return Result.ok({"folio": folio, "deliveryStatus": delivery.status.value, "orderStatus": order.status.value})

    # ---------- RN-17: intentos de la paquetería ----------
    async def reportar_intento(self, order_id: str, folio: str, exitoso: bool, motivo: str = "", tracking_number: str = "") -> Result[dict]:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            return Result.fail(f"Pedido {order_id} no encontrado.")
        r_abrir = await self._delivery_de(order, folio, tracking_number)
        if r_abrir.is_failure:
            return Result.fail(r_abrir.error)
        delivery = r_abrir.value

        r = delivery.registrar_intento(exitoso, motivo or None)
        if r.is_failure:
            return Result.fail(r.error)
        await self._delivery_repo.save(delivery)

        if r.value == DeliveryStatus.ENTREGADO:
            if order.is_split:
                rr = order.registrar_entrega_sub_envio(folio)   # RN-16: padre si todos
                if rr.is_failure:
                    return Result.fail(rr.error)
            else:
                rr = order.avanzar(OrderStatus.ENTREGADO)
                if rr.is_failure:
                    return Result.fail(rr.error)
        else:
            await self._sincronizar_padre(order)

        return await self._guardar_y_responder(order, folio, delivery)

    # ---------- RN-17: contacto post-retorno ----------
    async def contactar_cliente(self, order_id: str, folio: str,
                                fecha: Optional[datetime] = None) -> Result[dict]:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            return Result.fail(f"Pedido {order_id} no encontrado.")
        delivery = await self._delivery_repo.find_by_folio(folio)
        if delivery is None:
            return Result.fail(f"Entrega del sub-envío {folio} no encontrada.")
        r = delivery.registrar_contacto_cliente(fecha)   # inicia el plazo RN-18
        if r.is_failure:
            return Result.fail(r.error)
        await self._delivery_repo.save(delivery)
        await self._sincronizar_padre(order)
        return await self._guardar_y_responder(order, folio, delivery)

    # ---------- RN-17: el cliente respondió ----------
    async def reprogramar(self, order_id: str, folio: str, fecha_respuesta: Optional[datetime] = None) -> Result[dict]:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            return Result.fail(f"Pedido {order_id} no encontrado.")
        delivery = await self._delivery_repo.find_by_folio(folio)
        if delivery is None:
            return Result.fail(f"Entrega del sub-envío {folio} no encontrada.")
        r = delivery.reprogramar(fecha_respuesta)
        if r.is_failure:
            return Result.fail(r.error)
        await self._delivery_repo.save(delivery)
        await self._sincronizar_padre(order)   # unanimidad -> vuelve a EN_TRANSITO
        return await self._guardar_y_responder(order, folio, delivery)

    # ---------- RN-18: reembolso automático (job de inactividad) ----------
    async def resolver_por_inactividad(self, order_id: str, folio: str, fecha_actual: Optional[datetime] = None) -> Result[dict]:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            return Result.fail(f"Pedido {order_id} no encontrado.")
        delivery = await self._delivery_repo.find_by_folio(folio)
        if delivery is None:
            return Result.fail(f"Entrega del sub-envío {folio} no encontrada.")
        r = delivery.resolver_por_inactividad(fecha_actual)  # idempotente
        if r.is_failure:
            return Result.fail(r.error)
        await self._delivery_repo.save(delivery)
        await self._sincronizar_padre(order)
        return await self._guardar_y_responder(order, folio, delivery)