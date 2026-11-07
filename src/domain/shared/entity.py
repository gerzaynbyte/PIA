"""Base para Entidades y Agregados (DDD) con soporte de eventos de dominio."""
import uuid
from dataclasses import dataclass
from typing import Generic, List, Optional, Protocol, TypeVar

ID = TypeVar("ID")
T = TypeVar("T")


class ValueObject(Protocol):
    def __eq__(self, other: object) -> bool: ...


@dataclass(frozen=True)
class Identifier:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("El identificador no puede estar vacío.")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Identifier) and self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __str__(self) -> str:
        # str(id) se usa como folio, llave de BD y orderId de la API: debe ser
        # el valor, no la representación "Identifier(value=...)" del dataclass.
        return self.value


class Entity(Generic[ID, T]):
    def __init__(self, props: T, id_: Optional[ID] = None) -> None:
        if props is None:
            raise ValueError("Las propiedades de la entidad son obligatorias.")
        self._props = props
        self._id: ID = id_ if id_ is not None else Identifier(str(uuid.uuid4()))
        self._domain_events: List[object] = []

    @property
    def id(self) -> ID:
        return self._id

    @property
    def domain_events(self) -> List[object]:
        return list(self._domain_events)

    def add_domain_event(self, event: object) -> None:
        self._domain_events.append(event)

    def clear_events(self) -> None:
        self._domain_events.clear()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return type(self) is type(other) and self._id == other.id

    def __hash__(self) -> int:
        return hash(str(self._id))