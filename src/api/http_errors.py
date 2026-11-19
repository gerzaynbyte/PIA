"""Mapeo centralizado de errores de negocio -> códigos HTTP.

PROBLEMA QUE RESUELVE: los controllers decidían el status code con
substrings sueltos ("insuficiente", "escal"...). Si un mensaje del dominio
cambiaba una palabra, el contrato HTTP se rompía en silencio y sin tests.

DECISIÓN DE DISEÑO: la parte estable de los mensajes es el identificador de
la regla de negocio (RN-XX), porque es el vocabulario del BRD, no prosa
libre. Este módulo:
  1. Define las reglas token->HTTP por endpoint, en orden de prioridad.
  2. Ofrece `estatus_http()` como única puerta de entrada.
  3. Se apoya en tests/test_http_errors.py, que fija que los mensajes
     relevantes contienen los tokens esperados (contrato de mensajes).

Si mañana se quiere un contrato más rico, el siguiente paso natural es que
`Result` cargue un código estructural (Result.fail(msg, code="RN-13")); este
módulo es el punto de despegue para ello sin reescribir el dominio.
"""
from typing import List, Sequence, Tuple

# Par de mapeo: (token insensible a mayúsculas, código HTTP)
Regla = Tuple[str, int]

# --- Pedidos / checkout -------------------------------------------------
# RN-04: sin stock al reservar es conflicto de estado, no un 400 de validación.
REGLAS_RESERVA: List[Regla] = [
    ("insuficiente", 409),          # RN-04: Existencia insuficiente...
]
DEFECTO_RESERVA = 400               # datos inválidos (VOs: RN-01, RN-07, formato)

# RN-05 (revalidación al pagar) es conflicto de reserva; el resto de fallos
# del flujo de pago se interpretan como pago rechazado (incluye RN-08, 402).
REGLAS_PAGO: List[Regla] = [
    ("inexistente", 404),            # reserva inexistente (RN-05)
    ("rn-05", 409),                 # stock agotado en revalidación / ventana expirada
]
DEFECTO_PAGO = 402                  # RECHAZADO: monto, intentos, reserva inexistente

# --- Consulta -----------------------------------------------------------
# GET de un pedido: si falla, es inexistencia (la app solo falla por eso).
DEFECTO_CONSULTA = 404

# --- Cancelación (RN-11, 12, 13) ----------------------------------------
REGLAS_CANCELACION: List[Regla] = [
    ("no encontrado", 404),         # pedido inexistente
    ("transición no permitida", 409),  # estado actual no lo permite (matriz)
]
DEFECTO_CANCELACION = 403           # rol no autorizado / ventana RN-11 / RN-12

# --- Devoluciones (RN-20, RN-21) -----------------------------------------
REGLAS_DEVOLUCION: List[Regla] = [
    ("no encontrado", 404),         # pedido inexistente
    ("escal", 403),                 # RN-21: "...debe escalarse al Supervisor"
]
DEFECTO_DEVOLUCION = 400            # pedido no entregado, SKU ajeno, sin evidencia

# --- Entregas (RN-17, RN-18) ---------------------------------------------
REGLAS_ENTREGA: List[Regla] = [
    ("no encontrado", 404),         # pedido o entrega inexistente
]
DEFECTO_ENTREGA = 409               # estado actual no permite la operación


def estatus_http(mensaje: str, reglas: Sequence[Regla], defecto: int) -> int:
    """Única puerta de mapeo mensaje -> HTTP. Insensible a mayúsculas.

    Evalúa las reglas EN ORDEN: la primera coincidencia gana. Diseñado para
    reglas cortas y específicas primero (404) y genéricas después.
    """
    texto = (mensaje or "").lower()
    for token, codigo in reglas:
        if token in texto:
            return codigo
    return defecto