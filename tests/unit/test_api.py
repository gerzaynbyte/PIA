"""Contrato HTTP de los endpoints (FastAPI TestClient, repositorio InMemory)."""
import pytest
from fastapi.testclient import TestClient

from src.composition_root import order_application_service, reset_composition
from src.domain.value_objects.order_status import OrderStatus
from src.main import app

BODY = {"customerId": "cliente-1",
        "items": [{"sku": "ALIM-DOG-01", "quantity": 2, "unitPrice": 100.0}]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    reset_composition()
    with TestClient(app) as c:        # ejecuta el lifespan
        yield c
    reset_composition()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_crear_y_consultar_pedido(client):
    r = client.post("/v1/orders", json=BODY)
    assert r.status_code == 201 and r.json()["status"] == "PENDIENTE_PAGO" and r.json()["total"] == 200.0
    assert len(r.json()["orderId"]) == 36                 # UUID, no "Identifier(value=...)"
    g = client.get(f"/v1/orders/{r.json()['orderId']}")
    assert g.status_code == 200 and g.json()["customerId"] == "cliente-1"
    assert client.get("/v1/orders/no-existe").status_code == 404


def test_rn07_y_rn01_devuelven_400(client):
    grande = {"customerId": "c", "items": [{"sku": "ALIM-DOG-01", "quantity": 51, "unitPrice": 10}]}
    r = client.post("/v1/orders", json=grande)
    assert r.status_code == 400 and "RN-07" in r.json()["detail"]
    assert client.post("/v1/orders", json={"customerId": "c", "items": []}).status_code == 400
    assert client.post("/v1/orders", json={"customerId": "c", "items": [
        {"sku": "ALIM-DOG-01", "quantity": 0, "unitPrice": 10}]}).status_code == 422


def test_checkout_reserva_y_pago_sobreviven_entre_peticiones(client):
    """Regresión: antes cada petición creaba un servicio nuevo y perdía la reserva."""
    r = client.post("/v1/checkout/reserve", json=BODY)
    assert r.status_code == 201 and "reservationId" in r.json()
    pago = {"reservationId": r.json()["reservationId"], "paymentToken": "tok", "amount": 200.0}
    p = client.post("/v1/payments/process", json=pago)
    assert p.status_code == 200 and p.json()["status"] == "PAGO_CONFIRMADO"
    assert client.get(f"/v1/orders/{p.json()['orderId']}").json()["status"] == "PAGO_CONFIRMADO"


def test_reserva_rechaza_datos_invalidos(client):
    grande = {"customerId": "c", "items": [{"sku": "ALIM-DOG-01", "quantity": 99, "unitPrice": 10}]}
    assert client.post("/v1/checkout/reserve", json=grande).status_code == 400


def test_pago_rn08_402_y_cancelacion_al_tercer_intento(client):
    rid = client.post("/v1/checkout/reserve", json=BODY).json()["reservationId"]
    pago = {"reservationId": rid, "paymentToken": "t", "amount": 1.0}
    for _ in range(2):
        r = client.post("/v1/payments/process", json=pago)
        assert r.status_code == 402 and "Intentos restantes" in r.json()["detail"]
    ultimo = client.post("/v1/payments/process", json=pago)
    assert ultimo.status_code == 402 and "RN-08" in ultimo.json()["detail"]
    assert client.post("/v1/payments/process", json=pago).status_code == 402   # reserva ya cerrada


def test_pago_con_reserva_expirada_409(client):
    rid = client.post("/v1/checkout/reserve", json=BODY).json()["reservationId"]
    from datetime import datetime, timedelta, timezone
    order_application_service()._reservas[rid]["expires"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    r = client.post("/v1/payments/process",
                    json={"reservationId": rid, "paymentToken": "t", "amount": 200.0})
    assert r.status_code == 409 and "RN-05" in r.json()["detail"]


def test_cancelacion_200_403_404_409(client):
    oid = client.post("/v1/orders", json=BODY).json()["orderId"]
    assert client.post(f"/v1/orders/{oid}/cancel", json={"role": "hacker", "reason": "x"}).status_code == 403
    assert client.post("/v1/orders/zzz/cancel", json={"role": "CLIENTE"}).status_code == 404
    ok = client.post(f"/v1/orders/{oid}/cancel", json={"role": "CLIENTE", "reason": "error"})
    assert ok.status_code == 200 and ok.json()["data"]["status"] == "CANCELADO"
    assert client.post(f"/v1/orders/{oid}/cancel", json={"role": "CLIENTE"}).status_code == 409


def test_cancelacion_rn11_rn13_por_http(client):
    oid = client.post("/v1/orders", json=BODY).json()["orderId"]
    svc = order_application_service()
    import asyncio
    o = asyncio.run(svc._order_repo.find_by_id(oid))
    o._set_status(OrderStatus.EN_TRANSITO)
    r = client.post(f"/v1/orders/{oid}/cancel", json={"role": "AGENTE", "reason": "x",
                                                      "destinoProducto": "INVENTARIO"})
    assert r.status_code == 403 and "RN-13" in r.json()["detail"]
    assert client.post(f"/v1/orders/{oid}/cancel",
                       json={"role": "SUPERVISOR", "reason": "excepción"}).status_code == 200


def test_devoluciones_por_http(client):
    oid = client.post("/v1/orders", json=BODY).json()["orderId"]
    body = {"orderId": oid, "sku": "ALIM-DOG-01", "requestedByRole": "CLIENTE",
            "condition": "NUEVO_SIN_USAR"}
    assert client.post("/v1/returns", json=body).status_code == 400          # no entregado
    assert client.post("/v1/returns", json={**body, "orderId": "zzz"}).status_code == 404
    import asyncio
    o = asyncio.run(order_application_service()._order_repo.find_by_id(oid))
    o._set_status(OrderStatus.EN_TRANSITO)
    o.avanzar(OrderStatus.ENTREGADO)
    ok = client.post("/v1/returns", json=body)
    assert ok.status_code == 201 and ok.json()["status"] == "APROBADA"
