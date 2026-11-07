# src/infrastructure/csv_petmarket_repository.py
"""Carga del paquete de datos 01_Alumno (CSV UTF-8 con BOM, importes Decimal)."""
import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple

@dataclass(frozen=True)
class Actor:
    actor_id: str
    nombre: str
    es_preferente: bool
    activo: bool
    ciudad: str

@dataclass(frozen=True)
class Recurso:
    recurso_id: str
    descripcion: str
    precio_mxn: Decimal
    capacidad_o_stock: int
    habilitado: bool

@dataclass(frozen=True)
class LineaDetalle:
    operacion_id: str
    recurso_id: str
    cantidad: int

@dataclass(frozen=True)
class Operacion:
    operacion_id: str
    actor_id: str
    estado_inicial: str
    fecha_solicitud: date
    promocion_activa: bool
    autorizado: bool
    referencia: str

def _flag(v: str) -> bool:
    return v.strip() == "1"

def cargar_actores(ruta: Path) -> Dict[str, Actor]:
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return {r["actor_id"]: Actor(r["actor_id"], r["nombre"], _flag(r["es_preferente"]),
                                    _flag(r["activo"]), r["ciudad"])
                for r in csv.DictReader(f)}

def cargar_catalogo(ruta: Path) -> Dict[str, Recurso]:
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return {r["recurso_id"]: Recurso(r["recurso_id"], r["descripcion"], 
                                        Decimal(r["precio_mxn"]), int(r["capacidad_o_stock"]),
                                        _flag(r["habilitado"]))
                for r in csv.DictReader(f)}

def cargar_operaciones(ruta: Path) -> Dict[str, Operacion]:
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return {r["operacion_id"]: Operacion(r["operacion_id"], r["actor_id"], r["estado_inicial"],
                                            date.fromisoformat(r["fecha_solicitud"]),
                                            _flag(r["promocion_activa"]), _flag(r["autorizado"]),
                                            r["referencia"])
                for r in csv.DictReader(f)}

def cargar_detalle(ruta: Path) -> Dict[str, Tuple[LineaDetalle, ...]]:
    detalle: Dict[str, List[LineaDetalle]] = {}
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            detalle.setdefault(r["operacion_id"], []).append(
                LineaDetalle(r["operacion_id"], r["recurso_id"], int(r["cantidad"])))
    return {k: tuple(v) for k, v in detalle.items()}