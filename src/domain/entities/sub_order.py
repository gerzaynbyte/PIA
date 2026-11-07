"""Entidad SubEnvio (RN-16): folio derivado y guía propios."""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

from ..shared.result import Result
from ..value_objects.order_status import OrderStatus

class EstadoSubEnvio(str, Enum):
    EN_PREPARACION = "EN_PREPARACION"
    EN_TRANSITO = "EN_TRANSITO"
    ENTREGADO = "ENTREGADO"

@dataclass
class SubEnvio:
    folio: str                                  # derivado del pedido padre
    warehouse_id: str
    items: List[Tuple[str, int]]
    status: EstadoSubEnvio = EstadoSubEnvio.EN_PREPARACION
    guia_rastreo: str = ""                      # asignada por paquetería

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("Un sub-envío no puede estar vacío.")
        if not self.folio:
            raise ValueError("Un sub-envío requiere folio derivado.")

    def asignar_guia(self, guia: str) -> Result[None]:
        if self.guia_rastreo:
            return Result.fail("La guía ya fue asignada y es inmutable.")
        if not guia:
            return Result.fail("La guía no puede estar vacía.")
        self.guia_rastreo = guia
        return Result.ok()

    def transicionar(self, nuevo: EstadoSubEnvio) -> Result[None]:
        legales = {
            EstadoSubEnvio.EN_PREPARACION: {EstadoSubEnvio.EN_TRANSITO},
            EstadoSubEnvio.EN_TRANSITO: {EstadoSubEnvio.ENTREGADO},
            EstadoSubEnvio.ENTREGADO: set(),
        }
        if nuevo not in legales[self.status]:
            return Result.fail(
                f"Transición inválida de sub-envío: {self.status.value} → {nuevo.value}."
            )
        if nuevo == EstadoSubEnvio.EN_TRANSITO and not self.guia_rastreo:
            return Result.fail("No se puede despachar un sub-envío sin guía de rastreo.")
        self.status = nuevo
        return Result.ok()