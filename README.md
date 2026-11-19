# PetMarket — PIA Componentes de Lógica de Negocio

Sistema transaccional de e-commerce (pedidos, inventario, logística
multialmacén) bajo arquitectura limpia y DDD. Las reglas de negocio
RN-01 a RN-21 del BRD están materializadas como código verificable.

- **Repositorio:** https://github.com/gerzaynbyte/PIA.git
- **Despliegue:** _pendiente de sustituir con la URL real de Railway_
- **Swagger en producción:** `<URL>/docs` · **Portal de demostración:** `<URL>/portal`
- **Versión de la API:** 1.1.0

## Arquitectura

Capas de dominio puro sin dependencias externas, orquestadas por una
raíz de composición (DIP) que selecciona adaptadores según el entorno:

| Capa | Contenido |
|---|---|
| `src/domain` | Agregados (`Order`, `Delivery`, `Inventory`), value objects, especificaciones, máquinas de estado (RN-11…RN-21) y servicios de dominio (RN-14/RN-16 división y asignación de almacén) |
| `src/application` | `OrderApplicationService` (checkout, pago, cancelación, devolución) y `DeliveryApplicationService` (ciclo de entrega RN-17/RN-18 con puente hacia el pedido) |
| `src/infrastructure` | Repositorios InMemory, MySQL (`orders`, `order_items`, `sub_orders`, `inventory`) y carga del paquete de datos CSV |
| `src/api` | Controllers FastAPI + `http_errors.py`, mapeo centralizado mensaje-de-dominio → código HTTP con contrato testado |

## Requisitos

Python 3.11+, Docker y Docker Compose v2.

## Instalación local

    cp .env.example .env    # editar con credenciales reales
    pip install -r requirements.txt

> Nunca subas el `.env` real: está excluido por `.gitignore` y `.dockerignore`.
> `JWT_SECRET` se declara para la futura capa de autenticación (hoy ningún
> módulo lo consume).

## Ejecución

    uvicorn src.main:app --reload            # API en http://localhost:8000/docs
                                             # (sin DB_HOST: repositorios en memoria)
    docker compose up -d --build             # MySQL + API en http://localhost:3000/docs

Con `DB_HOST` definido la API usa **MySQL para pedidos e inventario** y
crea/migra las tablas al arrancar (`src/infrastructure/schema.sql`,
idempotente); el stock se siembra automáticamente desde
`data/catalogo.csv` si la tabla `inventory` está vacía. Sin `DB_HOST`
usa repositorios en memoria (modo desarrollo/tests).

Endpoints principales (contrato completo en `/docs`):

- `POST /v1/checkout/reserve` — reserva de stock (RN-04, RN-07)
- `POST /v1/payments/process` — pago con 3 intentos (RN-05, RN-08, RN-09)
- `POST /v1/orders` · `GET /v1/orders/{id}` — alta y consulta
- `POST /v1/orders/{id}/cancel` — cancelación por rol y ventana (RN-11…RN-13)
- `POST /v1/returns` — devoluciones (RN-20, RN-21)
- `POST /v1/deliveries/intentos|contacto|respuesta|reembolso-inactividad`
  — ciclo de entrega (RN-17, RN-18)

## Pruebas y cobertura (gate 80 %)

    pytest -m "not integration" --cov=src --cov-fail-under=80   # sin BD (lo que ejecuta el CI)
    docker compose run --rm tests                                # suite completa con MySQL + runner de CSV

> `docker compose run` activa solo el perfil del servicio `tests`; no uses
> `--profile` después de `run`. Alternativa equivalente:
> `docker compose --profile tests run --rm tests`.

Estado actual: **150 tests unitarios en verde, cobertura ≈ 90 %**.
Los tests de integración (`tests/integration/`) requieren MySQL levantado.

## Paquete de datos del curso

    python -m tools.ejecutar_casos data/ resultados/

## Contrato OpenAPI

El contrato vive en `docs/api/openapi.yaml` y se genera desde la API:

    python -m tools.exportar_openapi

Una prueba (`test_openapi_contract.py`) falla si el archivo se desincroniza
del código. Al agregar o modificar endpoints, regenerar y commitear.

## Estructura

    docs/           BRD, arquitectura, OpenAPI
    src/            domain · application · infrastructure · api
    tests/          unit/ · integration/
    tools/          wait_for_db · exportar_openapi · ejecutar_casos
    data/           paquete de datos del curso (catálogo y oráculos)
    templates/      portal de demostración (GET /portal)

## Limitaciones conocidas

- **Sin autenticación**: el rol llega en el cuerpo de la petición; el
  `JWT_SECRET` ya está definido en la configuración para la capa JWT futura.
- **Reservas de checkout (RN-04) en memoria del proceso**: válido para una
  sola instancia. El inventario ya es persistente y compartido en MySQL,
  pero la ventana de reserva requeriría un almacén compartido (Redis o
  tabla `reservations`) para múltiples réplicas.
- **`Delivery` integrado vía `POST /v1/deliveries/*`** (RN-17/RN-18) con
  repositorio en memoria de proceso; su persistencia en MySQL y el job
  programado de reembolso por inactividad (RN-18) son la siguiente iteración.
- **Servicios de almacén (RN-14/RN-16)**: modelados y probados en el dominio
  (`WarehouseAssignmentService`, `OrderSplittingService`), aún no cableados
  al flujo de la aplicación ni expuestos por la API.
- **Eventos de dominio** (`OrderCreatedEvent`, `OrderCancelledEvent`) se
  emiten pero no se persisten ni despachan (sin patrón Outbox todavía).