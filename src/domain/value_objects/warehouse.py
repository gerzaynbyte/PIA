"""Value Objects del contexto logístico (RN-14)."""
from dataclasses import dataclass
from enum import Enum


class WarehouseId(str, Enum):
    """Solo existen dos almacenes en PetMarket (BRD §1)."""
    ALMACEN_NORTE = "ALMACEN_NORTE"
    ALMACEN_SUR = "ALMACEN_SUR"


@dataclass(frozen=True)
class DistanciaKm:
    """Distancia del almacén al domicilio de entrega. Se computa fuera
    (geocoding) y entra al dominio como valor ya calculado."""
    value: float

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("La distancia no puede ser negativa.")

    def __lt__(self, other: "DistanciaKm") -> bool:
        return self.value < other.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DistanciaKm) and self.value == other.value