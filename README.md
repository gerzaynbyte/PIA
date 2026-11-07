# PetMarket — PIA Componentes de Lógica de Negocio

Sistema transaccional (pedidos, inventario, logística multialmacén) bajo
arquitectura limpia y DDD. Reglas de negocio RN-01 a RN-21 materializadas
como código verificable.

- **Repositorio:** `<URL del repositorio>` · **Despliegue:** `https://<app>.up.railway.app`
- **Swagger en producción:** `https://<app>.up.railway.app/docs`

## Requisitos
Python 3.11+, Docker y Docker Compose v2.

## Instalación local
    cp .env.example .env    # editar con credenciales reales
    pip install -r requirements.txt

## Ejecución
    uvicorn src.main:app --reload            # API en http://localhost:8000/docs (sin DB_HOST: repositorio en memoria)
    docker compose up -d --build             # MySQL + API en http://localhost:3000/docs

Con `DB_HOST` definido la API usa MySQL y crea/migra las tablas al arrancar
(`src/infrastructure/schema.sql`, idempotente). Sin `DB_HOST` usa un repositorio en memoria.

## Pruebas y cobertura (gate 80 %)
    pytest -m "not integration" --cov=src --cov-fail-under=80   # sin BD (lo que ejecuta el CI)
    docker compose run --rm tests                                # suite completa con MySQL + runner de CSV

> `docker compose run` activa solo el perfil del servicio `tests`; no uses `--profile` después de `run`.
> Alternativa equivalente: `docker compose --profile tests run --rm tests`.

## Paquete de datos del curso
    python -m tools.ejecutar_casos data/ resultados/

## Contrato OpenAPI
El contrato vive en `docs/api/openapi.yaml` y se genera desde la API:

    python -m tools.exportar_openapi

Una prueba (`test_openapi_contract.py`) falla si el archivo se desincroniza del código.

## Estructura
docs/ (BRD, arquitectura, OpenAPI) · src/ (domain, application,
infrastructure, api) · tests/ (unit + integration) · tools/ · data/

## Limitaciones conocidas
- Sin autenticación: el rol llega en el cuerpo de la petición (JWT es trabajo futuro).
- Las reservas de checkout (RN-04) viven en memoria del proceso: válido para una sola instancia.
- El inventario (`Inventory`), `Delivery` y los servicios de almacén están modelados y probados
  en el dominio, pero aún no están expuestos por la API.
