# User Stories & Criterios de Aceptación (Gherkin) - PetMarket

Las User Stories traducen las reglas de negocio fijadas en unidades de trabajo accionables.

## Matriz de Trazabilidad

| ID | Rol | Historia (resumen) | Regla de negocio / referencia |
|---|---|---|---|
| US-01 | Cliente | El carrito no reserva inventario ni genera pedido | RN-01 |
| US-02 | Cliente | Reserva de stock de 15 minutos en checkout | RN-04 |
| US-03 | Sistema (Pagos) | Revalidación de stock antes de confirmar el pago | RN-05 |
| US-04 | Cliente | Opciones ante producto agotado durante checkout | RN-06 |
| US-05 | Cliente | Límite de 50 unidades por SKU por pedido | RN-07 |
| US-06 | Cliente | 3 intentos de pago en 15 minutos | RN-08 |
| US-07 | Pagos / Riesgo | Revisión antifraude en pedidos > $15,000 MXN | RN-09 |
| US-08 | Sistema | Cancelación automática por pago no confirmado | RN-10 |
| US-09 | Cliente | Cancelación libre dentro de 2 horas | RN-11 |
| US-10 | Agente de Atención al Cliente | Cancelación asistida antes de "En tránsito" | RN-12 |
| US-11 | Supervisor de Atención al Cliente | Excepción de cancelación tras "En tránsito" | RN-13 |
| US-12 | Sistema | Asignación automática de almacén de origen | RN-14 |
| US-13 | Supervisor de Almacén | Resolución de incidencia de faltante físico | RN-15 |
| US-14 | Cliente | Visibilidad de sub-envíos en pedido dividido | RN-16 |
| US-15 | Cliente | Reprogramación o reembolso tras entrega fallida | RN-17 / RN-18 |
| US-16 | Cliente | Devolución inmediata por rechazo de paquete | RN-19 |
| US-17 | Agente de Atención al Cliente | Devolución estándar dentro de política | RN-20 |
| US-18 | Supervisor de Atención al Cliente | Devolución excepcional con evidencia | RN-21 |
| US-19 | Cliente | Estatus de pedido visible sin llamar a soporte | Necesidad de negocio #4 |
| US-20 | Gerente de Operaciones | Reporte diario de discrepancia de inventario | Objetivo 1 |
| US-21 | Gerente de Operaciones | Reportes mensuales de KPIs operativos | Objetivos 2 y 3 |

---

## Checkout e Inventario

### US-01: Carrito como intención de compra
**Como** Cliente,  
**Quiero** que agregar productos al carrito no genere un pedido ni reserve inventario,  
**Para** poder explorar y comparar productos sin comprometer existencia real hasta que decida pagar.  

**Trazabilidad**: RN-01  
**Criterios de aceptación**:  
```gherkin
Escenario: Agregar productos al carrito no afecta el inventario
  Dado un producto con 10 unidades de existencia disponible
  Cuando el cliente agrega 3 unidades de ese producto a su carrito
  Y no inicia el proceso de checkout
  Entonces la existencia disponible del producto se mantiene en 10 unidades
  Y no se crea ningún pedido en el sistema
```

---

### US-02: Reserva temporal de inventario en checkout
**Como** Cliente,  
**Quiero** que el sistema reserve el stock de los productos de mi carrito al entrar a checkout,  
**Para** tener 15 minutos garantizados para completar mi compra sin que otro cliente me gane el producto.  

**Trazabilidad**: RN-04  
**Criterios de aceptación**:  
```gherkin
Escenario: El sistema reserva stock al iniciar el checkout
  Dado un producto con 5 unidades de existencia disponible
  Cuando el cliente inicia el checkout con 2 unidades de ese producto
  Entonces la existencia reservada aumenta en 2 unidades
  Y la existencia disponible para otros clientes disminuye a 3 unidades

Escenario: La reserva se libera si el pago no se confirma a tiempo
  Dado un cliente con una reserva activa de 2 unidades desde hace 15 minutos
  Cuando el pago aún no ha sido confirmado
  Entonces el sistema libera automáticamente la reserva
  Y las 2 unidades vuelven a estar disponibles para otros clientes
```

---

### US-03: Revalidación de stock antes de confirmar el pago
**Como** Sistema (módulo de Pagos),  
**Quiero** revalidar la existencia disponible de cada ítem inmediatamente antes de confirmar el pago,  
**Para** evitar confirmar pedidos de productos que se agotaron durante el proceso de checkout.  

**Trazabilidad**: RN-05  
**Criterios de aceptación**:  
```gherkin
Escenario: Revalidación exitosa antes de confirmar el pago
  Dado un carrito en checkout con existencia disponible suficiente al momento de iniciar
  Cuando el cliente confirma el método de pago
  Y el sistema revalida el stock de cada ítem
  Entonces si la existencia sigue siendo suficiente, el pago se procesa normalmente
```

---

### US-04: Opciones ante producto agotado durante el checkout
**Como** Cliente,  
**Quiero** recibir opciones claras cuando un producto de mi pedido se agote justo antes de pagar,  
**Para** decidir cómo continuar mi compra sin perder el resto de mi pedido.  

**Trazabilidad**: RN-06  
**Criterios de aceptación**:  
```gherkin
Escenario: El sistema presenta las tres opciones al detectar faltante
  Dado un ítem del carrito sin existencia suficiente al revalidar el stock
  Cuando el sistema detiene el checkout de ese ítem
  Entonces se presentan al cliente las opciones de eliminar el ítem, dejarlo en espera de restock o sustituirlo

Escenario: La sustitución requiere confirmación explícita
  Dado el sistema sugiere un producto sustituto para el ítem agotado
  Cuando el cliente no confirma explícitamente la sustitución
  Entonces el sistema no reemplaza el ítem de forma automática
```

---

### US-05: Límite de unidades por SKU
**Como** Cliente,  
**Quiero** que el sistema me impida agregar más de 50 unidades del mismo producto a un pedido,  
**Para** que exista disponibilidad justa para otros clientes y se prevengan compras de reventa.  

**Trazabilidad**: RN-07  
**Criterios de aceptación**:  
```gherkin
Escenario: Bloqueo al exceder el límite por SKU
  Dado un carrito con 50 unidades de un mismo SKU
  Cuando el cliente intenta agregar 1 unidad adicional del mismo SKU
  Entonces el sistema rechaza la operación
  Y muestra un mensaje indicando el límite máximo de 50 unidades por SKU
```

---

## Pago

### US-06: Reintentos de pago
**Como** Cliente,  
**Quiero** contar con hasta 3 intentos de pago dentro de una ventana de 15 minutos,  
**Para** poder corregir un error de pago sin perder mi reserva de inventario.  

**Trazabilidad**: RN-08  
**Criterios de aceptación**:  
```gherkin
Escenario: Reintento exitoso dentro del límite
  Dado un cliente con 1 intento de pago rechazado en los últimos 15 minutos
  Cuando el cliente reintenta el pago con otro método
  Entonces el sistema acepta el reintento
  Y conserva la reserva de inventario mientras no se agoten los 3 intentos

Escenario: Bloqueo tras el tercer rechazo
  Dado un cliente que acumula 3 intentos de pago rechazados en 15 minutos
  Cuando ocurre el tercer rechazo
  Entonces el sistema libera el carrito
  Y el cliente debe reiniciar el proceso de checkout
```

---

### US-07: Revisión antifraude por monto elevado
**Como** Analista de Pagos / Riesgo,  
**Quiero** que los pedidos mayores a $15,000 MXN se envíen automáticamente a revisión antifraude,  
**Para** proteger a PetMarket de operaciones fraudulentas antes de iniciar la preparación del pedido.  

**Trazabilidad**: RN-09  
**Criterios de aceptación**:  
```gherkin
Escenario: Pedido de alto valor pasa a revisión manual
  Dado un pedido con monto total de $18,000 MXN y pago confirmado
  Cuando el sistema evalúa el monto del pedido
  Entonces el pedido pasa a estatus de revisión antifraude
  Y no avanza a preparación hasta que un analista lo resuelva en un plazo máximo de 24 horas
```

---

### US-08: Cancelación automática por pago no confirmado
**Como** Sistema,  
**Quiero** cancelar automáticamente un pedido cuando se agoten los intentos o venza la ventana de pago,  
**Para** liberar la reserva de inventario y mantener el catálogo actualizado sin intervención manual.  

**Trazabilidad**: RN-10  
**Criterios de aceptación**:  
```gherkin
Escenario: Cancelación automática sin cargo ni registro visible
  Dado un cliente que agotó sus 3 intentos de pago sin éxito
  Cuando vence la ventana de 15 minutos de reserva
  Entonces el pedido pasa a estatus "Cancelado por pago no confirmado"
  Y la reserva de inventario se libera al catálogo general
```

---

## Cancelación

### US-09: Cancelación libre dentro de la ventana de 2 horas
**Como** Cliente,  
**Quiero** poder cancelar mi pedido desde la app sin costo mientras esté en "Pago confirmado" o "En preparación",  
**Para** tener flexibilidad para corregir un error de compra sin depender de un agente.  

**Trazabilidad**: RN-11  
**Criterios de aceptación**:  
```gherkin
Escenario: Cancelación exitosa dentro de la ventana de 2 horas
  Dado un pedido en estatus "En preparación" confirmado hace 1 hora
  Cuando el cliente solicita cancelar el pedido desde la app
  Entonces el sistema cancela el pedido sin costo ni penalización

Escenario: Cancelación automática rechazada fuera de la ventana
  Dado un pedido confirmado hace 3 horas
  Cuando el cliente intenta cancelarlo directamente desde la app
  Entonces el sistema no permite la autocancelación
  Y redirige al cliente a contactar a Atención al Cliente
```

---

### US-10: Cancelación asistida por Atención al Cliente
**Como** Agente de Atención al Cliente,  
**Quiero** poder cancelar un pedido en cualquier momento antes de que esté "En tránsito" registrando un motivo,  
**Para** atender solicitudes válidas de cancelación fuera de la ventana automática de 2 horas.  

**Trazabilidad**: RN-12  
**Criterios de aceptación**:  
```gherkin
Escenario: Cancelación con registro de motivo y decisión de reintegro
  Dado un pedido en estatus "Empacado", aún no marcado "En tránsito"
  Cuando un Agente de Atención al Cliente cancela el pedido y registra un motivo
  Entonces el pedido cambia a estatus cancelado
  Y el agente registra si el producto se reintegra a inventario o se contabiliza como merma
```

---

### US-11: Excepción de cancelación tras "En tránsito"
**Como** Supervisor de Atención al Cliente,  
**Quiero** poder autorizar, de forma excepcional, la cancelación de un pedido que ya está "En tránsito",  
**Para** resolver casos justificados de error comprobable de PetMarket sin violar la regla general.  

**Trazabilidad**: RN-13  
**Criterios de aceptación**:  
```gherkin
Escenario: Autorización excepcional documentada
  Dado un pedido en estatus "En tránsito" con un error comprobable atribuible a PetMarket
  Cuando el Supervisor de Atención al Cliente autoriza la cancelación excepcional
  Entonces el pedido se cancela de forma excepcional
  Y la autorización queda registrada junto con el motivo y el responsable
```

---

## Asignación de Almacén y Envíos

### US-12: Asignación automática del almacén de origen
**Como** Sistema,  
**Quiero** asignar automáticamente el almacén de origen según cercanía al domicilio y carga de pedidos pendientes,  
**Para** optimizar tiempos de entrega de forma consistente sin depender del criterio manual de un agente.  

**Trazabilidad**: RN-14  
**Criterios de aceptación**:  
```gherkin
Escenario: Asignación por cercanía
  Dado dos almacenes con stock suficiente para un pedido, uno más cercano al domicilio de entrega
  Cuando el sistema asigna el almacén de origen
  Entonces se selecciona el almacén más cercano al domicilio del cliente

Escenario: Desempate por carga de pedidos pendientes
  Dado dos almacenes a la misma distancia del domicilio con stock suficiente
  Cuando el sistema asigna el almacén de origen
  Entonces se selecciona el almacén con menor carga de pedidos pendientes
```

---

### US-13: Resolución de incidencia de faltante físico
**Como** Supervisor de Almacén,  
**Quiero** resolver una incidencia reportada cuando existe stock en sistema pero no hay existencia física real,  
**Para** corregir la discrepancia y evitar que el pedido quede detenido sin explicación.  

**Trazabilidad**: RN-15  
**Criterios de aceptación**:  
```gherkin
Escenario: Reasignación automática tras confirmar el faltante
  Dado un Agente de Almacén reporta faltante físico de un SKU pese a existencia en sistema
  Cuando el Supervisor de Almacén confirma la incidencia
  Entonces el sistema reasigna automáticamente el pedido al otro almacén con stock suficiente
```

---

### US-14: Visibilidad de pedidos divididos entre almacenes
**Como** Cliente,  
**Quiero** ver cada sub-envío de mi pedido por separado con su propio folio, guía y fecha estimada,  
**Para** dar seguimiento claro a mi compra cuando se surte desde dos almacenes distintos.  

**Trazabilidad**: RN-16  
**Criterios de aceptación**:  
```gherkin
Escenario: Pedido dividido visible como dos sub-envíos
  Dado un pedido que ningún almacén puede cubrir al 100% por sí solo
  Cuando el sistema divide el pedido en dos sub-envíos
  Entonces el cliente ve ambos sub-envíos en "Rastrear mi pedido" con folios y guías independientes
  Y no se le cobra flete adicional por la división
  Y el pedido padre se marca "Entregado" solo cuando ambos sub-envíos han llegado
```

---

## Entrega y Devoluciones

### US-15: Reprogramación o reembolso tras entrega fallida
**Como** Cliente,  
**Quiero** que se me contacte para reprogramar la entrega o solicitar reembolso si fallan los dos intentos de entrega,  
**Para** no quedar sin solución cuando la paquetería no logra entregarme el pedido.  

**Trazabilidad**: RN-17 / RN-18  
**Criterios de aceptación**:  
```gherkin
Escenario: Contacto tras el segundo intento fallido
  Dado un pedido con un primer intento de entrega fallido
  Cuando el segundo intento realizado al día hábil siguiente también falla
  Entonces el paquete regresa al almacén de origen
  Y Atención al Cliente contacta al cliente para ofrecer reprogramación o reembolso

Escenario: Reembolso automático por falta de respuesta
  Dado un cliente contactado tras dos intentos fallidos de entrega
  Cuando el cliente no responde en un plazo de 5 días hábiles
  Entonces el sistema procesa un reembolso automático al método de pago original
```

---

### US-16: Devolución inmediata por rechazo del paquete
**Como** Cliente,  
**Quiero** que el rechazo del paquete en el momento de la entrega se procese como devolución inmediata,  
**Para** recibir mi reembolso sin que se confunda con un caso de entrega fallida por ausencia.  

**Trazabilidad**: RN-19  
**Criterios de aceptación**:  
```gherkin
Escenario: Rechazo en sitio inicia devolución inmediata
  Dado un repartidor presente en el domicilio con el paquete
  Cuando el cliente rechaza el paquete en el momento de la entrega
  Entonces el sistema registra el caso como devolución inmediata
  Y sigue la misma ruta de procesamiento de reembolso
```

---

### US-17: Devolución estándar dentro de política
**Como** Agente de Atención al Cliente,  
**Quiero** procesar devoluciones dentro de la ventana de 5 días hábiles y con producto sin usar,  
**Para** resolver casos estándar de devolución sin necesidad de escalar al supervisor.  

**Trazabilidad**: RN-20  
**Criterios de aceptación**:  
```gherkin
Escenario: Devolución aprobada dentro de política
  Dado un pedido entregado hace 3 días hábiles con el producto sin usar
  Cuando el cliente solicita una devolución y un Agente la revisa
  Entonces el agente aprueba la devolución sin necesidad de escalar al Supervisor
```

---

### US-18: Devolución excepcional con evidencia fotográfica
**Como** Supervisor de Atención al Cliente,  
**Quiero** autorizar devoluciones fuera de la ventana estándar, sin empaque original o por daño,  
**Para** resolver casos justificados que exceden la política estándar mediante evidencia adecuada.  

**Trazabilidad**: RN-21  
**Criterios de aceptación**:  
```gherkin
Escenario: Autorización de excepción con evidencia fotográfica
  Dado una solicitud de devolución por producto dañado fuera de la ventana de 5 días hábiles
  Cuando el cliente adjunta evidencia fotográfica del daño
  Y el Supervisor de Atención al Cliente revisa el caso
  Entonces el Supervisor puede autorizar la devolución de forma excepcional

Escenario: Un agente no puede aprobar la excepción
  Dado una solicitud de devolución sin empaque original fuera de política
  Cuando un Agente de Atención al Cliente intenta aprobarla
  Entonces el sistema bloquea la aprobación y exige escalación a Supervisor
```

---

## Visibilidad y Reportes

### US-19: Visibilidad de estatus del pedido para el cliente
**Como** Cliente,  
**Quiero** ver en la app/web el estatus real y actualizado de mi pedido,  
**Para** conocer en qué etapa está mi compra sin tener que llamar a Atención al Cliente.  

**Trazabilidad**: Necesidad de negocio #4 / Sección 10  
**Criterios de aceptación**:  
```gherkin
Escenario: Estatus visible en autoservicio
  Dado un pedido en estatus "En tránsito" con guía de rastreo asignada
  Cuando el cliente consulta su pedido en la app
  Entonces visualiza el estatus actual y la guía de rastreo directamente
```

---

### US-20: Reporte diario de discrepancia de inventario
**Como** Gerente de Operaciones,  
**Quiero** recibir un reporte diario de discrepancia entre el inventario web y la existencia física por SKU y almacén,  
**Para** detectar y corregir de forma oportuna errores de stock antes de que afecten la operación.  

**Trazabilidad**: Sección 10 / Objetivo 1  
**Criterios de aceptación**:  
```gherkin
Escenario: Generación del reporte diario
  Dado que existen movimientos de inventario registrados durante el día
  Cuando el sistema ejecuta el corte diario de discrepancia de inventario
  Entonces se genera un reporte consolidado por SKU y almacén para el Gerente de Operaciones
```

---

### US-21: Reportes mensuales de indicadores operativos
**Como** Gerente de Operaciones,  
**Quiero** consultar en un tablero mensual los tiempos de ciclo, porcentaje de pedidos divididos y tasas de cancelación/devolución,  
**Para** evaluar el desempeño operativo y medir el cumplimiento de objetivos del proyecto.  

**Trazabilidad**: Sección 10 / Objetivos 2 y 3  
**Criterios de aceptación**:  
```gherkin
Escenario: Consulta del tablero mensual
  Dado el cierre de un periodo mensual con pedidos procesados
  Cuando el Gerente de Operaciones abre el tablero de control
  Entonces visualiza los KPIs de tiempo de ciclo por etapa, % de pedidos divididos y tasas de cancelación y devolución
```
