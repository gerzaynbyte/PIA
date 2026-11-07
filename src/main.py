import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from src.api.order_controller import router
from src.composition_root import order_application_service

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Se construye el servicio (y, con DB_HOST, el pool y el esquema) al arrancar:
    # falla rápido si la BD no responde y evita carreras en las primeras peticiones.
    order_application_service()
    yield


app = FastAPI(
    title="PetMarket Order & Logistics API",
    version="1.0.0",
    description="API DDD del PIA PetMarket (FIME UANL). RN-01 a RN-21.",
    lifespan=lifespan,
)


@app.get("/health", tags=["Infraestructura"])
async def health() -> dict:
    return {"status": "ok"}


app.include_router(router)