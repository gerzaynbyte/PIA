# Diagramas UML de Arquitectura - PetMarket

Este documento contiene las representaciones arquitectónicas en PlantUML que detallan la estructura de clases de la capa de dominio, aplicación e infraestructura, así como el flujo de secuencia para el procesamiento de pedidos y evaluación antifraude.

---

## 1. Diagrama de Clases (Arquitectura Limpia / Hexagonal)

```plantuml
@startuml
title PetMarket - Diagrama de Clases Hexagonal

package "Domain Layer" #E1F5EE {
  enum EstadoPedido {
    PENDIENTE_PAGO
    EN_REVISION_ANTIFRAUDE
    PAGO_CONFIRMADO
    EN_PREPARACION
    EMPACADO
    EN_TRANSITO
    ENTREGADO
    CANCELADO
    CANCELADO_PAGO_EXPIRADO
    CANCELADO_EXCEPCIONAL
    EN_PROCESO_DEVOLUCION
    DEVOLUCION_COMPLETADA
    FINALIZADO_EXITOSO
    (+ estados de entrega fallida y rechazo)
  }

  enum RolUsuario {
    CLIENTE
    AGENTE_ATENCION
    SUPERVISOR_ATENCION
    AGENTE_ALMACEN
    SUPERVISOR_ALMACEN
  }

  class Pedido <<AggregateRoot>> {
    +id: string
    +clienteId: string
    +montoTotal: number
    +estado: EstadoPedido
    +fechaCreacion: Date
    +items: ItemPedido[]
    +subEnvios: SubEnvio[]
    +agregarSubEnvio(subEnvio: SubEnvio): void
  }

  class SubEnvio <<Entity>> {
    +id: string
    +almacenOrigen: string
    +guiaRastreo: string
    +estado: string
    +items: ItemPedido[]
  }

  class ItemPedido <<ValueObject>> {
    +sku: string
    +cantidad: number
    +precioUnitario: number
  }

  class PedidoStateMachine {
    +{static} canTransition(actual: EstadoPedido, nuevo: EstadoPedido, rol: RolUsuario, horas: number): boolean
  }

  interface ISpecification<T> {
    +isSatisfiedBy(candidate: T): boolean
  }

  class RequiereRevisionAntifraudeSpecification implements ISpecification {
    +isSatisfiedBy(pedido: Pedido): boolean
  }

  class LimiteUnidadesPorSkuSpecification implements ISpecification {
    +isSatisfiedBy(items: ItemPedido[]): boolean
  }

  Pedido "1" *-- "0..*" SubEnvio
  Pedido "1" *-- "1..*" ItemPedido
  SubEnvio "1" *-- "1..*" ItemPedido
  Pedido ..> EstadoPedido
  PedidoStateMachine ..> EstadoPedido
  PedidoStateMachine ..> RolUsuario
}

package "Application Layer" #E3F2FD {
  class OrderApplicationService {
    -limitSpec: LimiteUnidadesPorSkuSpecification
    -fraudSpec: RequiereRevisionAntifraudeSpecification
    +createOrder(id, clienteId, items, montoTotal): Promise<Pedido>
    +cancelOrder(pedidoId, rol, motivo): Promise<Pedido>
    +divideOrder(pedidoId, almacenes): Promise<Pedido>
  }
}

package "Infrastructure Layer" #FFF3E0 {
  interface IOrderRepository {
    +save(pedido: Pedido): Promise<void>
    +findById(id: string): Promise<Pedido | null>
    +findAll(): Promise<Pedido[]>
  }

  interface IInventoryRepository {
    +checkAndReserveStock(items: ItemPedido[]): Promise<boolean>
    +releaseStock(items: ItemPedido[]): Promise<void>
  }

  class InMemoryOrderRepository implements IOrderRepository {
    -storage: Map<string, Pedido>
    +save(pedido: Pedido): Promise<void>
    +findById(id: string): Promise<Pedido | null>
    +findAll(): Promise<Pedido[]>
  }

  class InMemoryInventoryRepository implements IInventoryRepository {
    -stock: Map<string, number>
    +checkAndReserveStock(items: ItemPedido[]): Promise<boolean>
    +releaseStock(items: ItemPedido[]): Promise<void>
  }
}

OrderApplicationService --> IOrderRepository
OrderApplicationService --> IInventoryRepository
OrderApplicationService ..> Pedido
@enduml
```

---

## 2. Diagrama de Secuencia (Creación de Pedido y Evaluación Antifraude)

```plantuml
@startuml
title Secuencia: Creación de Pedido, Reserva y Evaluación Antifraude (RN-04, RN-05, RN-07, RN-09)

autonumber
actor Cliente
participant OrderController as Controller
participant OrderApplicationService as Service
participant LimiteUnidadesPorSkuSpecification as LimitSpec
participant RequiereRevisionAntifraudeSpecification as FraudSpec
participant InMemoryInventoryRepository as InvRepo
participant InMemoryOrderRepository as OrderRepo

Cliente -> Controller: POST /api/v1/orders
Controller -> Service: createOrder(id, clienteId, items, montoTotal)

Service -> LimitSpec: isSatisfiedBy(items)
alt Unidades por SKU > 50 (Violación RN-07)
  LimitSpec --> Service: false
  Service --> Controller: Throw Error ("RN-07 Violada")
  Controller --> Cliente: HTTP 400 Bad Request
else Validación Correcta (<= 50 por SKU)
  LimitSpec --> Service: true
  Service -> InvRepo: checkAndReserveStock(items)
  
  alt Stock Insuficiente (Violación RN-05)
    InvRepo --> Service: false
    Service --> Controller: Throw Error ("RN-05 Violada")
    Controller --> Cliente: HTTP 400 Bad Request
  else Stock Reservado Exitosamente
    InvRepo --> Service: true
    
    Service -> FraudSpec: isSatisfiedBy(pedido)
    alt Monto Total > $15,000 MXN (RN-09)
      FraudSpec --> Service: true (Requiere Revisión)
      Service -> OrderRepo: save(Estado: EN_REVISION_ANTIFRAUDE)
    else Monto Total <= $15,000 MXN
      FraudSpec --> Service: false
      Service -> OrderRepo: save(Estado: PAGO_CONFIRMADO)
    end

    OrderRepo --> Service: Confirmación de Guardado
    Service --> Controller: Pedido Creado (Instancia de Pedido)
    Controller --> Cliente: HTTP 201 Created (JSON Response)
  end
end
@enduml
```
