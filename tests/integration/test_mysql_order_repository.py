"""Integración real contra MySQL del servicio docker compose 'tests'.
Marca: integration. Requiere DB_HOST apuntando al contenedor mysql_db."""
import os
from decimal import Decimal

import pytest
from mysql.connector import pooling

from src.domain.entities.order import Order
from src.domain.services.order_splitting_service import AsignacionAlmacenLineas
from src.domain.shared.entity import Identifier
from src.domain.value_objects.money import Money
from src.domain.value_objects.order_item import SKU, OrderItem
from src.domain.value_objects.order_status import OrderStatus
from src.infrastructure.mysql_order_repository import MySQLOrderRepository, apply_schema

pytestmark = pytest.mark.integration


def _pool():
    return pooling.MySQLConnectionPool(
        pool_name="test", pool_size=2,
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ["DB_PASSWORD"],
        database=os.environ.get("DB_NAME", "petmarket_db_test"),
    )


@pytest.fixture(scope="module")
def repo():
    pool = _pool()
    apply_schema(pool)          # el mismo esquema que usa la API (sin DDL duplicado)
    apply_schema(pool)          # idempotente
    return MySQLOrderRepository(pool)


@pytest.fixture(autouse=True)
def limpiar_tablas(repo):
    yield
    conn = repo._pool.get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM orders")     # FK ON DELETE CASCADE borra líneas y sub-envíos
    conn.commit()
    cur.close()
    conn.close()


def _pedido_aprobado():
    r = Order.create(
        Identifier("3f6c1c1e-2222-4aaa-8bbb-2ccc333d4444"),
        [OrderItem(SKU("ALIM-DOG-01"), 2, Money(Decimal("520.00"))),
         OrderItem(SKU("JUG-CAT-07"), 1, Money(Decimal("662.00")))],
    )
    order = r.value
    order.confirm_payment(order.total_amount)   # $1,702 -> PAGO_CONFIRMADO
    return order


async def test_roundtrip_conserva_estado_items_y_decimales(repo):
    order = _pedido_aprobado()
    await repo.save(order)

    hidratado = await repo.find_by_id(str(order.id))

    assert hidratado is not None
    assert str(hidratado.id) == str(order.id)
    assert hidratado.status == OrderStatus.PAGO_CONFIRMADO
    assert hidratado.total_amount.amount == Decimal("1702.00")  # Decimal, no float
    assert hidratado.payment_attempts == 1
    assert hidratado.payment_confirmed_at is not None
    assert hidratado.created_at.tzinfo is not None             # UTC reconstruido
    assert len(hidratado.items) == 2
    skus = {i.sku.value: i for i in hidratado.items}
    assert skus["ALIM-DOG-01"].quantity == 2
    assert skus["JUG-CAT-07"].unit_price.amount == Decimal("662.00")


async def test_hidratacion_no_emite_eventos_de_dominio(repo):
    """Crítico: reconstruir desde BD no debe replicar OrderCreatedEvent."""
    order = _pedido_aprobado()
    await repo.save(order)
    hidratado = await repo.find_by_id(str(order.id))
    assert hidratado.domain_events == []


async def test_pedido_hidratado_puede_cancelarse_y_guardarse(repo):
    """Regresión: Order.rehydrate no inicializaba _domain_events (AttributeError al cancelar)."""
    order = _pedido_aprobado()
    await repo.save(order)
    hidratado = await repo.find_by_id(str(order.id))
    assert not hidratado.cancel("CLIENTE", "me equivoqué").is_failure
    await repo.save(hidratado)
    assert (await repo.find_by_id(str(order.id))).status == OrderStatus.CANCELADO


async def test_find_by_id_inexistente_devuelve_none(repo):
    assert await repo.find_by_id("00000000-0000-0000-0000-000000000000") is None


async def test_guardar_dos_veces_actualiza_en_lugar_de_duplicar(repo):
    """UPSERT + DELETE/INSERT de líneas: no duplica (RN-07/BD)."""
    order = _pedido_aprobado()
    await repo.save(order)
    order._props.payment_attempts = 2
    await repo.save(order)

    hidratado = await repo.find_by_id(str(order.id))
    assert hidratado.payment_attempts == 2
    assert len(hidratado.items) == 2  # no 4

    conn = repo._pool.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM order_items WHERE order_id=%s", (str(order.id),))
    assert cur.fetchone()[0] == 2
    cur.close()
    conn.close()


async def test_subenvios_y_almacen_se_persisten(repo):
    """RN-16: el pedido dividido conserva sus sub-envíos tras guardar y leer."""
    order = _pedido_aprobado()
    order.asignar_almacen("ALMACEN_NORTE")
    order.dividir_en_sub_envios([
        AsignacionAlmacenLineas("ALMACEN_NORTE", [("ALIM-DOG-01", 2)]),
        AsignacionAlmacenLineas("ALMACEN_SUR", [("JUG-CAT-07", 1)])])
    order.sub_orders[0].asignar_guia("GUIA-777")
    await repo.save(order)

    h = await repo.find_by_id(str(order.id))
    assert h.is_split and h.warehouse_id == "ALMACEN_NORTE"
    assert [s.folio for s in h.sub_orders] == [s.folio for s in order.sub_orders]
    assert h.sub_orders[0].guia_rastreo == "GUIA-777"
    assert h.sub_orders[1].items == [("JUG-CAT-07", 1)]
