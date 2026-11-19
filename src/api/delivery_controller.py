"""Adapters HTTP del ciclo de entrega (RN-17, RN-18). La paquetería reporta
intentos; Atención al Cliente contacta y gestiona la respuesta del cliente."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.application.delivery_application_service import DeliveryApplicationService
from src.composition_root import delivery_application_service

router = APIRouter(prefix="/v1/deliveries", tags=["Entregas & Devoluciones"])


class IntentoRequest(BaseModel):
    orderId: str
    folio: str                     # folio del sub-envío; para pedidos indivisos, el orderId
    exitoso: bool
    motivoFalla: str = ""          # obligatorio si exitoso=False (lo valida el dominio)
    trackingNumber: str = ""       # solo pedidos indivisos sin guía registrada

class FolioRequest(BaseModel):
    orderId: str
    folio: str

class AccionResponse(BaseModel):
    folio: str
    deliveryStatus: str
    orderStatus: str


def svc() -> DeliveryApplicationService:
    return delivery_application_service()


def _fallar(r):
    raise HTTPException(estatus_http(r.error, REGLAS_ENTREGA, DEFECTO_ENTREGA), r.error)


@router.post("/intentos", response_model=AccionResponse,
            responses={404: {"description": "Pedido o sub-envío no encontrado"},
                        409: {"description": "Estado actual no permite el intento "
                                            "(p. ej. tercer intento, RN-17)"}})
async def registrar_intento(body: IntentoRequest,
                            service: DeliveryApplicationService = Depends(svc)):
    r = await service.reportar_intento(body.orderId, body.folio, body.exitoso,
                                        body.motivoFalla, body.trackingNumber)
    if r.is_failure:
        _fallar(r)
    return r.value


@router.post("/contacto", response_model=AccionResponse,
            responses={404: {"description": "Entrega no encontrada"},
                        409: {"description": "Solo procede tras el retorno a almacén (RN-17)"}})
async def contactar_cliente(body: FolioRequest,
                            service: DeliveryApplicationService = Depends(svc)):
    r = await service.contactar_cliente(body.orderId, body.folio)
    if r.is_failure:
        _fallar(r)
    return r.value


@router.post("/respuesta", response_model=AccionResponse,
            responses={404: {"description": "Entrega no encontrada"},
                        409: {"description": "Respuesta tardía: RN-18 exige reembolso, "
                                            "no reprogramación"}})
async def registrar_respuesta(body: FolioRequest,
                            service: DeliveryApplicationService = Depends(svc)):
    r = await service.reprogramar(body.orderId, body.folio)
    if r.is_failure:
        _fallar(r)
    return r.value


@router.post("/reembolso-inactividad", response_model=AccionResponse,
            responses={404: {"description": "Entrega no encontrada"},
                        409: {"description": "Plazo de 5 días hábiles aún vigente (RN-18)"}})
async def reembolso_por_inactividad(body: FolioRequest,
                                    fecha_actual: Optional[str] = None,
                                    service: DeliveryApplicationService = Depends(svc)):
    from datetime import datetime, timezone

    fecha = None
    if fecha_actual:
        try:
            fecha = datetime.fromisoformat(fecha_actual.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "fecha_actual debe ser ISO-8601")
    r = await service.resolver_por_inactividad(body.orderId, body.folio, fecha)
    if r.is_failure:
        _fallar(r)
    return r.value