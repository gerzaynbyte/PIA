"""Patrón Result: manejo explícito de éxito/fallo sin excepciones de control."""
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Result(Generic[T]):
    value: Optional[T] = None
    error: Optional[str] = None

    @property
    def is_failure(self) -> bool:
        return self.error is not None

    @classmethod
    def ok(cls, value: Optional[T] = None) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def fail(cls, error: str) -> "Result[T]":
        return cls(error=error)