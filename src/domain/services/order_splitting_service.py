"""Servicio de dominio RN-16: división del pedido entre almacenes.

Regla: si UN almacén cubre el 100 % del pedido, no hay división (se elige por
RN-14). Solo cuando ninguno lo cubre solo, se reparte cada línea hacia el
almacén más preferido (cercanía, luego carga) que tenga stock.
"""
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from ..shared.result import Result
from ..specifications_warehouse import (CandidatoAlmacen, ItemPedido,
                                        PreferenciaAlmacenSpecification,
                                        StockSuficienteSpecification)


@dataclass(frozen=True)
class AsignacionAlmacenLineas:
    warehouse_id: str
    items: List[ItemPedido]                     # cantidad cubierta por ese almacén


class OrderSplittingService:

    def __init__(self) -> None:
        self._preferencia = PreferenciaAlmacenSpecification()

    def _ordenar(self, candidatos: Sequence[CandidatoAlmacen]) -> List[CandidatoAlmacen]:
        """Orden RN-14: cercanía primero; en empate, menor carga (inserción estable)."""
        ordered = list(candidatos)
        for i in range(1, len(ordered)):
            c = ordered[i]
            j = i - 1
            while j >= 0 and self._preferencia.es_preferido_sobre(c, ordered[j]):
                ordered[j + 1] = ordered[j]
                j -= 1
            ordered[j + 1] = c
        return ordered

    def dividir(
        self, items: Sequence[ItemPedido], candidatos: Sequence[CandidatoAlmacen]
    ) -> Result[List[AsignacionAlmacenLineas]]:
        if not items:
            return Result.fail("El pedido no contiene ítems a dividir.")
        if len(candidatos) < 1:
            return Result.fail("No hay almacenes para surtir el pedido.")

        orden = self._ordenar(candidatos)

        # Un solo almacén cubre todo: no hay división; gana el más preferido (RN-14)
        cubre_todo = StockSuficienteSpecification(items)
        for c in orden:
            if cubre_todo.is_satisfied_by(c):
                return Result.ok([AsignacionAlmacenLineas(c.warehouse_id.value, list(items))])

        disponibilidad: Dict[Tuple[str, str], int] = {}
        for c in orden:
            for sku, cant in c.stock_por_sku.items():
                disponibilidad[(c.warehouse_id.value, sku)] = cant

        # Cobertura global: si ni sumando todo alcanza, no hay división posible
        for sku, cantidad in items:
            total = sum(v for (_, s), v in disponibilidad.items() if s == sku)
            if total < cantidad:
                return Result.fail(
                    f"Stock global insuficiente para {sku}: faltan "
                    f"{cantidad - total} unidades; no es divisible (RN-16).")

        # Asignación greedy por preferencia RN-14
        bolsas: Dict[str, List[ItemPedido]] = {}
        for sku, cantidad in items:
            pendiente = cantidad
            for c in orden:
                wid = c.warehouse_id.value
                tomar = min(disponibilidad.get((wid, sku), 0), pendiente)
                if tomar > 0:
                    bolsas.setdefault(wid, []).append((sku, tomar))
                    disponibilidad[(wid, sku)] -= tomar
                    pendiente -= tomar
                if pendiente == 0:
                    break

        return Result.ok([AsignacionAlmacenLineas(w, lines) for w, lines in bolsas.items()])
