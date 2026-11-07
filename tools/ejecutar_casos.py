"""Runner del paquete de datos. Uso: python -m tools.ejecutar_casos data/ resultados/"""
import csv
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.operacion_state_machine import (EstadoOperacion,
                                                TransicionInvalidaError,
                                                transicionar)
from src.domain.specifications_operaciones import (ContextoOperacion,
                                                    beneficio_referencia,
                                                    puede_procesarse)
from src.infrastructure.csv_petmarket_repository import (cargar_actores,
                                                        cargar_catalogo,
                                                        cargar_detalle,
                                                        cargar_operaciones)

# Secuencia de estados que implica cada acción sugerida del paquete
ACCIONES_SECUENCIA = {
    "aprobar":            [EstadoOperacion.PAGADO],
    "completar":          [EstadoOperacion.PAGADO, EstadoOperacion.SURTIDO,
                            EstadoOperacion.ENTREGADO],
    "cancelar":           [EstadoOperacion.CANCELADO],
    "repetir_aprobacion": [EstadoOperacion.PAGADO, EstadoOperacion.PAGADO],
    "saltar_estado":      [EstadoOperacion.ENTREGADO],
}


def construir_contexto(op_id: str, operaciones, actores, detalle, catalogo) -> tuple:
    """Arma el ContextoOperacion que evalúan las Specifications.
    Devuelve (contexto, operacion, actor)."""
    op = operaciones[op_id]
    lineas = detalle.get(op_id, ())
    total = sum((catalogo[l.recurso_id].precio_mxn * l.cantidad for l in lineas),
                Decimal("0.00"))
    actor = actores[op.actor_id]
    ctx = ContextoOperacion(
        actor_activo=actor.activo, actor_preferente=actor.es_preferente,
        autorizado=op.autorizado, total=total,
        promocion_activa=op.promocion_activa, num_lineas=len(lineas))
    return ctx, op, actor


def main(dir_datos: Path, dir_salida: Path) -> None:
    actores = cargar_actores(dir_datos / "actores.csv")
    catalogo = cargar_catalogo(dir_datos / "catalogo.csv")
    operaciones = cargar_operaciones(dir_datos / "operaciones.csv")
    detalle = cargar_detalle(dir_datos / "detalle_operaciones.csv")
    dir_salida.mkdir(parents=True, exist_ok=True)

    def contexto(op_id: str) -> ContextoOperacion:
        return construir_contexto(op_id, operaciones, actores, detalle, catalogo)[0]

    # ---- casos_prueba.csv ----
    with open(dir_salida / "resultados_casos.csv", "w", encoding="utf-8",
                newline="") as f:
        w = csv.writer(f)
        w.writerow(["caso_id", "operacion_id", "regla", "resultado", "evidencia"])
        with open(dir_datos / "casos_prueba.csv", encoding="utf-8-sig",
                    newline="") as src:
            for caso in csv.DictReader(src):
                ctx = contexto(caso["operacion_id"])
                spec = (puede_procesarse()
                        if caso["tipo_prueba"] == "validar_operacion"
                        else beneficio_referencia())
                w.writerow([caso["caso_id"], caso["operacion_id"],
                            caso["regla_a_verificar"],
                            "EXITOSO" if spec.is_satisfied_by(ctx) else "FALLIDO",
                            f"total={ctx.total} autorizado={ctx.autorizado} "
                            f"activo={ctx.actor_activo} lineas={ctx.num_lineas}"])

    # ---- transiciones_prueba.csv ----
    with open(dir_salida / "resultados_transiciones.csv", "w", encoding="utf-8",
                newline="") as f:
        w = csv.writer(f)
        w.writerow(["caso_id", "operacion_id", "accion", "estado_final",
                    "evento", "excepcion"])
        with open(dir_datos / "transiciones_prueba.csv", encoding="utf-8-sig",
                    newline="") as src:
            for caso in csv.DictReader(src):
                ctx = contexto(caso["operacion_id"])
                estado = EstadoOperacion(caso["estado_inicial"])
                eventos, exc = [], ""
                if not puede_procesarse().is_satisfied_by(ctx):
                    exc = "Precondiciones no satisfechas (puede_procesarse=False)"
                else:
                    try:
                        for objetivo in ACCIONES_SECUENCIA[caso["accion_sugerida"]]:
                            estado = transicionar(estado, objetivo)
                            eventos.append(f"OperacionTransicionada:{estado.value}")
                    except TransicionInvalidaError as e:
                        exc = str(e)
                w.writerow([caso["caso_id"], caso["operacion_id"],
                            caso["accion_sugerida"], estado.value,
                            ";".join(eventos), exc])


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "data"),
        Path(sys.argv[2] if len(sys.argv) > 2 else "resultados"))