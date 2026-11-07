"""Máquina de estados del ciclo de vida del pedido (RN-11, 12, 13, 16, 17, 18)."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .value_objects.order_status import OrderStatus
from .value_objects.role import Rol, normalizar_rol

SystemRole = str  # 'CLIENTE' | 'AGENTE' | 'SUPERVISOR' | 'SISTEMA'

ALLOWED_TRANSITIONS: Dict[OrderStatus, List[OrderStatus]] = {
    OrderStatus.PENDIENTE_PAGO: [OrderStatus.PAGO_CONFIRMADO,
                                OrderStatus.EN_REVISION_ANTIFRAUDE,
                                OrderStatus.CANCELADO_PAGO_EXPIRADO,
                                OrderStatus.CANCELADO],
    OrderStatus.EN_REVISION_ANTIFRAUDE: [OrderStatus.PAGO_CONFIRMADO, OrderStatus.CANCELADO],
    OrderStatus.PAGO_CONFIRMADO: [OrderStatus.EN_PREPARACION, OrderStatus.CANCELADO],
    OrderStatus.EN_PREPARACION: [OrderStatus.EMPACADO, OrderStatus.CANCELADO],
    OrderStatus.EMPACADO: [OrderStatus.EN_TRANSITO, OrderStatus.CANCELADO],
    OrderStatus.EN_TRANSITO: [OrderStatus.ENTREGADO,
                            OrderStatus.CANCELADO_EXCEPCIONAL,
                            OrderStatus.DEVOLUCION_INMEDIATA_RECHAZO,
                            OrderStatus.REGRESO_ALMACEN],
    OrderStatus.REGRESO_ALMACEN: [OrderStatus.CONTACTO_CLIENTE],
    OrderStatus.CONTACTO_CLIENTE: [OrderStatus.EN_TRANSITO, OrderStatus.REEMBOLSADO_AUTOMATICO],
    OrderStatus.ENTREGADO: [OrderStatus.EN_PROCESO_DEVOLUCION, OrderStatus.FINALIZADO_EXITOSO],
    OrderStatus.EN_PROCESO_DEVOLUCION: [OrderStatus.DEVOLUCION_COMPLETADA],
    OrderStatus.CANCELADO_PAGO_EXPIRADO: [],
    OrderStatus.CANCELADO: [],
    OrderStatus.CANCELADO_EXCEPCIONAL: [],
    OrderStatus.DEVOLUCION_INMEDIATA_RECHAZO: [],
    OrderStatus.REEMBOLSADO_AUTOMATICO: [],
    OrderStatus.DEVOLUCION_COMPLETADA: [],
    OrderStatus.FINALIZADO_EXITOSO: [],
}


@dataclass(frozen=True)
class TransitionValidation:
    allowed: bool
    reason: Optional[str] = None


VENTANA_AUTOCANCELACION_HORAS = 2                      # RN-11
ESTADOS_AUTOCANCELABLES = (OrderStatus.PENDIENTE_PAGO,  # sin cobro: nada que reembolsar
                           OrderStatus.PAGO_CONFIRMADO,
                           OrderStatus.EN_PREPARACION)
ESTADOS_CON_VENTANA = (OrderStatus.PAGO_CONFIRMADO, OrderStatus.EN_PREPARACION)


def can_transition(current: OrderStatus, next_status: OrderStatus) -> bool:
    return next_status in ALLOWED_TRANSITIONS.get(current, [])


def validate_transition_with_rules(current_status: OrderStatus, target_status: OrderStatus,
                                   role: SystemRole,
                                   payment_confirmed_at: datetime) -> TransitionValidation:
    """Valida una transición contra la matriz y las reglas por rol y tiempo.

    `payment_confirmed_at` es la referencia de la ventana RN-11 (confirmación
    del pago, no la creación del pedido).
    """
    if not can_transition(current_status, target_status):
        return TransitionValidation(
            False,
            f"Transición no permitida de {current_status.value} a {target_status.value}.")

    rol = normalizar_rol(role)

    if (current_status == OrderStatus.EN_TRANSITO
            and target_status == OrderStatus.CANCELADO_EXCEPCIONAL
            and rol != Rol.SUPERVISOR_ATENCION):
        return TransitionValidation(
            False, "RN-13: la cancelación post-tránsito requiere autorización de un Supervisor.")

    if rol == Rol.CLIENTE and target_status == OrderStatus.CANCELADO:
        if current_status not in ESTADOS_AUTOCANCELABLES:
            return TransitionValidation(
                False, "RN-11: la autocancelación solo aplica en PAGO_CONFIRMADO o "
                       "EN_PREPARACION; contacte a Atención al Cliente.")
        if current_status in ESTADOS_CON_VENTANA:
            if payment_confirmed_at.tzinfo is None:
                payment_confirmed_at = payment_confirmed_at.replace(tzinfo=timezone.utc)
            horas = (datetime.now(timezone.utc) - payment_confirmed_at).total_seconds() / 3600
            if horas > VENTANA_AUTOCANCELACION_HORAS:
                return TransitionValidation(
                    False, "RN-11: la ventana de autocancelación libre de 2 horas ha expirado.")

    return TransitionValidation(True)
