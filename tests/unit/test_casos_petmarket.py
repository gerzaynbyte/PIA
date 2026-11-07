"""Oráculos del paquete de datos del curso (data/*.csv) contra el runner."""
import csv
from collections import Counter
from pathlib import Path

import pytest

from src.domain.specifications_operaciones import beneficio_referencia, puede_procesarse
from src.infrastructure.csv_petmarket_repository import (cargar_actores, cargar_catalogo,
                                                         cargar_detalle, cargar_operaciones)
from tools.ejecutar_casos import construir_contexto, main

DATOS = Path(__file__).parents[2] / "data"


@pytest.fixture(scope="module")
def paquete():
    return (cargar_operaciones(DATOS / "operaciones.csv"), cargar_actores(DATOS / "actores.csv"),
            cargar_detalle(DATOS / "detalle_operaciones.csv"), cargar_catalogo(DATOS / "catalogo.csv"))


def _ctx(op_id, paquete):
    ops, actores, detalle, catalogo = paquete
    return construir_contexto(op_id, ops, actores, detalle, catalogo)[0]


@pytest.mark.parametrize("op_id,esperado", [
    ("PET-O001", False),  # actor PET-C021 inactivo
    ("PET-O002", False),  # actor PET-C028 inactivo
    ("PET-O008", False),  # autorizado=0
    ("PET-O013", False),  # sin detalle (no aparece en detalle_operaciones.csv)
    ("PET-O033", True),
    ("PET-O060", True),
])
def test_puede_procesarse(op_id, esperado, paquete):
    assert puede_procesarse().is_satisfied_by(_ctx(op_id, paquete)) is esperado


@pytest.mark.parametrize("op_id,esperado", [
    ("PET-O018", False),  # VIP y total 7,476, PERO promocion_activa=1 -> NOT falla
    ("PET-O033", True),   # VIP, sin promoción, total >= 1,500
])
def test_beneficio_referencia(op_id, esperado, paquete):
    assert beneficio_referencia().is_satisfied_by(_ctx(op_id, paquete)) is esperado


def test_runner_reproduce_los_oraculos_documentados(tmp_path):
    main(DATOS, tmp_path)
    casos = list(csv.DictReader(open(tmp_path / "resultados_casos.csv", encoding="utf-8")))
    assert len(casos) == 120
    por_grupo = Counter((c["caso_id"][:5], c["resultado"]) for c in casos)
    assert por_grupo[("PET-T", "EXITOSO")] == 45 and por_grupo[("PET-T", "FALLIDO")] == 15
    assert por_grupo[("PET-B", "EXITOSO")] == 10 and por_grupo[("PET-B", "FALLIDO")] == 50
    fallidos = {c["operacion_id"] for c in casos
                if c["caso_id"].startswith("PET-T") and c["resultado"] == "FALLIDO"}
    assert {"PET-O013", "PET-O039", "PET-O001"} <= fallidos and "PET-O028" not in fallidos

    trans = {t["caso_id"]: t for t in
             csv.DictReader(open(tmp_path / "resultados_transiciones.csv", encoding="utf-8"))}
    assert len(trans) == 20
    assert trans["PET-S005"]["estado_final"] == "PAGADO" and not trans["PET-S005"]["excepcion"]
    assert trans["PET-S006"]["estado_final"] == "ENTREGADO"
    assert "Transición inválida" in trans["PET-S004"]["excepcion"]      # saltar_estado
    assert trans["PET-S018"]["estado_final"] == "PAGADO" and trans["PET-S018"]["excepcion"]
    assert "Precondiciones" in trans["PET-S001"]["excepcion"]
