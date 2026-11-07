# Matriz de Trazabilidad Obligatoria — PetMarket (PIA)

> Rubricario: *"Un proyecto sin trazabilidad entre el análisis, la arquitectura,
> el código y las pruebas se considerará incompleto."* Esta matriz conecta
> BRD (RN-01–RN-21) → User Stories → componente de código → Specification →
> prueba automatizada → caso del paquete de datos (cuando aplica).
>
> Todos los nombres de prueba de esta matriz existen en `tests/` (se verificó
> automáticamente contra `pytest --collect-only`).

**Leyenda de estado.** **Completo** = implementado en `src/` y con prueba automatizada que lo fija;
**Parcial** = implementado, pero falta un flujo o una integración; **Diseñado** = definido en BRD/BPMN, sin implementación.
La columna *API* indica si la regla es alcanzable por un endpoint HTTP.

## 1.1 Reglas de negocio → Código → Pruebas

| RN | Descripción (BRD) | Componente (src/) | Specification / Patrón | Prueba automatizada | API | Estado |
|----|-------------------|--------------------|------------------------|--------------------|-----|--------|
| RN-01 | El carrito no crea pedido ni reserva stock; un pedido exige ≥ 1 producto | `Order.create` (guard de ítems) | Fábrica con guard | `test_create_rechaza_pedido_sin_items`, `test_alta_rechaza_sin_items_rn01_y_mas_de_50_rn07`, `test_rn07_y_rn01_devuelven_400` | POST /v1/orders | Completo |
| RN-02 | Cierre exitoso: 5 días hábiles sin reclamo | `state_machine.py` (ENTREGADO → FINALIZADO_EXITOSO), `shared/calendario.py` | State Machine | `test_rn02_entregado_puede_finalizarse_por_la_matriz`, `test_calendario_habil` | — | Parcial (falta el job que dispara el cierre a los 5 días) |
| RN-03 | Cierre por excepción | `Order.cancel`, `CANCELADO_*`, `OrderCancelledEvent` | State Machine + Domain Event | `test_pago_con_exceso_de_intentos_cancela_rn08`, `test_rn13_en_transito_solo_supervisor_y_queda_cancelado_excepcional` | POST …/cancel | Completo |
| RN-04 | Reserva de stock 15 min en checkout | `OrderApplicationService.reserve_stock`; `Inventory.reserve` | Agregado Inventory | `test_reserva_y_pago_exitoso_persisten_el_pedido`, `test_reserva_descuenta_disponibilidad_rn04`, `test_checkout_reserva_y_pago_sobreviven_entre_peticiones` | POST /v1/checkout/reserve | Parcial (la reserva es en memoria y no descuenta `Inventory`) |
| RN-05 | Revalidación antes del cobro | `process_payment` (valida vigencia de la reserva) | Guard en Application Service | `test_pago_con_reserva_expirada_409`, `test_reserva_insuficiente_falla` | POST /v1/payments/process | Parcial (no revalida existencias contra `Inventory`) |
| RN-06 | 3 opciones ante agotado | — (el 409 está declarado pero no es alcanzable) | — | — | — | Diseñado |
| RN-07 | Máx. 50 unidades **por SKU** por pedido | `OrderItem`, `LimiteUnidadesPorSkuSpecification` (suma líneas), `Order.create` | **Specification** | `test_create_rechaza_mas_de_50_unidades_por_sku_rn07`, `test_rn07_dos_lineas_del_mismo_sku_se_suman`, `test_limite_por_sku_suma_las_lineas` | POST /v1/orders → 400 | Completo |
| RN-08 | Máx. 3 intentos de pago / 15 min | `Order.confirm_payment` | Invariante de agregado | `test_tercer_intento_con_monto_incorrecto_cancela_el_pedido`, `test_rn08_tres_pagos_incorrectos_cancelan_y_persisten`, `test_pago_rn08_402_y_cancelacion_al_tercer_intento` | POST /v1/payments/process → 402 | Completo |
| RN-09 | Antifraude > $15,000 MXN | `RequiereRevisionAntifraudeSpecification` (la usa `Order.confirm_payment`) | **Specification** (Decimal) | `test_pedido_grande_va_a_antifraude_rn09`, `test_antifraude_usa_decimal_y_es_estrictamente_mayor`, `test_rn09_pago_grande_va_a_revision_antifraude` | POST /v1/payments/process | Completo |
| RN-10 | Cancelación por pago no confirmado y liberación de reserva | `Order.expirar_pago`, `process_payment` | State Machine | `test_rn10_reserva_expirada_cancela_el_pedido`, `test_solo_se_paga_un_pedido_pendiente_y_expira_si_no_se_paga`, `test_release_no_baja_de_cero_rn10` | POST /v1/payments/process → 409 | Parcial (cancela el pedido; la liberación de stock requiere integrar `Inventory`) |
| RN-11 | Autocancelación del cliente ≤ 2 h **desde la confirmación del pago** (Pago confirmado / En preparación) | `Order.cancel` + `validate_transition_with_rules` | State Machine (rol + tiempo) | `test_cliente_puede_autocancelar_dentro_de_2_horas`, `test_rechaza_autocancelacion_despues_de_2_horas_rn11`, `test_rn11_la_ventana_cuenta_desde_el_pago_no_desde_la_creacion`, `test_rn11_cliente_no_autocancela_en_estados_posteriores` | POST …/cancel | Completo |
| RN-12 | Cancelación asistida por Agente antes de EN_TRANSITO (motivo + destino) | `Order.cancel` | State Machine | `test_rn12_agente_cancela_pre_transito_con_motivo_y_destino`, `test_rn12_exige_destino_y_motivo` | POST …/cancel | Completo |
| RN-13 | Post-tránsito solo Supervisor (queda CANCELADO_EXCEPCIONAL) | `validate_transition_with_rules`, `Order.cancel` | State Machine (rol) | `test_supervisor_requerido_para_cancelar_en_transito_rn13`, `test_supervisor_si_puede_cancelar_en_transito_rn13`, `test_rn13_en_transito_solo_supervisor_y_queda_cancelado_excepcional`, `test_cancelacion_rn11_rn13_por_http` | POST …/cancel → 403 | Completo |
| RN-14 | Asignación por cercanía y, en empate, menor carga | `WarehouseAssignmentService`, `PreferenciaAlmacenSpecification` | **Specification** compuesta | `test_asignacion_por_cercania_gana_el_mas_cercano`, `test_desempate_por_menor_carga_cuando_distancia_empata`, `test_agente_de_almacen_no_puede_asignar_manualmente` | — (dominio) | Completo |
| RN-15 | Faltante físico resuelto por Supervisor de Almacén | `Inventory.report_discrepancy` | Agregado Inventory | `test_reporte_discrepancia_ajusta_fisico_rn15` | — | Parcial (falta validar el rol y la reasignación al otro almacén) |
| RN-16 | División en sub-envíos; padre entregado solo cuando todos llegan | `OrderSplittingService`, `SubEnvio`, `Order.dividir_en_sub_envios`; persistencia en `sub_orders` | Agregado + servicio de dominio | `test_divide_en_dos_almacenes_cuando_ninguno_cubre_100`, `test_un_almacen_que_cubre_todo_gana_aunque_el_cercano_cubra_solo_parte`, `test_padre_entregado_solo_cuando_todos_los_sub_envios_llegan`, `test_subenvios_y_almacen_se_persisten` | GET /v1/orders/{id} (lectura) | Completo |
| RN-17 | 2 intentos de entrega → retorno → contacto | `Delivery.registrar_intento`, `registrar_contacto_cliente` | Agregado | `test_segundo_intento_fallido_retorna_a_almacen_rn17`, `test_tercer_intento_es_prohibido_rn17` | — (dominio) | Completo |
| RN-18 | Reembolso automático a los 5 días hábiles sin respuesta | `Delivery.resolver_por_inactividad` | Agregado (idempotente) | `test_reembolso_automatico_tras_5_dias_habiles_rn18`, `test_reembolso_es_idempotente` | — (falta el job) | Completo (dominio) |
| RN-19 | Rechazo en sitio = devolución inmediata | `Order.registrar_rechazo_en_sitio` | State Machine | `test_rn19_rechazo_en_sitio_solo_en_transito` | — (dominio) | Completo |
| RN-20 | Devolución estándar ≤ 5 días hábiles desde la entrega, producto sin usar | `OrderApplicationService.create_return`, `Order.iniciar_devolucion` | State Machine | `test_rn20_devolucion_estandar_aprobada_mueve_el_pedido`, `test_devolucion_con_fecha_naive_de_bd`, `test_devoluciones_por_http` | POST /v1/returns | Completo |
| RN-21 | Excepción: evidencia fotográfica + solo Supervisor | `create_return` | Guard por rol y evidencia | `test_rn21_fuera_de_ventana_solo_supervisor_con_evidencia`, `test_devolucion_valida_pedido_sku_estado_y_rol` | POST /v1/returns → 403 | Completo |

**Resumen:** 15 completas, 5 parciales (RN-02, 04, 05, 10, 15) y 1 diseñada (RN-06).
Convención de plazos (RN-18 y RN-20): el día del evento cuenta como día 1; no se modelan festivos.

## 1.2 User Stories → RN → Evidencia

| US | RN | Escenario Gherkin verificado por | Resultado |
|----|----|----------------------------------|-----------|
| US-01 | RN-01 | `test_create_rechaza_pedido_sin_items` | ✅ |
| US-02 | RN-04 | `test_reserva_y_pago_exitoso_persisten_el_pedido` | ⚠️ parcial |
| US-03 | RN-05 | `test_pago_con_reserva_expirada_409` | ⚠️ parcial |
| US-04 | RN-06 | — | ❌ diseñado |
| US-05 | RN-07 | `test_rn07_dos_lineas_del_mismo_sku_se_suman` | ✅ |
| US-06 | RN-08 | `test_tercer_intento_con_monto_incorrecto_cancela_el_pedido` | ✅ |
| US-07 | RN-09 | `test_pedido_grande_va_a_antifraude_rn09` | ✅ |
| US-08 | RN-10 | `test_rn10_reserva_expirada_cancela_el_pedido` | ⚠️ parcial |
| US-09 | RN-11 | `test_rn11_la_ventana_cuenta_desde_el_pago_no_desde_la_creacion` | ✅ |
| US-10 | RN-12 | `test_rn12_agente_cancela_pre_transito_con_motivo_y_destino` | ✅ |
| US-11 | RN-13 | `test_rn13_en_transito_solo_supervisor_y_queda_cancelado_excepcional` | ✅ |
| US-12 | RN-14 | `test_asignacion_por_cercania_gana_el_mas_cercano` | ✅ |
| US-13 | RN-15 | `test_reporte_discrepancia_ajusta_fisico_rn15` | ⚠️ parcial |
| US-14 | RN-16 | `test_padre_entregado_solo_cuando_todos_los_sub_envios_llegan` | ✅ |
| US-15 | RN-17/18 | `test_segundo_intento_fallido_retorna_a_almacen_rn17`, `test_reembolso_automatico_tras_5_dias_habiles_rn18` | ✅ (dominio) |
| US-16 | RN-19 | `test_rn19_rechazo_en_sitio_solo_en_transito` | ✅ (dominio) |
| US-17 | RN-20 | `test_rn20_devolucion_estandar_aprobada_mueve_el_pedido` | ✅ |
| US-18 | RN-21 | `test_rn21_fuera_de_ventana_solo_supervisor_con_evidencia` | ✅ |
| US-19 | — | `test_crear_y_consultar_pedido` (GET /v1/orders/{id}) | ✅ |
| US-20/21 | — | Reportes gerenciales (CQRS desnormalizado, ver ADR-03) | ❌ pendiente |

## 1.3 Modelo de pruebas del paquete (LEEME.txt) ↔ Dominio PetMarket

> **Obligatorio documentar** (LEEME.txt): el paquete es un modelo de pruebas
> propuesto, no un requerimiento original. No sustituimos RN-01–RN-21;
> adaptamos fixtures y oráculos.

| Elemento del paquete | Equivalente en dominio | Justificación |
|----------------------|-----------------------|---------------|
| `CREADO` | `PENDIENTE_PAGO` | Punto de entrada del ciclo |
| `PAGADO` | `PAGO_CONFIRMADO` | Pago confirmado, sin excepciones |
| `SURTIDO` | `EN_PREPARACION` / `EMPACADO` | Preparación en almacén |
| `ENTREGADO` | `ENTREGADO` | Igual en ambos modelos |
| `CANCELADO` | `CANCELADO` | Igual en ambos modelos |
| `puede_procesarse` (activo AND líneas AND autorización) | Precondiciones de `Order.create` (RN-01) + guard de detalle | Análogo a "detalle no vacío"; actor/autorización son del dataset |
| `beneficio_referencia` (preferente AND ≥1500 AND NOT promoción) | **Sin equivalente en RN-01–21** — regla exclusiva del paquete | Specification demostrativa (`AND` + `NOT`) |
| `repetir_aprobacion` / `saltar_estado` | `TransicionInvalidaError` en `operacion_state_machine.py` | Ambos modelos exigen transiciones legales únicamente |

## 1.4 Casos del paquete de datos → Componente → Oráculo esperado

Ejecutable: `python -m tools.ejecutar_casos data/ resultados/`. Los oráculos de esta sección
los verifica `tests/unit/test_casos_petmarket.py::test_runner_reproduce_los_oraculos_documentados`.

**a) `casos_prueba.csv` (PET-T001–T060, PET-B001–B060)**

| Grupo | Regla evaluada | Componente | Oráculo (`resultados_casos.csv`) |
|-------|----------------|------------|-----------------------------------|
| PET-Txxx (60) | `puede_procesarse` | `specifications_operaciones.py::puede_procesarse` | **45 EXITOSOS / 15 FALLIDOS.** Fallan O001, O002, O003, O008, O013, O016, O024, O032, O039, O040, O041, O042, O043, O048, O056 (actor inactivo, `autorizado=0` o detalle vacío: O013 no tiene líneas en `detalle_operaciones.csv`) |
| PET-Bxxx (60) | `beneficio_referencia` | `specifications_operaciones.py::beneficio_referencia` | **10 verdaderos:** O003, O008, O023, O028, O033, O038, O043, O048, O053, O058 (actor preferente, total ≥ $1,500 y sin promoción). La regla del paquete no exige actor activo (p. ej. O003 es verdadero aunque su actor está inactivo); O018 es falso por promoción activa |

**b) `transiciones_prueba.csv` (PET-S001–S020)**

| Casos | Acción | Resultado esperado |
|-------|--------|--------------------|
| S001, S002, S003, S008, S013, S016 | varias | **Precondición falla** (`puede_procesarse=False`): se registra y no transiciona |
| S005, S010, S015, S020 | `aprobar` | `CREADO→PAGADO`, evento `OperacionTransicionada:PAGADO` |
| S006, S011 | `completar` | Llegan a `ENTREGADO` con 3 eventos |
| S007, S012, S017 | `cancelar` | `CREADO→CANCELADO`, evento registrado |
| S004, S009, S014, S019 | `saltar_estado` | **`TransicionInvalidaError`** (CREADO→ENTREGADO no existe en la matriz) |
| S018 | `repetir_aprobacion` | 1er `PAGADO` válido; el 2º lanza `TransicionInvalidaError` |

Totales: 9 transicionan, 6 no cumplen precondición, 4 transiciones inválidas y 1 parcial (S018).

## 1.5 Hallazgos documentados del dataset

- `PET-P011` tiene `habilitado=0` y aparece en **6** operaciones (O005, O015, O020, O035, O040, O055).
  La regla 1 del paquete **no** incluye habilitación del recurso, por lo que NO se considera en
  `puede_procesarse`. Si el docente la exige, añadir `RecursoHabilitadoSpecification` (extra, demuestra `OR`).
- `PET-O013` y `PET-O039` no tienen líneas de detalle → oráculos intencionales de línea vacía (RN-01).
- Totales calculados con `Decimal` (nunca `float`), según punto 3 del LEEME.
