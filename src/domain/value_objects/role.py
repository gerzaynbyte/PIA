"""Vocabulario único de roles (Glosario §1). Acepta alias heredados."""
from enum import Enum
from typing import Optional


class Rol(str, Enum):
    CLIENTE = "CLIENTE"
    AGENTE_ATENCION = "AGENTE_ATENCION"
    SUPERVISOR_ATENCION = "SUPERVISOR_ATENCION"
    AGENTE_ALMACEN = "AGENTE_ALMACEN"
    SUPERVISOR_ALMACEN = "SUPERVISOR_ALMACEN"
    SISTEMA = "SISTEMA"


_ALIAS = {"AGENTE": Rol.AGENTE_ATENCION, "SUPERVISOR": Rol.SUPERVISOR_ATENCION}


def normalizar_rol(valor: str) -> Optional[Rol]:
    """Devuelve el Rol canónico o None si el texto no corresponde a un rol."""
    texto = (valor or "").strip().upper()
    if texto in _ALIAS:
        return _ALIAS[texto]
    try:
        return Rol(texto)
    except ValueError:
        return None
