"""El contrato publicado (docs/api/openapi.yaml) debe coincidir con la API real."""
from pathlib import Path

import yaml

from tools.exportar_openapi import esquema

RUTA = Path(__file__).parents[2] / "docs" / "api" / "openapi.yaml"


def test_openapi_yaml_esta_sincronizado_con_la_api():
    publicado = yaml.safe_load(RUTA.read_text(encoding="utf-8"))
    assert publicado == esquema(), "Regenere con: python -m tools.exportar_openapi"


def test_openapi_expone_los_seis_endpoints_de_negocio():
    rutas = set(esquema()["paths"])
    assert {"/v1/checkout/reserve", "/v1/payments/process", "/v1/orders",
            "/v1/orders/{order_id}", "/v1/orders/{order_id}/cancel", "/v1/returns"} <= rutas
