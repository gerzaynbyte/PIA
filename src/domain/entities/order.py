"""Agregado Raíz: Pedido Padre. RN-01, 07, 08, 09, 11, 12, 13, 16, 19, 20."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from ..events.order_events import OrderCancelledEvent, OrderCreatedEvent
from ..shared.entity import Entity, Identifier
from ..shared.result import Result
from ..specifications import (UMBRAL_ANTIFRAUDE_MXN,  # noqa: F401  (re-export)
                              LimiteUnidadesPorSkuSpecification,
                              RequiereRevisionAntifraudeSpecification)
from ..state_machine import (VENTANA_AUTOCANCELACION_HORAS,  # noqa: F401
                             can_transition, validate_transition_with_rules)
from ..value_objects.money import Money
from ..value_objects.order_item import OrderItem
from ..value_objects.order_status import OrderStatus
from ..value_objects.role import Rol, normalizar_rol
from .sub_order import EstadoSubEnvio, SubEnvio

MAX_INTENTOS_PAGO = 3


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@dataclass
class OrderProps:
    customer_id: Identifier
    items: List[OrderItem]
    status: OrderStatus
    total_amount: Money
    created_at: datetime
    updated_at: datetime
    warehouse_id: Optional[str] = None
    is_split: bool = False
    payment_attempts: int = 0
    sub_orders: List[SubEnvio] = field(default_factory=list)
    payment_confirmed_at: Optional[datetime] = None   # referencia de RN-11
    delivered_at: Optional[datetime] = None           # referencia de RN-20


class Order(Entity[Identifier, OrderProps]):

    # ---------- getters ----------
    @property
    def customer_id(self) -> Identifier: return self._props.customer_id
    @property
    def items(self) -> List[OrderItem]: return list(self._props.items)
    @property
    def status(self) -> OrderStatus: return self._props.status
    @property
    def total_amount(self) -> Money: return self._props.total_amount
    @property
    def created_at(self) -> datetime: return self._props.created_at
    @property
    def updated_at(self) -> datetime: return self._props.updated_at
    @property
    def payment_attempts(self) -> int: return self._props.payment_attempts
    @property
    def is_split(self) -> bool: return self._props.is_split
    @property
    def sub_orders(self) -> List[SubEnvio]: return list(self._props.sub_orders)
    @property
    def warehouse_id(self) -> Optional[str]: return self._props.warehouse_id
    @property
    def payment_confirmed_at(self) -> Optional[datetime]: return self._props.payment_confirmed_at
    @property
    def delivered_at(self) -> Optional[datetime]: return self._props.delivered_at

    # ---------- fábrica ----------
    @classmethod
    def create(cls, customer_id: Identifier, items: List[OrderItem]) -> Result["Order"]:
        if not items:  # RN-01
            return Result.fail("Un pedido debe contener al menos un producto.")

        limite = LimiteUnidadesPorSkuSpecification()  # RN-07: se suma por SKU, no por línea
        excedentes = limite.excedentes(items)
        if excedentes:
            sku, cantidad = next(iter(excedentes.items()))
            return Result.fail(
                f"El SKU {sku} excede el límite de 50 unidades por pedido "
                f"(RN-07): {cantidad} solicitadas.")

        consolidado = cls._consolidar(items)
        if consolidado.is_failure:
            return Result.fail(consolidado.error)
        items = consolidado.value

        total = Money.zero(items[0].unit_price.currency)
        for item in items:
            total = total.add(item.subtotal)

        ahora = datetime.now(timezone.utc)
        order = cls(OrderProps(
            customer_id=customer_id, items=items,
            status=OrderStatus.PENDIENTE_PAGO, total_amount=total,
            created_at=ahora, updated_at=ahora,
        ))
        order.add_domain_event(OrderCreatedEvent(
            aggregate_id=str(order.id),
            customer_id=customer_id.value,
            total_amount=total.amount))
        return Result.ok(order)

    @staticmethod
    def _consolidar(items: List[OrderItem]) -> Result[List[OrderItem]]:
        """Une las líneas repetidas del mismo SKU (una línea por SKU)."""
        por_sku: Dict[str, OrderItem] = {}
        for item in items:
            clave = item.sku.value
            previo = por_sku.get(clave)
            if previo is None:
                por_sku[clave] = item
            elif not previo.unit_price.equals(item.unit_price):
                return Result.fail(
                    f"El SKU {clave} aparece con precios unitarios distintos.")
            else:
                por_sku[clave] = OrderItem(item.sku, previo.quantity + item.quantity,
                                           previo.unit_price)
        return Result.ok(list(por_sku.values()))

    @classmethod
    def rehydrate(cls, order_id: str, props: OrderProps) -> "Order":
        """Reconstitución desde persistencia. NO valida ni emite eventos:
        crear es distinto de reconstruir (punto clave para la defensa)."""
        order = cls.__new__(cls)
        order._props = props
        order._id = Identifier(order_id)
        order._domain_events = []   # sin esto, cancelar un pedido hidratado fallaba
        return order

    # ---------- pago (RN-08, RN-09, RN-10) ----------
    def confirm_payment(self, amount_paid: Money) -> Result[None]:
        if self._props.status != OrderStatus.PENDIENTE_PAGO:
            return Result.fail("Solo se puede pagar un pedido en estatus PENDIENTE_PAGO.")
        self._props.payment_attempts += 1
        if self._props.payment_attempts > MAX_INTENTOS_PAGO:  # RN-08
            self._set_status(OrderStatus.CANCELADO_PAGO_EXPIRADO)
            return Result.fail("Límite de 3 intentos de pago excedido (RN-08). Pedido cancelado.")
        if not amount_paid.equals(self._props.total_amount):
            if self._props.payment_attempts >= MAX_INTENTOS_PAGO:
                self._set_status(OrderStatus.CANCELADO_PAGO_EXPIRADO)   # RN-10
                return Result.fail(
                    "El monto pagado no coincide con el total y se agotaron los 3 "
                    "intentos de pago (RN-08). Pedido cancelado.")
            return Result.fail("El monto pagado no coincide con el total del pedido.")
        if RequiereRevisionAntifraudeSpecification().is_satisfied_by(self):  # RN-09
            self._set_status(OrderStatus.EN_REVISION_ANTIFRAUDE)
        else:
            self._set_status(OrderStatus.PAGO_CONFIRMADO)
            self._props.payment_confirmed_at = self._props.updated_at
        return Result.ok()

    def expirar_pago(self) -> Result[None]:
        """RN-10: venció la ventana de pago (15 min) sin confirmar."""
        if self._props.status != OrderStatus.PENDIENTE_PAGO:
            return Result.fail("Solo expira el pago de un pedido PENDIENTE_PAGO.")
        self._set_status(OrderStatus.CANCELADO_PAGO_EXPIRADO)
        return Result.ok()

    # ---------- avance genérico validado por la matriz ----------
    def avanzar(self, nuevo: OrderStatus) -> Result[None]:
        """Avanza por la matriz de transiciones (p. ej. aprobación antifraude,
        preparación, empaque, despacho). Registra las marcas de tiempo de RN-11/RN-20."""
        if not can_transition(self._props.status, nuevo):
            return Result.fail(
                f"Transición no permitida de {self._props.status.value} a {nuevo.value}.")
        self._set_status(nuevo)
        if nuevo == OrderStatus.PAGO_CONFIRMADO:
            self._props.payment_confirmed_at = self._props.updated_at
        if nuevo == OrderStatus.ENTREGADO:
            self._props.delivered_at = self._props.updated_at
        return Result.ok()

    def asignar_almacen(self, warehouse_id: str) -> Result[None]:
        """Resultado de RN-14 (cercanía y carga)."""
        if not warehouse_id:
            return Result.fail("El almacén de origen es obligatorio.")
        self._props.warehouse_id = warehouse_id
        self._props.updated_at = datetime.now(timezone.utc)
        return Result.ok()

    # ---------- cancelación (RN-11, 12, 13) ----------
    def cancel(self, requested_by_role: str, reason: str,
               destino_producto: str = "") -> Result[None]:
        rol = normalizar_rol(requested_by_role)
        if rol not in (Rol.CLIENTE, Rol.AGENTE_ATENCION, Rol.SUPERVISOR_ATENCION):
            return Result.fail("Rol no autorizado para solicitar cancelaciones.")

        actual = self._props.status
        # RN-13: tras EN_TRANSITO la cancelación es excepcional (solo Supervisor)
        objetivo = (OrderStatus.CANCELADO_EXCEPCIONAL if actual == OrderStatus.EN_TRANSITO
                    else OrderStatus.CANCELADO)

        referencia = self._props.payment_confirmed_at or self._props.created_at
        validacion = validate_transition_with_rules(actual, objetivo, rol.value,
                                                    _utc(referencia))
        if not validacion.allowed:
            return Result.fail(validacion.reason or "Transición no permitida.")

        if rol != Rol.CLIENTE and not (reason or "").strip():
            return Result.fail("RN-12: registre el motivo de la cancelación.")
        if rol == Rol.AGENTE_ATENCION and destino_producto not in ("INVENTARIO", "MERMA_EMPAQUE"):
            return Result.fail("RN-12: registre si el producto se reintegra a inventario o es merma.")

        self._set_status(objetivo)
        self.add_domain_event(OrderCancelledEvent(
            aggregate_id=str(self.id), reason=reason,
            requested_by_role=rol.value,
            destino_producto=destino_producto))
        return Result.ok()

    # ---------- RN-19 ----------
    def registrar_rechazo_en_sitio(self) -> Result[None]:
        if self._props.status != OrderStatus.EN_TRANSITO:
            return Result.fail("Solo se rechaza en sitio un pedido EN_TRANSITO (RN-19).")
        self._set_status(OrderStatus.DEVOLUCION_INMEDIATA_RECHAZO)
        self.add_domain_event(OrderCancelledEvent(
            aggregate_id=str(self.id), reason="RECHAZO_EN_SITIO",
            requested_by_role=Rol.SISTEMA.value))
        return Result.ok()

    # ---------- RN-20 / RN-21 ----------
    def iniciar_devolucion(self) -> Result[None]:
        if self._props.status != OrderStatus.ENTREGADO:
            return Result.fail("Solo se devuelve un pedido ENTREGADO (RN-20).")
        self._set_status(OrderStatus.EN_PROCESO_DEVOLUCION)
        return Result.ok()

    # ---------- RN-16 ----------
    def dividir_en_sub_envios(self, asignaciones: list) -> Result[int]:
        if self._props.sub_orders and self._props.is_split:
            return Result.fail("El pedido ya fue dividido (RN-16).")
        if len(asignaciones) < 2:
            return Result.fail("RN-16 no aplica: un solo almacén cubre el pedido.")
        parent = str(self.id)
        for idx, asig in enumerate(asignaciones, start=1):
            self._props.sub_orders.append(SubEnvio(
                folio=f"{parent}-S{idx}",
                warehouse_id=asig.warehouse_id,
                items=[(sku, qty) for sku, qty in asig.items]))
        self._props.is_split = True
        self._props.updated_at = datetime.now(timezone.utc)
        return Result.ok(len(self._props.sub_orders))

    def registrar_entrega_sub_envio(self, folio: str) -> Result[Optional[OrderStatus]]:
        sub = next((s for s in self._props.sub_orders if s.folio == folio), None)
        if sub is None:
            return Result.fail(f"Sub-envío {folio} no pertenece al pedido.")
        r = sub.transicionar(EstadoSubEnvio.ENTREGADO)
        if r.is_failure:
            return Result.fail(r.error)
        if (self._props.status == OrderStatus.EN_TRANSITO
                and all(s.status == EstadoSubEnvio.ENTREGADO for s in self._props.sub_orders)):
            self.avanzar(OrderStatus.ENTREGADO)   # padre solo cuando TODOS llegan
            return Result.ok(OrderStatus.ENTREGADO)
        return Result.ok(None)

    # ---------- interno ----------
    def _set_status(self, new_status: OrderStatus) -> None:
        self._props.status = new_status
        self._props.updated_at = datetime.now(timezone.utc)
