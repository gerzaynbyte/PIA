from enum import Enum

class DeliveryStatus(str, Enum):
    """Estados del ciclo de vida de entrega (nivel sub-envío).

    Los tres últimos implementan la excepción RN-17/RN-18:
    falla doble -> regreso -> contacto -> (reprogramar | reembolso auto).
    """
    EN_TRANSITO = "EN_TRANSITO"
    ENTREGADO = "ENTREGADO"                    # camino feliz
    DEVOLUCION_INMEDIATA_RECHAZO = "DEVOLUCION_INMEDIATA_RECHAZO"  # RN-19
    REGRESO_ALMACEN = "REGRESO_ALMACEN"        # RN-17: 2 intentos fallidos
    CONTACTO_CLIENTE = "CONTACTO_CLIENTE"      # RN-17: atención contacta
    REPROGRAMADA = "REPROGRAMADA"              # cliente respondió a tiempo
    REEMBOLSADO_AUTOMATICO = "REEMBOLSADO_AUTOMATICO"  # RN-18: 5 días sin respuesta