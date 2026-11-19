import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse, HTMLResponse
from pathlib import Path

from src.api.delivery_controller import router as delivery_router
from src.api.order_controller import router
from src.composition_root import order_application_service

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Se construyen los servicios (y, con DB_HOST, el pool y el esquema) al arrancar:
    # falla rápido si la BD no responde y evita carreras en las primeras peticiones.
    order_application_service()
    yield


app = FastAPI(
    title="PetMarket Order & Logistics API",
    version="1.1.0",
    description="API DDD del PIA PetMarket (FIME UANL). RN-01 a RN-21.",
    lifespan=lifespan,
)

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

@app.get("/portal", include_in_schema=False)
async def portal() -> HTMLResponse:
    return HTMLResponse((TEMPLATES_DIR / "portal.html").read_text(encoding="utf-8"))

@app.get("/health", tags=["Infraestructura"])
async def health() -> dict:
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


app.include_router(router)
app.include_router(delivery_router)