"""Raíz de composición (DIP): elige el adaptador de persistencia según el
entorno. Con DB_HOST -> MySQL (producción/Docker); sin él -> InMemory (dev).

El servicio se crea UNA sola vez por proceso (lru_cache): las reservas de
checkout y el pool de conexiones deben sobrevivir entre peticiones.
"""
import os
from functools import lru_cache

from src.application.order_application_service import OrderApplicationService


@lru_cache(maxsize=1)
def order_application_service() -> OrderApplicationService:
    if os.getenv("DB_HOST"):
        from mysql.connector import pooling

        from src.infrastructure.mysql_order_repository import (MySQLOrderRepository,
                                                               apply_schema)
        pool = pooling.MySQLConnectionPool(
            pool_name="petmarket", pool_size=4,
            host=os.environ["DB_HOST"],
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "petmarket_db"))
        apply_schema(pool)
        return OrderApplicationService(MySQLOrderRepository(pool))
    from src.infrastructure.in_memory_order_repository import InMemoryOrderRepository
    return OrderApplicationService(InMemoryOrderRepository())


def reset_composition() -> None:
    """Descarta el servicio cacheado (pruebas)."""
    order_application_service.cache_clear()
