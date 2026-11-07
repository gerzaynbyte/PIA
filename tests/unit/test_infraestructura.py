"""Repositorio MySQL (con un pool simulado), raíz de composición y carga de CSV."""
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.composition_root import order_application_service, reset_composition
from src.domain.entities.order import Order
from src.domain.services.order_splitting_service import AsignacionAlmacenLineas
from src.domain.shared.entity import Identifier
from src.domain.value_objects.money import Money
from src.domain.value_objects.order_item import SKU, OrderItem
from src.domain.value_objects.order_status import OrderStatus
from src.infrastructure.csv_petmarket_repository import (cargar_actores, cargar_catalogo,
                                                         cargar_detalle, cargar_operaciones)
from src.infrastructure.in_memory_order_repository import InMemoryOrderRepository
from src.infrastructure.mysql_order_repository import MySQLOrderRepository, apply_schema

DATOS = Path(__file__).parents[2] / "data"


# ---------- doble de prueba del pool MySQL (emula las sentencias que usa el repositorio) ----------
class FakeDB:
    def __init__(self, columnas=("order_id",)):
        self.orders, self.items, self.subs, self.sentencias = {}, [], [], []
        self.columnas = list(columnas)
        self.commits = 0


class FakeCursor:
    def __init__(self, db, dictionary=False):
        self.db, self.dictionary, self._rows = db, dictionary, []

    def execute(self, sql, params=()):
        db = self.db
        db.sentencias.append(" ".join(sql.split()))
        s = db.sentencias[-1]
        if s.startswith("INSERT INTO orders"):
            cols = ["order_id", "customer_id", "status", "total_amount", "created_at",
                    "updated_at", "is_split", "payment_attempts", "warehouse_id",
                    "payment_confirmed_at", "delivered_at"]
            db.orders[params[0]] = dict(zip(cols, params))
        elif s.startswith("DELETE FROM order_items"):
            db.items = [i for i in db.items if i["order_id"] != params[0]]
        elif s.startswith("DELETE FROM sub_orders"):
            db.subs = [i for i in db.subs if i["order_id"] != params[0]]
        elif s.startswith("SELECT * FROM orders"):
            self._rows = [db.orders[params[0]]] if params[0] in db.orders else []
        elif s.startswith("SELECT * FROM order_items"):
            self._rows = [i for i in db.items if i["order_id"] == params[0]]
        elif s.startswith("SELECT * FROM sub_orders"):
            self._rows = [i for i in db.subs if i["order_id"] == params[0]]
        elif "information_schema" in s:
            self._rows = [(c,) for c in db.columnas]

    def executemany(self, sql, seq):
        s = " ".join(sql.split())
        self.db.sentencias.append(s)
        for p in seq:
            if "INTO order_items" in s:
                self.db.items.append(dict(zip(["order_id", "sku", "quantity", "unit_price"], p)))
            else:
                self.db.subs.append(dict(zip(["folio", "order_id", "warehouse_id", "status",
                                              "guia_rastreo", "items"], p)))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self, dictionary=False):
        return FakeCursor(self.db, dictionary)

    def commit(self):
        self.db.commits += 1

    def close(self):
        pass


class FakePool:
    def __init__(self, db=None, **_kw):
        self.db = db or FakeDB()

    def get_connection(self):
        return FakeConn(self.db)


def _pedido_con_subenvios():
    o = Order.create(Identifier("cliente-1"),
                     [OrderItem(SKU("ALIM-DOG-01"), 4, Money(Decimal("520.00"))),
                      OrderItem(SKU("JUG-CAT-07"), 1, Money(Decimal("662.00")))]).value
    o.confirm_payment(o.total_amount)
    o.asignar_almacen("ALMACEN_NORTE")
    o.dividir_en_sub_envios([AsignacionAlmacenLineas("ALMACEN_NORTE", [("ALIM-DOG-01", 2)]),
                             AsignacionAlmacenLineas("ALMACEN_SUR", [("ALIM-DOG-01", 2), ("JUG-CAT-07", 1)])])
    o.sub_orders[0].asignar_guia("GUIA-1")
    return o


async def test_roundtrip_completo_con_subenvios_fechas_y_decimales():
    pool = FakePool()
    repo = MySQLOrderRepository(pool)
    o = _pedido_con_subenvios()
    await repo.save(o)

    # las fechas se guardan en UTC sin zona
    assert pool.db.orders[str(o.id)]["created_at"].tzinfo is None
    h = await repo.find_by_id(str(o.id))
    assert h.status == OrderStatus.PAGO_CONFIRMADO and h.total_amount.amount == Decimal("2742.00")
    assert h.warehouse_id == "ALMACEN_NORTE" and h.is_split and len(h.sub_orders) == 2
    assert h.sub_orders[0].guia_rastreo == "GUIA-1"
    assert h.sub_orders[1].items == [("ALIM-DOG-01", 2), ("JUG-CAT-07", 1)]
    assert h.created_at.tzinfo is not None and h.payment_confirmed_at is not None
    assert h.domain_events == []                       # hidratar no emite eventos
    assert not h.cancel("CLIENTE", "x").is_failure     # y el pedido hidratado es operable


async def test_guardar_dos_veces_no_duplica_lineas_ni_subenvios():
    pool = FakePool()
    repo = MySQLOrderRepository(pool)
    o = _pedido_con_subenvios()
    await repo.save(o)
    o._props.payment_attempts = 2
    await repo.save(o)
    assert len(pool.db.items) == 2 and len(pool.db.subs) == 2
    assert (await repo.find_by_id(str(o.id))).payment_attempts == 2
    assert any("ON DUPLICATE KEY UPDATE" in s for s in pool.db.sentencias)


async def test_find_inexistente_y_pedido_sin_subenvios():
    pool = FakePool()
    repo = MySQLOrderRepository(pool)
    assert await repo.find_by_id("nada") is None
    o = Order.create(Identifier("c"), [OrderItem(SKU("AAA"), 1, Money(Decimal("1")))]).value
    await repo.save(o)
    assert not any("INTO sub_orders" in s for s in pool.db.sentencias)
    pool.db.subs.append({"folio": "F", "order_id": str(o.id), "warehouse_id": "ALMACEN_SUR",
                         "status": "EN_PREPARACION", "guia_rastreo": None,
                         "items": [["AAA", 1]]})            # JSON ya decodificado por el driver
    assert (await repo.find_by_id(str(o.id))).sub_orders[0].items == [("AAA", 1)]


def test_apply_schema_crea_tablas_y_migra_columnas_faltantes():
    pool = FakePool(FakeDB(columnas=("order_id", "customer_id")))
    apply_schema(pool)
    s = pool.db.sentencias
    assert sum(x.startswith("CREATE TABLE") for x in s) == 3
    alters = [x for x in s if x.startswith("ALTER TABLE")]
    assert len(alters) == 3 and any("warehouse_id" in a for a in alters)


def test_apply_schema_es_idempotente_si_ya_existen_las_columnas():
    pool = FakePool(FakeDB(columnas=("warehouse_id", "payment_confirmed_at", "delivered_at")))
    apply_schema(pool)
    assert not any(x.startswith("ALTER TABLE") for x in pool.db.sentencias)


# ---------- raíz de composición ----------
def test_composicion_in_memory_devuelve_siempre_la_misma_instancia(monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    reset_composition()
    a, b = order_application_service(), order_application_service()
    assert a is b and isinstance(a._order_repo, InMemoryOrderRepository)
    reset_composition()
    assert order_application_service() is not a
    reset_composition()


def test_composicion_mysql_crea_pool_una_vez_y_aplica_esquema(monkeypatch):
    from mysql.connector import pooling
    creados = []

    def fake_pool(**kw):
        creados.append(kw)
        return FakePool()
    monkeypatch.setattr(pooling, "MySQLConnectionPool", fake_pool)
    monkeypatch.setenv("DB_HOST", "mysql_db")
    monkeypatch.setenv("DB_NAME", "petmarket_db")
    reset_composition()
    s1, s2 = order_application_service(), order_application_service()
    assert s1 is s2 and len(creados) == 1 and creados[0]["host"] == "mysql_db"
    assert isinstance(s1._order_repo, MySQLOrderRepository)
    assert any(x.startswith("CREATE TABLE") for x in s1._order_repo._pool.db.sentencias)
    reset_composition()


# ---------- CSV ----------
def test_carga_de_csv_con_bom_y_decimales():
    assert len(cargar_actores(DATOS / "actores.csv")) == 40
    cat = cargar_catalogo(DATOS / "catalogo.csv")
    assert len(cat) == 20 and cat["PET-P001"].precio_mxn == Decimal("520.00")
    assert cat["PET-P011"].habilitado is False
    assert len(cargar_operaciones(DATOS / "operaciones.csv")) == 60
    det = cargar_detalle(DATOS / "detalle_operaciones.csv")
    assert "PET-O013" not in det and len(det["PET-O001"]) == 2
