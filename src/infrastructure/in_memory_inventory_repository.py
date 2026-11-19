"""Adaptador InMemory del puerto InventoryRepository (Global por SKU).

En el checkout aún no se sabe de qué almacén saldrá el pedido (RN-14 ocurre
post-pago), así que la reserva bloquea la DISPONIBILIDAD AGREGADA por SKU:
disponible = física(agregada) - reservada(agregada)  [Glosario §2].

La revalidación RN-05 verifica que la reserva siga respaldada por existencias
físicas (p. ej. tras un faltante físico RN-15 detectado entre reserva y pago).
"""
from typing import Dict, Iterable, Tuple

from src.domain.shared.result import Result

Lineas = Iterable[Tuple[str, int]]


class InMemoryInventoryRepository:
    def __init__(self, fisico_por_sku: Dict[str, int] | None = None) -> None:
        self._fisico: Dict[str, int] = dict(fisico_por_sku or {})
        self._reservado: Dict[str, int] = {}

    # ---------- interno ----------
    @staticmethod
    def _normalizar(items: Lineas) -> Dict[str, int]:
        totales: Dict[str, int] = {}
        for sku, cantidad in items:
            totales[sku] = totales.get(sku, 0) + cantidad
        return totales

    # ---------- puerto ----------
    async def disponibles_por_sku(self, skus: Iterable[str]) -> Dict[str, int]:
        return {s: max(0, self._fisico.get(s, 0) - self._reservado.get(s, 0))
                for s in set(skus)}

    async def reservar(self, items: Lineas) -> Result[None]:      # RN-04
        """Atómico a nivel proceso: valida TODO antes de tocar estado."""
        requerido = self._normalizar(items)
        for sku, cant in requerido.items():
            disp = max(0, self._fisico.get(sku, 0) - self._reservado.get(sku, 0))
            if disp < cant:
                return Result.fail(
                    f"Existencia insuficiente del SKU {sku}: "
                    f"solicitadas {cant}, disponibles {disp}.")
        for sku, cant in requerido.items():
            self._reservado[sku] = self._reservado.get(sku, 0) + cant
        return Result.ok()

    async def revalidar(self, items: Lineas) -> Result[None]:     # RN-05
        """La reserva sigue vigente solo si las existencias físicas respaldan
        todo lo reservado (un faltante físico puede haberlas reducido)."""
        for sku, _ in self._normalizar(items).items():
            if self._fisico.get(sku, 0) < self._reservado.get(sku, 0):
                return Result.fail(f"RN-05: existencias insuficientes al "                                 f"revalidar el SKU {sku}.")
        return Result.ok()

    async def consumar(self, items: Lineas) -> Result[None]:      # pago exitoso
        """El reservado se convierte en salida física (vendido)."""
        for sku, cant in self._normalizar(items).items():
            fis = self._fisico.get(sku, 0)
            if fis < cant:
                return Result.fail(f"RN-05: existencias físicas del SKU {sku} "
                                    f"desaparecieron antes del cobro.")
            self._fisico[sku] = fis - cant
            self._reservado[sku] = max(0, self._reservado.get(sku, 0) - cant)
        return Result.ok()

    async def liberar(self, items: Lineas) -> None:               # RN-10 / fallos
        for sku, cant in self._normalizar(items).items():
            self._reservado[sku] = max(0, self._reservado.get(sku, 0) - cant)

    # ---------- soporte de pruebas / RN-15 ----------
    def report_discrepancia(self, sku: str, conteo_fisico: int) -> None:
        self._fisico[sku] = max(0, conteo_fisico)