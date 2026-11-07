"""Adaptador de infraestructura: persistencia MySQL 8 del agregado Order.
Implementa el puerto OrderRepository (ADR-02). El agregado se guarda y se
reconstruye completo (pedido + líneas + sub-envíos); la hidratación NO
re-emite eventos.

Las fechas se guardan en UTC sin zona (DATETIME) y se reconstruyen como UTC.
"""
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from mysql.connector import pooling

from ..domain.entities.order import Order, OrderProps
from ..domain.entities.sub_order import EstadoSubEnvio, SubEnvio
from ..domain.shared.entity import Identifier
from ..domain.value_objects.money import Money
from ..domain.value_objects.order_item import SKU, OrderItem
from ..domain.value_objects.order_status import OrderStatus

_STATUSES = {s.value: s for s in OrderStatus}
_SCHEMA = Path(__file__).with_name("schema.sql")

# Columnas añadidas después de la primera versión del esquema: se agregan
# a bases ya existentes (CREATE TABLE IF NOT EXISTS no altera tablas previas).
_COLUMNAS_NUEVAS = {
    "warehouse_id": "VARCHAR(30) NULL",
    "payment_confirmed_at": "DATETIME(6) NULL",
    "delivered_at": "DATETIME(6) NULL",
}


def _a_bd(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _de_bd(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def apply_schema(pool: pooling.MySQLConnectionPool) -> None:
    """Crea las tablas si no existen y migra columnas nuevas. Idempotente."""
    conn = pool.get_connection()
    try:
        cur = conn.cursor()
        for sentencia in _SCHEMA.read_text(encoding="utf-8").split(";"):
            if sentencia.strip():
                cur.execute(sentencia)
        cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders'")
        existentes = {fila[0] for fila in cur.fetchall()}
        for columna, ddl in _COLUMNAS_NUEVAS.items():
            if columna not in existentes:
                cur.execute(f"ALTER TABLE orders ADD COLUMN {columna} {ddl}")
        conn.commit()
        cur.close()
    finally:
        conn.close()


class MySQLOrderRepository:

    def __init__(self, pool: pooling.MySQLConnectionPool) -> None:
        self._pool = pool

    # ---------------- escritura ----------------
    async def save(self, order: Order) -> None:
        await asyncio.to_thread(self._save_sync, order)

    def _save_sync(self, order: Order) -> None:
        oid = str(order.id)
        conn = self._pool.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO orders
                    (order_id, customer_id, status, total_amount, created_at, updated_at,
                     is_split, payment_attempts, warehouse_id, payment_confirmed_at, delivered_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                     status=VALUES(status), total_amount=VALUES(total_amount),
                     updated_at=VALUES(updated_at), is_split=VALUES(is_split),
                     payment_attempts=VALUES(payment_attempts),
                     warehouse_id=VALUES(warehouse_id),
                     payment_confirmed_at=VALUES(payment_confirmed_at),
                     delivered_at=VALUES(delivered_at)""",
                (oid, order.customer_id.value, order.status.value, order.total_amount.amount,
                 _a_bd(order.created_at), _a_bd(order.updated_at), order.is_split,
                 order.payment_attempts, order.warehouse_id,
                 _a_bd(order.payment_confirmed_at), _a_bd(order.delivered_at)),
            )
            cur.execute("DELETE FROM order_items WHERE order_id = %s", (oid,))
            cur.executemany(
                "INSERT INTO order_items (order_id, sku, quantity, unit_price) "
                "VALUES (%s, %s, %s, %s)",
                [(oid, i.sku.value, i.quantity, i.unit_price.amount) for i in order.items],
            )
            cur.execute("DELETE FROM sub_orders WHERE order_id = %s", (oid,))
            if order.sub_orders:
                cur.executemany(
                    "INSERT INTO sub_orders (folio, order_id, warehouse_id, status, "
                    "guia_rastreo, items) VALUES (%s, %s, %s, %s, %s, %s)",
                    [(s.folio, oid, s.warehouse_id, s.status.value, s.guia_rastreo,
                      json.dumps([[sku, qty] for sku, qty in s.items]))
                     for s in order.sub_orders],
                )
            conn.commit()
            cur.close()
        finally:
            conn.close()

    # ---------------- lectura (hidratación) ----------------
    async def find_by_id(self, order_id: str) -> Optional[Order]:
        return await asyncio.to_thread(self._find_by_id_sync, order_id)

    def _find_by_id_sync(self, order_id: str) -> Optional[Order]:
        conn = self._pool.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
            row = cur.fetchone()
            if not row:
                return None

            cur.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
            items = [
                OrderItem(sku=SKU(r["sku"]), quantity=r["quantity"],
                          unit_price=Money(Decimal(str(r["unit_price"]))))
                for r in cur.fetchall()
            ]

            cur.execute("SELECT * FROM sub_orders WHERE order_id = %s ORDER BY folio", (order_id,))
            subs = []
            for r in cur.fetchall():
                crudo = r["items"]
                lineas = json.loads(crudo) if isinstance(crudo, (str, bytes)) else crudo
                subs.append(SubEnvio(
                    folio=r["folio"], warehouse_id=r["warehouse_id"],
                    items=[(sku, qty) for sku, qty in lineas],
                    status=EstadoSubEnvio(r["status"]), guia_rastreo=r["guia_rastreo"] or ""))

            props = OrderProps(
                customer_id=Identifier(row["customer_id"]),
                items=items,
                status=_STATUSES[row["status"]],
                total_amount=Money(Decimal(str(row["total_amount"]))),
                created_at=_de_bd(row["created_at"]),
                updated_at=_de_bd(row["updated_at"]),
                warehouse_id=row.get("warehouse_id"),
                is_split=bool(row["is_split"]),
                payment_attempts=int(row["payment_attempts"]),
                sub_orders=subs,
                payment_confirmed_at=_de_bd(row.get("payment_confirmed_at")),
                delivered_at=_de_bd(row.get("delivered_at")),
            )
            return Order.rehydrate(order_id=row["order_id"], props=props)
        finally:
            conn.close()
