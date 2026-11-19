"""Raíz de composición (DIP): elige el adaptador de persistencia según el
entorno. Con DB_HOST -> MySQL (producción/Docker); sin él -> InMemory (dev).

Todos los servicios se crean UNA sola vez por proceso y comparten los mismos
repositorios: las reservas de checkout, las entregas y el pool de conexiones
deben sobrevivir entre peticiones.
"""
import os
from functools import lru_cache

from src.application.delivery_application_service import DeliveryApplicationService
from src.application.order_application_service import OrderApplicationService


@lru_cache(maxsize=1)
def _servicios() -> tuple:
    if os.getenv("DB_HOST"):
        from mysql.connector import pooling

        from src.infrastructure.mysql_inventory_repository import MySQLInventoryRepository
        from src.infrastructure.mysql_order_repository import (MySQLOrderRepository, apply_schema)
        pool = pooling.MySQLConnectionPool(
            pool_name="petmarket", pool_size=4,
            host=os.environ["DB_HOST"],
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "petmarket_db"))
        apply_schema(pool)

        inventario = MySQLInventoryRepository(pool)
        inventario.sembrar_si_vacia()   # stock persistente desde data/catalogo.csv
        order_repo = MySQLOrderRepository(pool)

        from src.infrastructure.in_memory_delivery_repository import InMemoryDeliveryRepository
        return (OrderApplicationService(order_repo, inventario),
                DeliveryApplicationService(order_repo, InMemoryDeliveryRepository()))

    from src.infrastructure.in_memory_delivery_repository import InMemoryDeliveryRepository
    from src.infrastructure.in_memory_inventory_repository import InMemoryInventoryRepository
    from src.infrastructure.in_memory_order_repository import InMemoryOrderRepository
    order_repo = InMemoryOrderRepository()
    return (OrderApplicationService(order_repo, _inventario_dev()),
            DeliveryApplicationService(order_repo, InMemoryDeliveryRepository()))


def order_application_service() -> OrderApplicationService:
    return _servicios()[0]

def delivery_application_service() -> DeliveryApplicationService:
    return _servicios()[1]

def _inventario_dev():
    """Siembra existencias desde el catálogo del curso (modo dev/tests sin BD)."""
    from pathlib import Path

    from src.infrastructure.in_memory_inventory_repository import InMemoryInventoryRepository
    try:
        from src.infrastructure.csv_petmarket_repository import cargar_catalogo
        ruta = Path(__file__).resolve().parents[1] / "data" / "catalogo.csv"
        stock = {sku: r.capacidad_o_stock for sku, r in cargar_catalogo(ruta).items()}
    except OSError:
        stock = {}
    return InMemoryInventoryRepository(stock)

def reset_composition() -> None:
    """Descarta los servicios cacheados (pruebas)."""
    _servicios.cache_clear()