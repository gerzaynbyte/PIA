# Registro de correcciones (revisión técnica del PIA)

Resultado verificado: **131 pruebas (125 unitarias + 6 de integración contra MySQL 8) en verde,
cobertura 97.8 % sobre todo `src/`** (antes: el paquete no importaba y no se podía recolectar ninguna prueba).

## Bloqueantes
| # | Defecto | Corrección |
|---|---------|------------|
| 1 | `src/__init__.py` contenía un comando `touch` pegado como texto (SyntaxError) y faltaban los demás `__init__.py` | Archivos vacíos creados en todos los paquetes (también hace que la cobertura mida `api/`, `application/` e `infrastructure/`) |
| 2 | `Dockerfile` dentro de `src/domain/entities/`; no copiaba `pyproject.toml` | Movido a la raíz; copia `pyproject.toml` y `docs/api/` |
| 3 | `docs/api/openapi.yaml` inexistente (lo exige el CI) | Generado con `python -m tools.exportar_openapi` + prueba de sincronía |
| 4 | `test_casos_petmarket.py` importaba símbolos inexistentes | `construir_contexto` expuesto en el runner; prueba reescrita con oráculos verificables |

## Defectos funcionales
| # | Defecto | Corrección |
|---|---------|------------|
| 5 | `OrderApplicationService` definida dos veces (la 2ª borraba la 1ª); `get_order_details` no existía → 500 en POST /orders y GET /orders/{id} | Una sola clase; `process_order_creation` y `get_order_details` implementados |
| 6 | El servicio y el repositorio se recreaban en cada petición (reserva → pago imposible; un pool MySQL por petición) | `composition_root` con `lru_cache`; el servicio se construye en el `lifespan` |
| 7 | `Order.rehydrate` no inicializaba `_domain_events` (cancelar un pedido leído de la BD fallaba) | Inicializado |
| 8 | `str(order.id)` devolvía `Identifier(value='…')`: `orderId` de la API y llaves MySQL inválidas (`VARCHAR(36)`) | `Identifier.__str__` devuelve el valor |
| 9 | RN-07 se validaba por línea | Se suma por SKU (`LimiteUnidadesPorSkuSpecification`) y las líneas repetidas se consolidan |
| 10 | Se podía cancelar un pedido ENTREGADO o ya cancelado | `Order.cancel` delega en la máquina de estados |
| 11 | RN-11 contaba desde la creación y sin revisar el estatus | Cuenta desde la confirmación del pago y solo en PAGO_CONFIRMADO / EN_PREPARACION |
| 12 | RN-08: el pedido no se cancelaba al 3.er pago fallido y los intentos nunca persistían entre peticiones | Cancela al 3.er fallo; los intentos viven en la reserva |
| 13 | RN-13 dejaba CANCELADO; la máquina de estados exige CANCELADO_EXCEPCIONAL | Alineado |
| 14 | `Money(float)` provocaba `Decimal + float` | `Money` convierte a `Decimal` |
| 15 | `create_return`: `TypeError` con fechas de MySQL; días naturales desde la creación | Fechas UTC; días hábiles desde la entrega; exige pedido ENTREGADO y SKU del pedido |
| 16 | Persistencia MySQL sin sub-envíos ni almacén; esquema nunca aplicado | Tabla `sub_orders`; `apply_schema` idempotente al arrancar (migra columnas nuevas) |
| 17 | `RN-16`: el servicio dividía aunque un solo almacén cubriera el 100 % | Si un almacén cubre todo, no hay división |
| 18 | Mensaje «Faltantes globales: {}» engañoso en el disparador de RN-16 | Reporta los SKU sin cobertura en un solo almacén |
| 19 | Roles inconsistentes (`AGENTE`, `AGENTE_ATENCION`, …) | `Rol` + `normalizar_rol` (acepta alias heredados) |
| 20 | `or_`/`not_` quedaron fuera de la clase `Specification`; el antifraude no usaba la Specification | Movidos a la clase; `Order` usa ambas Specifications |
| 21 | POST con >50 unidades devolvía 422 (el DTO lo cortaba) en vez de 400 RN-07 | El dominio aplica RN-07 → 400 con mensaje |

## Infraestructura y documentación
`.gitignore`/`.dockerignore`, `NODE_ENV`→`APP_ENV`, `pyyaml` en requirements, CI con `security-defined`
omitido a propósito (JWT pendiente), README con el comando de pruebas correcto, ADR-02 y UML alineados
al código, residuos `[cite: N]` eliminados del BRD y `trazabilidad.md` reescrita (52 pruebas citadas, todas existen).

## Pendiente (documentado, no corregido)
Autenticación JWT · integrar `Inventory` en reserva/revalidación (RN-04/05/06/10) · rol de Supervisor de
Almacén en RN-15 · jobs de cierre (RN-02) y reembolso automático (RN-18) · reservas compartidas entre réplicas.
