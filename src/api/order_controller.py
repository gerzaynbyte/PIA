"""Capa API: adapters HTTP delgados (SRP). Los 6 endpoints de OpenAPI."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.application.order_application_service import OrderApplicationService
from src.composition_root import order_application_service

router = APIRouter(prefix="/v1")


# ---------- DTOs (espejo de docs/api/openapi.yaml) ----------
class ItemIn(BaseModel):
    sku: str
    quantity: int = Field(gt=0)   # RN-07 (máx. 50 por SKU) la aplica el dominio -> 400
    unitPrice: float = Field(gt=0)

class ReserveRequest(BaseModel):
    customerId: str
    items: list[ItemIn]

class ReserveResponse(BaseModel):
    reservationId: str
    expiresAt: datetime
    reservedItems: list[ItemIn]

class PaymentRequest(BaseModel):
    reservationId: str
    paymentToken: str
    amount: float

class PaymentResponse(BaseModel):
    orderId: str
    status: str
    transactionId: str
    attemptsRemaining: int

class CreateOrderRequest(BaseModel):
    customerId: str
    items: list[ItemIn]

class CreateOrderResponse(BaseModel):
    orderId: str
    status: str
    total: float

class CancelRequest(BaseModel):
    role: str   # CLIENTE | AGENTE_ATENCION | SUPERVISOR_ATENCION (alias: AGENTE, SUPERVISOR)
    reason: str = ""
    destinoProducto: str = ""

class SubOrderDTO(BaseModel):
    folio: str
    warehouseId: str
    status: str
    trackingNumber: str
    items: list[tuple]

class OrderDetailsDTO(BaseModel):
    orderId: str
    customerId: str
    status: str
    totalAmount: float
    isSplit: bool
    subOrders: list[SubOrderDTO]

class ReturnRequest(BaseModel):
    orderId: str
    sku: str
    requestedByRole: str
    condition: str
    evidencePhotoUrl: Optional[str] = None

class ReturnResponse(BaseModel):
    returnId: str
    status: str
    returnLabelUrl: str = ""


def svc() -> OrderApplicationService:
    return order_application_service()


# ---------- 1. POST /checkout/reserve (RN-04, RN-07) ----------
@router.post("/checkout/reserve", response_model=ReserveResponse,
            status_code=status.HTTP_201_CREATED, tags=["Carrito & Checkout"],
            responses={400: {"description": ">50 unidades por SKU o datos inválidos"},
                        409: {"description": "Stock insuficiente"}})
async def reserve_stock(body: ReserveRequest,
                        service: OrderApplicationService = Depends(svc)):
    r = await service.reserve_stock(body.customerId,
                                    [(i.sku, i.quantity, Decimal(str(i.unitPrice)))
                                    for i in body.items])
    if r.is_failure:
        code = 409 if "insuficiente" in (r.error or "").lower() else 400
        raise HTTPException(code, r.error)
    return r.value


# ---------- 2. POST /payments/process (RN-05, RN-08, RN-09) ----------
@router.post("/payments/process", response_model=PaymentResponse,
            tags=["Pagos & Transacciones"],
            responses={402: {"description": "Pago rechazado (incrementa reintento)"},
                        409: {"description": "Stock agotado en revalidación (RN-05)"}})
async def process_payment(body: PaymentRequest,
                        service: OrderApplicationService = Depends(svc)):
    r = await service.process_payment(body.reservationId,
                                    Decimal(str(body.amount)))
    if r.is_failure:
        msg = r.error or ""
        code = 409 if "RN-05" in msg else 402
        raise HTTPException(code, msg)
    return r.value


# ---------- 3. POST /orders (RN-01, RN-07) ----------
@router.post("/orders", response_model=CreateOrderResponse,
            status_code=status.HTTP_201_CREATED, tags=["Pedidos"])
async def create_order(body: CreateOrderRequest,
                    service: OrderApplicationService = Depends(svc)):
    r = await service.process_order_creation(
        body.customerId, [(i.sku, i.quantity, Decimal(str(i.unitPrice)))
                            for i in body.items])
    if r.is_failure:
        raise HTTPException(400, r.error)
    return r.value


# ---------- 4. GET /orders/{order_id} (US-19, US-14) ----------
@router.get("/orders/{order_id}", response_model=OrderDetailsDTO,
            tags=["Pedidos"], responses={404: {"description": "No encontrado"}})
async def get_order(order_id: str,
                    service: OrderApplicationService = Depends(svc)):
    r = await service.get_order_details(order_id)
    if r.is_failure:
        raise HTTPException(404, r.error)
    return r.value


# ---------- 5. POST /orders/{id}/cancel (RN-11, 12, 13) ----------
@router.post("/orders/{order_id}/cancel", tags=["Cancelaciones"],
                responses={200: {"description": "Cancelación procesada"},
                        403: {"description": "No autorizada (RN-11, RN-12, RN-13)"},
                        404: {"description": "No encontrado"},
                        409: {"description": "El estatus actual no permite cancelar"}})
async def cancel_order(order_id: str, body: CancelRequest,
                        service: OrderApplicationService = Depends(svc)):
    r = await service.cancel_order(order_id, body.role, body.reason,
                                    body.destinoProducto)
    if r.is_failure:
        msg = r.error or ""
        if "no encontrado" in msg:
            raise HTTPException(404, msg)
        if "Transición no permitida" in msg:
            raise HTTPException(409, msg)
        raise HTTPException(403, msg)
    return {"message": "Pedido cancelado correctamente", "data": r.value}


# ---------- 6. POST /returns (RN-20, RN-21) ----------
@router.post("/returns", response_model=ReturnResponse,
            status_code=status.HTTP_201_CREATED, tags=["Entregas & Devoluciones"],
            responses={400: {"description": "Pedido no entregado, SKU ajeno o falta evidencia"},
                        403: {"description": "Agente no puede aprobar excepción"},
                        404: {"description": "Pedido no encontrado"}})
async def create_return(body: ReturnRequest,
                        service: OrderApplicationService = Depends(svc)):
    r = await service.create_return(body.orderId, body.sku, body.requestedByRole,
                                    body.condition, body.evidencePhotoUrl)
    if r.is_failure:
        msg = r.error or ""
        code = 404 if "no encontrado" in msg else 403 if "escal" in msg else 400
        raise HTTPException(code, msg)
    return r.value