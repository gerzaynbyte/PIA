# Glosario de Dominio (Lenguaje Ubicuo) - PetMarket

Este documento establece la terminología estandarizada del dominio (Domain-Driven Design) para garantizar que los desarrolladores, arquitectos, analistas de negocio y partes interesadas compartan un mismo significado conceptual.

---

## 1. Roles y Actores del Sistema

- **Cliente**: Usuario final que explora el catálogo, agrega productos a la bolsa de compras, completa el proceso de checkout y realiza el pago de sus pedidos.
- **Agente de Atención al Cliente**: Personal operativo encargado de gestionar la atención post-venta, procesar cancelaciones asistidas previas al despacho en tránsito y autorizar devoluciones dentro de política.
- **Supervisor de Atención al Cliente**: Rol de autoridad jerárquica con permisos exclusivos para autorizar cancelaciones por excepción (post en tránsito) y devoluciones fuera de política (productos dañados o sin empaque original).
- **Agente de Almacén**: Operador logístico en depósito encargado de las actividades de picking, empaque y preparación de paquetes para despacho. No posee facultades para cancelar pedidos.
- **Supervisor de Almacén**: Responsable de la gestión de existencias físicas en bodega, resolución de incidencias por faltantes de inventario y reasignación de órdenes entre almacenes.

---

## 2. Entidades y Conceptos de Inventario

- **SKU (Stock Keeping Unit)**: Identificador único universal asignado a cada producto individual o variante del catálogo de PetMarket.
- **Existencia Física**: Cantidad real de producto presente físicamente en los estantes del almacén.
- **Existencia Reservada**: Cantidad de inventario bloqueada temporalmente por procesos de checkout activos (ventana de 15 minutos) que aún no han sido cobrados.
- **Existencia Disponible**: Cantidad neta habilitada para venta pública en la tienda en línea. Se calcula como:  
  $$\text{Existencia Disponible} = \text{Existencia Física} - \text{Existencia Reservada}$$
- **Faltante Físico (Discrepancia)**: Incidencia detectada en almacén cuando el sistema refleja existencia disponible pero el producto no se encuentra en el estante durante el picking.

---

## 3. Ciclo de Vida del Pedido y Envíos

- **Folio de Pedido**: Código alfanumérico único e inmutable asignado a una transacción desde su creación.
- **Pedido Padre**: Registro transaccional global generado al confirmar el checkout. Representa la totalidad de la orden del cliente.
- **Sub-envío**: Envío independiente derivado de un Pedido Padre cuando ningún almacén posee el 100% del inventario solicitado. Posee su propio folio derivado y guía de rastreo.
- **Guía de Rastreo**: Código emitido por la paquetería externa asignada para el seguimiento del paquete durante la fase de tránsito.
- **Revisión Antifraude**: Estado de congelamiento operativo aplicado automáticamente a pedidos cuyo monto supere los $15,000 MXN para validación manual de riesgo en un lapso máximo de 24 horas.

---

## 4. Transiciones y Excepciones

- **Ventana de Autocancelación**: Período de 2 horas posteriores a la confirmación del pago en el cual el cliente puede cancelar directamente desde la plataforma sin costo.
- **Intento de Entrega**: Gestión logística de la paquetería para entregar el paquete en el domicilio indicado. Se permiten máximo 2 intentos antes del retorno al depósito.
- **Rechazo en Sitio**: Acción donde el cliente niega la recepción del paquete en su domicilio, desencadenando un retorno y proceso de devolución inmediata.
- **Merma de Empaque**: Clasificación del estado de un producto devuelto o no entregado que no puede reincorporarse al inventario de venta por daños físicos o alteración de empaque.
