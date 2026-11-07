"""Exporta el contrato OpenAPI de la API a docs/api/openapi.yaml.
Uso: python -m tools.exportar_openapi [ruta_salida]"""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.main import app  # noqa: E402

DESTINO = Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.yaml"


def esquema() -> dict:
    """Esquema normalizado a tipos JSON (comparable con el YAML exportado)."""
    return json.loads(json.dumps(app.openapi()))


def main(destino: Path = DESTINO) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(yaml.safe_dump(esquema(), sort_keys=False, allow_unicode=True),
                       encoding="utf-8")
    print(f"OpenAPI exportado a {destino}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO)
