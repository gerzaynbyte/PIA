"""Servicio de Dominio: asignación automática de almacén de origen (RN-14)."""
from dataclasses import dataclass
from typing import Dict, List, Sequence

from ..shared.result import Result
from ..specifications_warehouse import (CandidatoAlmacen, ItemPedido,
                                        PreferenciaAlmacenSpecification,
                                        StockSuficienteSpecification)
from ..value_objects.warehouse import WarehouseId

ROLES_PUEDEN_ASIGNAR = frozenset({"SISTEMA", "SUPERVISOR_ALMACEN"})
# RN-14: un Agente de Almacén NO puede reasignar el origen manualmente.


@dataclass(frozen=True)
class AsignacionAlmacen:
    warehouse_id: WarehouseId
    candidatos_evaluados: int


class WarehouseAssignmentService:

    def __init__(self) -> None:
        self._preferencia = PreferenciaAlmacenSpecification()

    def asignar(
        self,
        items: Sequence[ItemPedido],
        candidatos: Sequence[CandidatoAlmacen],
        rol_solicitante: str = "SISTEMA",
    ) -> Result[AsignacionAlmacen]:
        if rol_solicitante not in ROLES_PUEDEN_ASIGNAR:
            return Result.fail(
                "RN-14: Un Agente de Almacén no puede reasignar el almacén "
                "de origen; la asignación es automática."
            )

        if not items:
            return Result.fail("El pedido no contiene ítems a surtir.")

        if not candidatos:
            return Result.fail("No hay almacenes candidatos disponibles.")

        # 1. Filtro duro por Specification: ¿este almacén cubre el 100%?
        stock_ok = StockSuficienteSpecification(items)
        viables: List[CandidatoAlmacen] = [
            c for c in candidatos if stock_ok.is_satisfied_by(c)
        ]

        if not viables:
            sin_cobertura = self._skus_sin_cobertura_unica(items, candidatos)
            faltantes = self._calcular_faltantes(items, candidatos)
            return Result.fail(
                "RN-16 (disparador): ningún almacén cubre el 100% del stock; "
                "se requiere división en sub-envíos. "
                f"SKU sin cobertura en un solo almacén (faltante por almacén): {sin_cobertura}. "
                f"Faltantes globales: {faltantes}"
            )

        # 2. Selección por preferencia RN-14: cercanía OR(=, menor carga)
        mejor = viables[0]
        for candidato in viables[1:]:
            if self._preferencia.es_preferido_sobre(candidato, mejor):
                mejor = candidato

        return Result.ok(AsignacionAlmacen(mejor.warehouse_id, len(viables)))

    @staticmethod
    def _skus_sin_cobertura_unica(
        items: Sequence[ItemPedido], candidatos: Sequence[CandidatoAlmacen]
    ) -> Dict[str, int]:
        """SKU que ningún almacén por sí solo cubre, con lo que le falta al mejor."""
        resultado: Dict[str, int] = {}
        requerido: Dict[str, int] = {}
        for sku, cantidad in items:
            requerido[sku] = requerido.get(sku, 0) + cantidad
        for sku, cantidad in requerido.items():
            mejor = max((c.stock_por_sku.get(sku, 0) for c in candidatos), default=0)
            if mejor < cantidad:
                resultado[sku] = cantidad - mejor
        return resultado

    @staticmethod
    def _calcular_faltantes(
        items: Sequence[ItemPedido], candidatos: Sequence[CandidatoAlmacen]
    ) -> Dict[str, int]:
        faltantes: Dict[str, int] = {}
        for sku, cantidad in items:
            total_disponible = sum(c.stock_por_sku.get(sku, 0) for c in candidatos)
            if total_disponible < cantidad:
                faltantes[sku] = cantidad - total_disponible
        return faltantes