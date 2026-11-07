"""Specifications del paquete de pruebas PetMarket (LEEME.txt).
puede_procesarse     = ActorActivo AND DetalleNoVacio AND Autorizado
beneficio_referencia = ActorPreferente AND TotalMinimo AND NOT PromocionActiva"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Tuple

from .specifications import AndSpecification, NotSpecification, Specification

UMBRAL_BENEFICIO = Decimal("1500.00")

@dataclass(frozen=True)
class ContextoOperacion:
    """Datos que las specifications evalúan (inyectados por el runner)."""
    actor_activo: bool
    actor_preferente: bool
    autorizado: bool
    total: Decimal
    promocion_activa: bool
    num_lineas: int

class ActorActivoSpecification(Specification):
    def is_satisfied_by(self, c: ContextoOperacion) -> bool:
        return c.actor_activo

class ActorPreferenteSpecification(Specification):
    def is_satisfied_by(self, c: ContextoOperacion) -> bool:
        return c.actor_preferente

class DetalleNoVacioSpecification(Specification):
    def is_satisfied_by(self, c: ContextoOperacion) -> bool:
        return c.num_lineas > 0

class AutorizacionSpecification(Specification):
    def is_satisfied_by(self, c: ContextoOperacion) -> bool:
        return c.autorizado

class TotalMinimoSpecification(Specification):
    def __init__(self, umbral: Decimal = UMBRAL_BENEFICIO) -> None:
        self._umbral = umbral

    def is_satisfied_by(self, c: ContextoOperacion) -> bool:
        return c.total >= self._umbral

class PromocionActivaSpecification(Specification):
    def is_satisfied_by(self, c: ContextoOperacion) -> bool:
        return c.promocion_activa

def puede_procesarse() -> Specification:      # Composición AND/AND
    return (ActorActivoSpecification()
            .and_(DetalleNoVacioSpecification())
            .and_(AutorizacionSpecification()))

def beneficio_referencia() -> Specification:  # Composición AND + NOT
    return (ActorPreferenteSpecification()
            .and_(TotalMinimoSpecification())
            .and_(NotSpecification(PromocionActivaSpecification())))