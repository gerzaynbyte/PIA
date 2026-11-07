# Architecture Decision Records (ADRs) - PetMarket

Este documento registra las decisiones de arquitectura de software fundamentales tomadas durante el diseño del sistema transaccional de PetMarket.

---

## ADR-01: Selección del Patrón de Lógica de Negocio (Domain Model)

- **Estado**: Aceptado
- **Contexto**: PetMarket cuenta con 21 reglas de negocio entrelazadas, reservas de inventario temporales de 15 minutos, revalidación pre-cobro, sub-envíos multialmacén y una matriz de permisos jerárquicos por roles.
- **Alternativas Evaluadas**:
  1. *Transaction Script*: Generaría duplicación masiva de código procedural y acoplamiento directo entre controladores y base de datos, incrementando el riesgo de sobreventa de stock.
  2. *Table Module*: Dificultaría la gestión del ciclo de vida complejo de los pedidos y sus reglas temporales.
  3. *Domain Model*: Encapsula el estado y las reglas en entidades ricas protegidas por agregados e invariantes.
- **Decisión**: Adoptar **Domain Model** como patrón central para la capa transaccional.
- **Consecuencias**: 
  - Aislamiento total de las reglas de negocio (RN-01 a RN-21) frente a detalles de infraestructura.
  - Facilidad para realizar pruebas unitarias sobre las reglas del dominio sin depender de base de datos.
  - Requiere mapeo explícito mediante DTOs para la comunicación externa.

---

## ADR-02: Control Transaccional con Repositorios y Unit of Work

- **Estado**: Aceptado
- **Contexto**: Operaciones críticas como la confirmación del cobro y la reserva/descuento de existencias físicas deben ejecutarse bajo una transacción atómica del tipo "todo o nada".
- **Decisión**: Definir el puerto de repositorio como `Protocol` en la capa de aplicación (`OrderRepository`), con adaptadores InMemory y MySQL intercambiables desde la raíz de composición. La atomicidad se logra hoy con **una transacción por `save`** del agregado completo (pedido + líneas + sub-envíos); un **Unit of Work** que abarque varios agregados (reserva + cobro) queda como evolución.
- **Consecuencias**:
  - Cada agregado se guarda de forma atómica; la consistencia entre varios agregados aún no es transaccional.
  - Permite sustituir la persistencia (InMemory ↔ MySQL, y a futuro otra) sin alterar la capa de aplicación.

---

## ADR-03: CQRS Básico con DTOs Planos de Lectura

- **Estado**: Aceptado
- **Contexto**: Alto volumen de consultas de seguimiento por parte de clientes y tableros operativos gerenciales que no deben sobrecargar el modelo de agregados de escritura.
- **Decisión**: Implementar **CQRS Básico**, separando los comandos de modificación (Commands gestionados por el servicio de aplicación) de las consultas de lectura (Queries que retornan DTOs planos).
- **Consecuencias**:
  - Maximiza el rendimiento en la consulta de estatus de pedidos y reportes de inventario.
  - Mantiene las entidades del dominio enfocadas exclusivamente en la validación transaccional.
