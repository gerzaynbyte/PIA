# src/domain/operacion_state_machine.py
from enum import Enum

class EstadoOperacion(str, Enum):
    CREADO = "CREADO"; PAGADO = "PAGADO"; SURTIDO = "SURTIDO"
    ENTREGADO = "ENTREGADO"; CANCELADO = "CANCELADO"

TRANSICIONES_VALIDAS = {
    EstadoOperacion.CREADO: [EstadoOperacion.PAGADO, EstadoOperacion.CANCELADO],
    EstadoOperacion.PAGADO: [EstadoOperacion.SURTIDO, EstadoOperacion.CANCELADO],
    EstadoOperacion.SURTIDO: [EstadoOperacion.ENTREGADO, EstadoOperacion.CANCELADO],
    EstadoOperacion.ENTREGADO: [],
    EstadoOperacion.CANCELADO: [],
}

class TransicionInvalidaError(Exception):
    """Salta al intentar un cambio de estado no contemplado en la matriz."""

def transicionar(actual: EstadoOperacion, nuevo: EstadoOperacion) -> EstadoOperacion:
    if nuevo not in TRANSICIONES_VALIDAS.get(actual, []):
        raise TransicionInvalidaError(
            f"Transición inválida: {actual.value} → {nuevo.value}")
    return nuevo