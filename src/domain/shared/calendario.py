"""Utilidades de calendario del dominio (días hábiles, lunes a viernes).

Convención del proyecto (RN-18, RN-20): el día del evento que inicia el
plazo cuenta como el día 1. No se modelan días festivos.
"""
from datetime import date, timedelta


def es_dia_habil(d: date) -> bool:
    return d.weekday() < 5  # lunes=0 ... viernes=4


def dias_habiles_entre(inicio: date, fin: date) -> int:
    """Cuenta días hábiles en [inicio, fin]. Si fin < inicio devuelve 0
    (el plazo nunca es negativo)."""
    if fin < inicio:
        return 0
    dias, cursor = 0, inicio
    while cursor <= fin:
        if es_dia_habil(cursor):
            dias += 1
        cursor += timedelta(days=1)
    return dias
