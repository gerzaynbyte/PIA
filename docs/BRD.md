# Business Requirements Document (BRD) - PetMarket

## 1. Introducción y Contexto del Negocio
PetMarket es un negocio de comercio electrónico que comercializa comestibles, complementos y artículos para mascotas, operando con dos depósitos (almacenes) y distintas modalidades de entrega. El proceso abarca desde la confirmación del pago hasta la entrega final, pasando por la preparación, empaque, despacho, cancelaciones y devoluciones.

## 2. Problemas Actuales y Oportunidades
- **Discrepancia de inventario**: El inventario del sitio web difiere de la existencia física (~15%).
- **División de pedidos**: Complejidad en seguimiento cuando un pedido se surte desde dos almacenes.
- **Falta de visibilidad**: Alto volumen de llamadas a soporte preguntando "¿dónde está mi pedido?".
- **Gestión manual**: Procesamiento manual de cancelaciones y devoluciones repetitivo.

## 3. Objetivos del Proyecto (Medibles)
1. **Inventario Confiable**: Reducir la discrepancia de inventario de ~15% a menos del 2%.
2. **Autoservicio y Visibilidad**: Reducir en un 60% las llamadas a Atención al Cliente sobre el estatus de pedidos.
3. **Automatización de Reglas**: Resolver al menos el 70% de cancelaciones/devoluciones dentro de política sin decisión manual caso por caso.

## 4. Reglas de Negocio Confirmadas (RN-01 a RN-21)
- **RN-01**: El carrito de compras representa intención de compra; no crea pedido ni reserva stock.
- **RN-02**: Cierre exitoso del proceso tras quedar "Entregado" y transcurrir 5 días hábiles sin reclamo.
- **RN-03**: Cierre por excepción al cancelar, rebasar reintentos de pago o procesar reembolso completo.
- **RN-04**: El stock se reserva por 15 minutos al iniciar el checkout. Si no se confirma el pago, se libera automáticamente.
- **RN-05**: El stock se revalida obligatoriamente inmediatamente antes de procesar el pago.
- **RN-06**: Si un ítem se agota al revalidar, se ofrecen 3 opciones: eliminar ítem, esperar restock o sustituir (requiere confirmación explícita del cliente).
- **RN-07**: Límite estricto de 50 unidades por SKU por pedido para evitar reventas.
- **RN-08**: Máximo 3 intentos de pago dentro de la ventana de 15 minutos.
- **RN-09**: Pedidos mayores a $15,000 MXN pasan automáticamente a revisión antifraude manual (plazo hasta 24h).
- **RN-10**: Si vencen intentos o tiempo sin pago, pasa a "Cancelado por pago no confirmado" y libera reserva.
- **RN-11**: El cliente puede cancelar libremente en la app dentro de 2 horas desde la confirmación de pago (si está en "Pago confirmado" o "En preparación").
- **RN-12**: Un Agente de Atención al Cliente puede cancelar en cualquier momento antes de "En tránsito", registrando motivo y destino del producto (inventario o merma).
- **RN-13**: Tras "En tránsito", no se permite cancelación estándar; requiere autorización del Supervisor de Atención al Cliente por excepción.
- **RN-14**: Asignación automática de almacén por cercanía al domicilio y, en desempate, menor carga de pedidos pendientes.
- **RN-15**: Incidencia de faltante físico es resuelta por el Supervisor de Almacén, pudiendo reasignar al otro almacén.
- **RN-16**: División automática en sub-envíos con folios y guías independientes cuando ningún almacén cubre el 100% del stock. Sin flete extra. El pedido padre se marca "Entregado" solo cuando todos los sub-envíos son entregados.
- **RN-17**: Paquetería realiza 2 intentos de entrega. Si fallan, el paquete regresa al almacén y Atención al Cliente contacta para reprogramar o reembolsar.
- **RN-18**: Reembolso automático si el cliente no responde en 5 días hábiles tras la doble entrega fallida.
- **RN-19**: Rechazo del paquete en sitio se trata como devolución inmediata.
- **RN-20**: Devolución estándar aplica en 5 días hábiles con producto sin usar.
- **RN-21**: Devolución fuera de ventana, sin empaque o por daño exige evidencia fotográfica y aprobación exclusiva del Supervisor de Atención al Cliente.
