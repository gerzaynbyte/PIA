import pytest

from src.domain.entities.inventory import Inventory
from src.domain.shared.result import Result
from src.domain.value_objects.order_item import SKU


def _inv(stock=10):
    r = Inventory.create(SKU("ALIM-DOG-01"), "ALMACEN_NORTE", stock)
    return r.value


def test_reserva_descuenta_disponibilidad_rn04():
    inv = _inv(10)
    assert inv.reserve(3).is_failure is False
    assert inv.available_stock == 7
    assert inv.reserved_stock == 3


def test_reserva_insuficiente_falla():
    inv = _inv(5)
    assert inv.reserve(6).is_failure


def test_release_no_baja_de_cero_rn10():
    inv = _inv(10)
    inv.release_reservation(5)
    inv.release_reservation(5)
    inv.release_reservation(5)  # no negativa
    assert inv.reserved_stock == 0


def test_reporte_discrepancia_ajusta_fisico_rn15():
    inv = _inv(10)
    inv.report_discrepancy(6)
    assert inv.physical_stock == 6