"""RN-14 — Asignación automática de almacén de origen (US-12).
Escenarios espejo de los criterios de aceptación Gherkin de US-12."""
import pytest

from src.domain.services.warehouse_assignment_service import (
    WarehouseAssignmentService,
)
from src.domain.specifications_warehouse import CandidatoAlmacen
from src.domain.value_objects.warehouse import WarehouseId

ITEMS = [("ALIM-DOG-01", 2)]


def _candidato(wid, distancia, carga, stock=None):
    return CandidatoAlmacen(
        warehouse_id=wid,
        distancia_km=distancia,
        carga_pendiente=carga,
        stock_por_sku=stock or {"ALIM-DOG-01": 10},
    )


def test_asignacion_por_cercania_gana_el_mas_cercano():
    """Gherkin US-12: dos almacenes con stock suficiente, uno más cercano."""
    norte = _candidato(WarehouseId.ALMACEN_NORTE, distancia=12.0, carga=5)
    sur = _candidato(WarehouseId.ALMACEN_SUR, distancia=3.5, carga=40)

    resultado = WarehouseAssignmentService().asignar(ITEMS, [norte, sur])

    assert not resultado.is_failure
    assert resultado.value.warehouse_id == WarehouseId.ALMACEN_SUR


def test_desempate_por_menor_carga_cuando_distancia_empata():
    """Gherkin US-12: misma distancia -> menor carga de pedidos pendientes."""
    norte = _candidato(WarehouseId.ALMACEN_NORTE, distancia=10.0, carga=25)
    sur = _candidato(WarehouseId.ALMACEN_SUR, distancia=10.0, carga=4)

    resultado = WarehouseAssignmentService().asignar(ITEMS, [norte, sur])

    assert not resultado.is_failure
    assert resultado.value.warehouse_id == WarehouseId.ALMACEN_SUR


def test_la_carga_no_compensa_distancia_mayor():
    """RN-14 estricto: la carga SOLO desempata; jamás sobreescribe cercanía."""
    cercano_cargado = _candidato(WarehouseId.ALMACEN_NORTE, distancia=2.0, carga=99)
    lejano_libre = _candidato(WarehouseId.ALMACEN_SUR, distancia=80.0, carga=0)

    resultado = WarehouseAssignmentService().asignar(ITEMS, [cercano_cargado, lejano_libre])

    assert resultado.value.warehouse_id == WarehouseId.ALMACEN_NORTE


def test_almacen_cercano_sin_stock_es_descartado():
    """El filtro StockSuficiente corre ANTES de la preferencia."""
    cercano_sin_stock = _candidato(
        WarehouseId.ALMACEN_NORTE, distancia=1.0, carga=0, stock={"ALIM-DOG-01": 1}
    )
    lejano_con_stock = _candidato(
        WarehouseId.ALMACEN_SUR, distancia=50.0, carga=30, stock={"ALIM-DOG-01": 8}
    )

    resultado = WarehouseAssignmentService().asignar(ITEMS, [cercano_sin_stock, lejano_con_stock])

    assert resultado.value.warehouse_id == WarehouseId.ALMACEN_SUR


def test_nadie_cubre_100_por_ciento_dispara_division_rn16():
    """Disparador de RN-16: se informa el faltante para dividir el pedido."""
    norte = _candidato(WarehouseId.ALMACEN_NORTE, distancia=5.0, carga=1,
                       stock={"ALIM-DOG-01": 1})
    sur = _candidato(WarehouseId.ALMACEN_SUR, distancia=9.0, carga=1,
                     stock={"ALIM-DOG-01": 1})

    resultado = WarehouseAssignmentService().asignar(
        [("ALIM-DOG-01", 2)], [norte, sur]
    )

    assert resultado.is_failure
    assert "RN-16" in resultado.error
    assert "ALIM-DOG-01" in resultado.error  # el faltante global viaja en el error


def test_agente_de_almacen_no_puede_asignar_manualmente():
    """RN-14: solo el sistema asigna; el Agente de Almacén está bloqueado."""
    norte = _candidato(WarehouseId.ALMACEN_NORTE, distancia=3.0, carga=2)

    resultado = WarehouseAssignmentService().asignar(
        ITEMS, [norte], rol_solicitante="AGENTE_ALMACEN"
    )

    assert resultado.is_failure
    assert "RN-14" in resultado.error


def test_pedido_vacio_es_rechazado():
    resultado = WarehouseAssignmentService().asignar([], [])
    assert resultado.is_failure