"""Adaptador MySQL del puerto InventoryRepository (opción A: global por SKU).
Implementa la misma semántica de InMemoryInventoryRepository pero persistente:

- Fórmula del glosario: disponible = física - reservada.
- Concurrencia entre instancias: cada mutación es un UPDATE condicional dentro
  de una transacción; si alguna fila no cumple la condición (rowcount == 0)
  se hace ROLLBACK completo -> la reserva es todo-o-nada, como en InMemory.
- Revalidación RN-05: la reserva sigue vigente solo si las existencias físicas
  respaldan lo reservado (p. ej. tras un faltante físico RN-15).
- Siembra: si la tabla está vacía al arrancar, se llena desde data/catalogo.csv
  (capacidad_o_stock), igual que _inventario_dev() en modo dev.
"""
import asyncio
from pathlib import Path
from typing import Dict, Iterable, Tuple

from mysql.connector import pooling

from src.domain.shared.result import Result

Lineas = Iterable[Tuple[str, int]]

_CATALOGO = Path(__file__).resolve().parents[2] / "data" / "catalogo.csv"


class MySQLInventoryRepository:

    def __init__(self, pool: pooling.MySQLConnectionPool) -> None:
        self._pool = pool

    # ---------- interno ----------
    @staticmethod
    def _normalizar(items: Lineas) -> Dict[str, int]:
        totales: Dict[str, int] = {}
        for sku, cantidad in items:
            totales[sku] = totales.get(sku, 0) + cantidad
        return totales

    @staticmethod
    def _cerrar(conn, cur=None) -> None:
        if cur is not None:
            cur.close()
        conn.close()

    # ---------- puerto ----------
    async def disponibles_por_sku(self, skus: Iterable[str]) -> Dict[str, int]:
        return await asyncio.to_thread(self._disponibles_sync, set(skus))

    def _disponibles_sync(self, skus: set) -> Dict[str, int]:
        conn = self._pool.get_connection()
        cur = conn.cursor()
        try:
            marcadores = ", ".join(["%s"] * len(skus)) if skus else "''"
            cur.execute(
                f"SELECT sku, GREATEST(0, physical_stock - reserved_stock) "
                f"FROM inventory WHERE sku IN ({marcadores})", tuple(skus))
            hallados = {sku: int(disp) for sku, disp in cur.fetchall()}
            return {s: hallados.get(s, 0) for s in skus}
        finally:
            self._cerrar(conn, cur)

    async def reservar(self, items: Lineas) -> Result[None]:        # RN-04
        return await asyncio.to_thread(self._reservar_sync,
                                       self._normalizar(items))

    def _reservar_sync(self, requerido: Dict[str, int]) -> Result[None]:
        conn = self._pool.get_connection()
        cur = conn.cursor()
        try:
            for sku, cant in requerido.items():
                # UPDATE condicional: solo descuenta si hay disponibilidad real
                cur.execute(
                    "UPDATE inventory "
                    "SET reserved_stock = reserved_stock + %s "
                    "WHERE sku = %s AND physical_stock - reserved_stock >= %s",
                    (cant, sku, cant))
                if cur.rowcount == 0:          # sin stock o SKU inexistente
                    conn.rollback()            # deshace los SKU ya tocados
                    cur.execute(
                        "SELECT GREATEST(0, physical_stock - reserved_stock) "
                        "FROM inventory WHERE sku = %s", (sku,))
                    fila = cur.fetchone()
                    disp = int(fila[0]) if fila else 0
                    return Result.fail(
                        f"Existencia insuficiente del SKU {sku}: "
                        f"solicitadas {cant}, disponibles {disp}.")
            conn.commit()                      # todo-o-nada
            return Result.ok()
        finally:
            self._cerrar(conn, cur)

    async def revalidar(self, items: Lineas) -> Result[None]:       # RN-05
        return await asyncio.to_thread(self._revalidar_sync,
                                       self._normalizar(items))

    def _revalidar_sync(self, requerido: Dict[str, int]) -> Result[None]:
        """Misma semántica que InMemory: la física total debe respaldar lo
        reservado total del SKU (las reservas de todos los checkouts vivos)."""
        conn = self._pool.get_connection()
        cur = conn.cursor()
        try:
            for sku in requerido:
                cur.execute(
                    "SELECT physical_stock, reserved_stock "
                    "FROM inventory WHERE sku = %s", (sku,))
                fila = cur.fetchone()
                fisica = int(fila[0]) if fila else 0
                reservada = int(fila[1]) if fila else 0
                if fisica < reservada:
                    conn.rollback()
                    return Result.fail(
                        f"RN-05: existencias insuficientes al revalidar el SKU {sku}.")
            conn.commit()          # solo lecturas; commit libera la conexión
            return Result.ok()
        finally:
            self._cerrar(conn, cur)

    async def consumar(self, items: Lineas) -> Result[None]:        # pago exitoso
        return await asyncio.to_thread(self._consumar_sync,
                                       self._normalizar(items))

    def _consumar_sync(self, requerido: Dict[str, int]) -> Result[None]:
        conn = self._pool.get_connection()
        cur = conn.cursor()
        try:
            for sku, cant in requerido.items():
                cur.execute(
                    "UPDATE inventory "
                    "SET physical_stock = physical_stock - %s, "
                    "    reserved_stock = GREATEST(0, reserved_stock - %s) "
                    "WHERE sku = %s AND physical_stock >= %s",
                    (cant, cant, sku, cant))
                if cur.rowcount == 0:
                    conn.rollback()
                    return Result.fail(
                        f"RN-05: existencias físicas del SKU {sku} "
                        f"desaparecieron antes del cobro.")
            conn.commit()
            return Result.ok()
        finally:
            self._cerrar(conn, cur)

    async def liberar(self, items: Lineas) -> None:                 # RN-10 / fallos
        await asyncio.to_thread(self._liberar_sync, self._normalizar(items))

    def _liberar_sync(self, requerido: Dict[str, int]) -> None:
        conn = self._pool.get_connection()
        cur = conn.cursor()
        try:
            for sku, cant in requerido.items():
                cur.execute(
                    "UPDATE inventory "
                    "SET reserved_stock = GREATEST(0, reserved_stock - %s) "
                    "WHERE sku = %s", (cant, sku))
            conn.commit()
        finally:
            self._cerrar(conn, cur)

    # ---------- siembra y soporte de pruebas / RN-15 ----------
    def sembrar_si_vacia(self) -> None:
        """Idempotente: llena la tabla desde data/catalogo.csv si no hay filas."""
        conn = self._pool.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM inventory")
            fila = cur.fetchone()
            total = int(fila[0]) if fila else 0
            if total > 0:
                conn.commit()
                return
            try:
                from src.infrastructure.csv_petmarket_repository import cargar_catalogo
                stock = {sku: r.capacidad_o_stock
                         for sku, r in cargar_catalogo(_CATALOGO).items()}
            except OSError:
                stock = {}
            if stock:
                cur.executemany(
                    "INSERT IGNORE INTO inventory (sku, physical_stock, "
                    "reserved_stock) VALUES (%s, %s, 0)",
                    list(stock.items()))
            conn.commit()
        finally:
            self._cerrar(conn, cur)

    def resembrar(self, stock: Dict[str, int]) -> None:
        """Soporte de pruebas: trunca y siembra un stock base conocido."""
        conn = self._pool.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM inventory")
            cur.executemany(
                "INSERT INTO inventory (sku, physical_stock, reserved_stock) "
                "VALUES (%s, %s, 0)", list(stock.items()))
            conn.commit()
        finally:
            self._cerrar(conn, cur)

    def report_discrepancia(self, sku: str, conteo_fisico: int) -> None:  # RN-15
        conn = self._pool.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE inventory SET physical_stock = GREATEST(0, %s) "
                "WHERE sku = %s", (conteo_fisico, sku))
            conn.commit()
        finally:
            self._cerrar(conn, cur)