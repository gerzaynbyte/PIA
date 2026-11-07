"""Agregado Delivery: gestión de intentos de entrega y excepciones (RN-17, RN-18).

Flujo normativo (BPMN PetMarket):
    EN_TRANSITO --(1er intento falla)--> EN_TRANSITO (contador=1)
    EN_TRANSITO --(2do intento falla)--> REGRESO_ALMACEN        (RN-17)
    REGRESO_ALMACEN --(contacto registrado)--> CONTACTO_CLIENTE
    CONTACTO_CLIENTE --(cliente responde)--> REPROGRAMADA       (RN-17)
    CONTACTO_CLIENTE --(silencio >= 5 días hábiles)--> REEMBOLSADO_AUTOMATICO (RN-18)
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from ..shared.calendario import dias_habiles_entre  # noqa: F401  (re-export)
from ..shared.entity import Entity, Identifier
from ..shared.result import Result
from ..value_objects.delivery_status import DeliveryStatus

MAX_INTENTOS_ENTREGA = 2        # RN-17
PLAZO_RESPUESTA_DIAS_HABILES = 5  # RN-18

@dataclass(frozen=True)
class IntentoEntrega:
    """Registro inmutable de un intento de la paquetería (trazabilidad del
    actor externo 'Paquetería', BRD §5)."""
    fecha: datetime
    exitoso: bool
    motivo_falla: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.exitoso and not self.motivo_falla:
            raise ValueError("Un intento fallido debe registrar el motivo de la falla.")
        if self.exitoso and self.motivo_falla:
            raise ValueError("Un intento exitoso no registra motivo de falla.")

@dataclass
class DeliveryProps:
    sub_order_id: str
    tracking_number: str
    status: DeliveryStatus
    intentos: List[IntentoEntrega] = field(default_factory=list)
    fecha_contacto: Optional[datetime] = None   # dispara el conteo de RN-18

class Delivery(Entity[Identifier, DeliveryProps]):

    @property
    def status(self) -> DeliveryStatus:
        return self._props.status

    @property
    def tracking_number(self) -> str:
        return self._props.tracking_number

    @property
    def intentos(self) -> List[IntentoEntrega]:
        return list(self._props.intentos)

    @property
    def intentos_fallidos(self) -> int:
        return sum(1 for i in self._props.intentos if not i.exitoso)

    @classmethod
    def create(cls, sub_order_id: str, tracking_number: str) -> Result["Delivery"]:
        if not tracking_number:
            return Result.fail("Un sub-envío en tránsito requiere guía de rastreo.")
        return Result.ok(cls(DeliveryProps(
            sub_order_id=sub_order_id,
            tracking_number=tracking_number,
            status=DeliveryStatus.EN_TRANSITO,
        )))

    def _set_status(self, s: DeliveryStatus) -> None:
        self._props.status = s

    # ---------- RN-17: registro de intentos ----------
    def registrar_intento(self, exitoso: bool,
                          motivo: Optional[str] = None,
                          fecha: Optional[datetime] = None) -> Result[DeliveryStatus]:
        """La paquetería reporta el resultado del intento.

        - Exitoso  -> ENTREGADO (camino feliz).
        - Fallido  -> si es el 2do fallo, REGRESO_ALMACEN (RN-17);
                      si es el 1ro, permanece EN_TRANSITO para el intento
                      del día hábil siguiente.
        """
        if self._props.status != DeliveryStatus.EN_TRANSITO:
            return Result.fail(
                f"Solo se registran intentos en EN_TRANSITO (actual: {self._props.status.value})."
            )

        intento = IntentoEntrega(
            fecha=fecha or datetime.now(timezone.utc),
            exitoso=exitoso,
            motivo_falla=motivo,
        )
        self._props.intentos.append(intento)

        if exitoso:
            self._set_status(DeliveryStatus.ENTREGADO)
            return Result.ok(DeliveryStatus.ENTREGADO)

        if self.intentos_fallidos >= MAX_INTENTOS_ENTREGA:
            self._set_status(DeliveryStatus.REGRESO_ALMACEN)
            return Result.ok(DeliveryStatus.REGRESO_ALMACEN)

        return Result.ok(DeliveryStatus.EN_TRANSITO)  # esperando 2do intento

    # ---------- RN-17: contacto tras retorno ----------
    def registrar_contacto_cliente(self, fecha: Optional[datetime] = None) -> Result[None]:
        """Atención al Cliente contacta al cliente tras el retorno del paquete.
        La marca de tiempo del contacto inicia el plazo de 5 días hábiles (RN-18)."""
        if self._props.status != DeliveryStatus.REGRESO_ALMACEN:
            return Result.fail(
                "Solo se contacta al cliente cuando el paquete regresó a almacén (RN-17)."
            )
        self._props.fecha_contacto = fecha or datetime.now(timezone.utc)
        self._set_status(DeliveryStatus.CONTACTO_CLIENTE)
        return Result.ok()

    # ---------- RN-17: cliente respondió ----------
    def reprogramar(self, fecha_respuesta: Optional[datetime] = None) -> Result[None]:
        if self._props.status != DeliveryStatus.CONTACTO_CLIENTE:
            return Result.fail("Solo se reprograma tras el contacto post-retorno (RN-17).")
        if self._responde_fuera_de_plazo(fecha_respuesta):
            return Result.fail(
                "RN-18: La respuesta llegó después de 5 días hábiles; "
                "procede reembolso automático, no reprogramación."
            )
        self._set_status(DeliveryStatus.REPROGRAMADA)
        return Result.ok()

    # ---------- RN-18: reembolso automático ----------
    def resolver_por_inactividad(self, fecha_actual: Optional[datetime] = None) -> Result[None]:
        """Cierra por excepción (RN-03) si el cliente no respondió en plazo.
        Idempotente: re-invocar no cambia nada ni duplica el reembolso."""
        if self._props.status == DeliveryStatus.REEMBOLSADO_AUTOMATICO:
            return Result.ok()
        if self._props.status != DeliveryStatus.CONTACTO_CLIENTE:
            return Result.fail(
                "El reembolso automático solo aplica tras contacto sin respuesta (RN-18)."
            )
        if not self._responde_fuera_de_plazo(fecha_actual):
            return Result.fail("Aún está vigente el plazo de 5 días hábiles (RN-18).")
        self._set_status(DeliveryStatus.REEMBOLSADO_AUTOMATICO)
        return Result.ok()

    # ---------- interno ----------
    def _responde_fuera_de_plazo(self, fecha: Optional[datetime]) -> bool:
        assert self._props.fecha_contacto is not None
        contacto = self._props.fecha_contacto
        fecha = fecha or datetime.now(timezone.utc)
        habiles = dias_habiles_entre(contacto.date(), fecha.date())
        return habiles > PLAZO_RESPUESTA_DIAS_HABILES