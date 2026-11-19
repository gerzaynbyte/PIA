"""RN-04/05/10 a nivel servicio: la reserva descuenta inventario real y se
libera en todos los caminos de salida (pago, expiración, 3er fallo, faltante)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.application.order_application_service import OrderApplicationService
from src.infrastructure.in_memory_inventory_repository import InMemoryInventoryRepository
from src.infrastructure.in_memory_order_repository import InMemoryOrderRepository

ITEMS = [("ALIM-DOG-01", 3, Decimal("100.00"))]


@pytest.fixture
def inventario():
    return InMemoryInventoryRepository({"ALIM-DOG-01": 10})


@pytest.fixture
def svc(inventario):
    return OrderApplicationService(InMemoryOrderRepository(), inventario)


async def test_reserva_descuenta_disponibilidad_y_pago_consuma_fisico_rn04(svc, inventario):
    r = (await svc.reserve_stock("c", ITEMS)).value
    assert (await inventario.disponibles_por_sku(["ALIM-DOG-01"]))["ALIM-DOG-01"] == 7
    pago = await svc.process_payment(r["reservationId"], Decimal("300.00"))
    assert not pago.is_failure
    inv = inventario
    assert inv._fisico["ALIM-DOG-01"] == 7 and inv._reservado["ALIM-DOG-01"] == 0


async def test_reserva_insuficiente_falla_sin_dejar_residuo(svc, inventario):
    r = await svc.reserve_stock("c", [("ALIM-DOG-01", 11, Decimal("1"))])
    assert "insuficiente" in r.error            # el controller lo mapea a 409
    assert (await inventario.disponibles_por_sku(["ALIM-DOG-01"]))["ALIM-DOG-01"] == 10


async def test_rn05_faltante_fisico_entre_reserva_y_pago(svc, inventario):
    """Escenario US-03: existía stock al reservar; RN-15 detecta faltante antes del cobro."""
    rid = (await svc.reserve_stock("c", ITEMS)).value["reservationId"]
    inventario.report_discrepancia("ALIM-DOG-01", 1)     # física cae por debajo de lo reservado
    r = await svc.process_payment(rid, Decimal("300.00"))
    assert "RN-05" in r.error
    assert (await inventario.disponibles_por_sku(["ALIM-DOG-01"]))["ALIM-DOG-01"] == 1
    assert rid not in svc._reservas            # la reserva se cerró sin fuga


async def test_rn10_tres_pagos_fallidos_liberan_reserva(svc, inventario):
    rid = (await svc.reserve_stock("c", ITEMS)).value["reservationId"]
    for _ in range(3):
        assert (await svc.process_payment(rid, Decimal("1"))).is_failure
    assert (await inventario.disponibles_por_sku(["ALIM-DOG-01"]))["ALIM-DOG-01"] == 10


async def test_rn10_expiracion_liberar_reserva(svc, inventario):
    rid = (await svc.reserve_stock("c", ITEMS)).value["reservationId"]
    svc._reservas[rid]["expires"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    r = await svc.process_payment(rid, Decimal("300.00"))
    assert "RN-10" in r.error
    assert (await inventario.disponibles_por_sku(["ALIM-DOG-01"]))["ALIM-DOG-01"] == 10


async def test_pago_exitoso_tras_fallo_no_duplica_reservas(svc, inventario):
    rid = (await svc.reserve_stock("c", ITEMS)).value["reservationId"]
    assert (await svc.process_payment(rid, Decimal("5"))).is_failure
    pago = await svc.process_payment(rid, Decimal("300.00"))
    assert not pago.is_failure
    assert inventario._fisico["ALIM-DOG-01"] == 7   # un solo consumo, no dos

async def test_consumar_falla_si_la_fisica_desaparece_entre_medio(svc, inventario):
    """Caso patológico: merma física simultánea al cobro (requeriría compensación
    transaccional — límite declarado del alcance, ver ADR-02)."""
    from unittest.mock import patch

    rid = (await svc.reserve_stock("c", ITEMS)).value["reservationId"]
    # Hacer que revalidar pase pero consumar vea física insuficiente:
    async def revalidar_ok(_):
        from src.domain.shared.result import Result
        return Result.ok()
    async def consumar_fail(_):
        from src.domain.shared.result import Result
        return Result.fail("RN-05: existencias físicas del SKU ALIM-DOG-01 desaparecieron.")
    with patch.object(inventario, "revalidar", revalidar_ok), \
        patch.object(inventario, "consumar", consumar_fail):
        r = await svc.process_payment(rid, Decimal("300.00"))
    assert "desaparecieron" in r.error