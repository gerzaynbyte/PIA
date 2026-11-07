"""Capa de Aplicación: orquesta casos de uso sin lógica de negocio propia.
Depende de abstracciones de repositorio (inversión de dependencias, SOLID-D)."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Protocol

from ..domain.entities.order import MAX_INTENTOS_PAGO, Order
from ..domain.shared.calendario import dias_habiles_entre
from ..domain.shared.entity import Identifier
from ..domain.shared.result import Result
from ..domain.state_machine import validate_transition_with_rules
from ..domain.value_objects.money import Money
from ..domain.value_objects.order_item import SKU, OrderItem
from ..domain.value_objects.order_status import OrderStatus
from ..domain.value_objects.role import Rol, normalizar_rol

VENTANA_RESERVA_MIN = 15           # RN-04
VENTANA_DEVOLUCION_DIAS_HABILES = 5  # RN-20


class OrderRepository(Protocol):  # Puerto de salida (hexagonal)
    async def save(self, order: Order) -> None: ...
    async def find_by_id(self, order_id: str) -> Optional[Order]: ...


def _a_items(items: list) -> List[OrderItem]:
    """(sku, cantidad, precio) -> OrderItem. Propaga ValueError (SKU, RN-07 por VO)."""
    return [OrderItem(SKU(s), q, Money(p)) for s, q, p in items]


class OrderApplicationService:
    def __init__(self, order_repo: OrderRepository) -> None:
        self._order_repo = order_repo  # Inyectado, no instanciado aquí (SRP + DIP)
        # Reservas de checkout vigentes (RN-04). En memoria: válido para una sola
        # instancia de la API; con varias réplicas requeriría un almacén compartido.
        self._reservas: Dict[str, dict] = {}

    # ---------- RN-01 / RN-07: alta directa de pedido ----------
    async def process_order_creation(self, customer_id: str, items: list) -> Result[dict]:
        try:
            cid = Identifier(customer_id)
        except ValueError:
            return Result.fail("customerId inválido.")
        try:
            order_items = _a_items(items)
        except ValueError as e:
            return Result.fail(str(e))

        creado = Order.create(cid, order_items)
        if creado.is_failure:
            return Result.fail(creado.error)

        order = creado.value
        await self._order_repo.save(order)
        return Result.ok({
            "orderId": str(order.id),
            "status": order.status.value,
            "total": order.total_amount.amount,
        })

    # ---------- consulta (CQRS, ADR-03) ----------
    async def get_order_details(self, order_id: str) -> Result[dict]:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            return Result.fail(f"Pedido {order_id} no encontrado.")
        return Result.ok({
            "orderId": str(order.id),
            "customerId": order.customer_id.value,
            "status": order.status.value,
            "totalAmount": order.total_amount.amount,
            "isSplit": order.is_split,
            "subOrders": [
                {"folio": s.folio, "warehouseId": s.warehouse_id,
                 "status": s.status.value, "trackingNumber": s.guia_rastreo,
                 "items": [tuple(i) for i in s.items]}
                for s in order.sub_orders
            ],
        })

    async def transition_order_status(
        self, current_status: OrderStatus, target_status: OrderStatus,
        role: str, reference_at: datetime,
    ) -> Result[None]:
        validation = validate_transition_with_rules(current_status, target_status,
                                                    role, reference_at)
        if not validation.allowed:
            return Result.fail(validation.reason or "Transición no permitida.")
        return Result.ok()

    # ---------- RN-04: reserva de checkout ----------
    async def reserve_stock(self, customer_id: str, items: list) -> Result[dict]:
        try:
            cid = Identifier(customer_id)
            order_items = _a_items(items)
        except ValueError as e:
            return Result.fail(str(e) or "customerId inválido.")
        creado = Order.create(cid, order_items)       # RN-01 y RN-07 (suma por SKU)
        if creado.is_failure:
            return Result.fail(creado.error)
        order = creado.value

        rid = str(uuid.uuid4())
        expires = datetime.now(timezone.utc) + timedelta(minutes=VENTANA_RESERVA_MIN)
        self._reservas[rid] = {"order": order, "expires": expires}
        return Result.ok({
            "reservationId": rid, "expiresAt": expires,
            "reservedItems": [{"sku": i.sku.value, "quantity": i.quantity,
                               "unitPrice": float(i.unit_price.amount)}
                              for i in order.items]})

    # ---------- RN-05/08/09/10: pago ----------
    async def process_payment(self, reservation_id: str, amount: Decimal) -> Result[dict]:
        res = self._reservas.get(reservation_id)
        if res is None:
            return Result.fail("Reserva inexistente; inicie el checkout de nuevo.")
        order: Order = res["order"]

        if datetime.now(timezone.utc) > res["expires"]:                  # RN-10
            self._reservas.pop(reservation_id, None)
            order.expirar_pago()
            await self._order_repo.save(order)
            return Result.fail("RN-05/RN-10: la ventana de reserva de 15 minutos expiró.")

        try:
            monto = Money(amount)
        except ValueError:
            return Result.fail("RECHAZADO: monto de pago inválido.")

        r = order.confirm_payment(monto)                                 # RN-08/09
        if r.is_failure:
            if order.status == OrderStatus.CANCELADO_PAGO_EXPIRADO:      # agotó intentos
                self._reservas.pop(reservation_id, None)
                await self._order_repo.save(order)
                return Result.fail(f"RECHAZADO: {r.error}")
            restantes = max(0, MAX_INTENTOS_PAGO - order.payment_attempts)
            return Result.fail(f"RECHAZADO: {r.error} Intentos restantes: {restantes}.")

        self._reservas.pop(reservation_id, None)
        await self._order_repo.save(order)
        return Result.ok({"orderId": str(order.id), "status": order.status.value,
                          "transactionId": f"TX-{uuid.uuid4().hex[:12]}",
                          "attemptsRemaining": max(0, MAX_INTENTOS_PAGO - order.payment_attempts)})

    # ---------- RN-11/12/13: cancelación ----------
    async def cancel_order(self, order_id: str, role: str, reason: str,
                           destino: str = "") -> Result[dict]:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            return Result.fail(f"Pedido {order_id} no encontrado.")
        r = order.cancel(role, reason, destino_producto=destino)
        if r.is_failure:
            return Result.fail(r.error)
        await self._order_repo.save(order)
        return Result.ok({"orderId": order_id, "status": order.status.value})

    # ---------- RN-20/21: devoluciones ----------
    async def create_return(self, order_id: str, sku: str, role: str,
                            condition: str, evidence_url: Optional[str]) -> Result[dict]:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            return Result.fail(f"Pedido {order_id} no encontrado.")
        if order.status != OrderStatus.ENTREGADO:
            return Result.fail("RN-20: solo se devuelve un pedido ENTREGADO.")
        if sku not in {i.sku.value for i in order.items}:
            return Result.fail(f"El SKU {sku} no pertenece al pedido.")

        rol = normalizar_rol(role)
        entregado = order.delivered_at or order.updated_at
        if entregado.tzinfo is None:
            entregado = entregado.replace(tzinfo=timezone.utc)
        habiles = dias_habiles_entre(entregado.date(), datetime.now(timezone.utc).date())
        dentro_politica = (habiles <= VENTANA_DEVOLUCION_DIAS_HABILES
                           and condition == "NUEVO_SIN_USAR")

        if dentro_politica:
            if rol not in (Rol.CLIENTE, Rol.AGENTE_ATENCION, Rol.SUPERVISOR_ATENCION):
                return Result.fail("Rol no válido para devolución estándar.")
            estatus = "APROBADA"                                        # RN-20
        else:
            if rol != Rol.SUPERVISOR_ATENCION:
                return Result.fail("RN-21: excepción bloqueada; debe escalarse al Supervisor.")
            if not evidence_url:
                return Result.fail("RN-21: la excepción exige evidencia fotográfica.")
            estatus = "APROBADA_POR_EXCEPCION"                          # RN-21

        iniciada = order.iniciar_devolucion()
        if iniciada.is_failure:
            return Result.fail(iniciada.error)
        await self._order_repo.save(order)
        return Result.ok({"returnId": str(uuid.uuid4()), "status": estatus,
                          "returnLabelUrl":
                          f"https://labels.petmarket.local/{uuid.uuid4().hex[:8]}.pdf"})
