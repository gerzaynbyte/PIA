# Proceso de Negocio Integrado (BPMN) - PetMarket

Este documento describe el flujo operativo end-to-end de PetMarket desde el inicio del proceso de checkout hasta la entrega exitosa o resolución de excepciones (cancelaciones, devoluciones e intentos fallidos de entrega).

---

## Diagrama de Flujo de Negocio (PlantUML BPMN)

```plantuml
@startuml
skinparam handwritten false
skinparam defaultFontName Arial
skinparam ActivityBackgroundColor #E3F2FD
skinparam ActivityBorderColor #1565C0

title Diagrama de Flujo Operativo PetMarket (BPMN Integrado)

start
:Cliente inicia Checkout en App/Web;
:Reservar stock por 15 min (RN-04);

if (¿Stock disponible al revalidar pre-cobro? RN-05) then (Sí)
  :Procesar intento de pago (RN-08);
  if (¿Pago Exitoso?) then (Sí)
    if (¿Monto Total > $15,000 MXN? RN-09) then (Sí)
      :Estado: EN_REVISION_ANTIFRAUDE;
      :Revisión Manual por Analista de Riesgo (Max 24h);
      if (¿Aprobado por Riesgo?) then (Sí)
        :Estado: PAGO_CONFIRMADO;
      else (No)
        :Cancelar Pedido y Liberar Stock (RN-03);
        stop
      endif
    else (No)
      :Estado: PAGO_CONFIRMADO;
    endif
    
    :Asignar Almacén por Cercanía y Carga (RN-14);
    if (¿Un solo almacén cubre el 100% del stock?) then (Sí)
      :Preparar y Empacar Envío Único;
    else (No)
      :Dividir en Sub-envíos Independientes sin costo extra (RN-16);
    endif
    
    :Estado: EN_TRANSITO;
    :Entrega mediante Paquetería;
    
    if (¿Entrega Exitosa en 1er Intento?) then (Sí)
      :Estado: ENTREGADO;
      :Transcurrir 5 días hábiles sin reclamo (RN-02);
      :Cierre Exitoso de Pedido;
      stop
    else (No)
      :Segundo Intento de Entrega al día hábil siguiente (RN-17);
      if (¿Segundo Intento Exitoso?) then (Sí)
        :Estado: ENTREGADO;
        :Transcurrir 5 días hábiles sin reclamo (RN-02);
        :Cierre Exitoso de Pedido;
        stop
      else (No)
        :Retorno del paquete a Almacén de Origen;
        :Atención al Cliente contacta al cliente (RN-17);
        if (¿Cliente responde en 5 días hábiles?) then (Sí / Reprogramar)
          :Reprogramar Entrega;
          stop
        else (No / Reembolsar)
          :Reembolso Automático al método original (RN-18);
          :Cierre por Excepción (RN-03);
          stop
        endif
      endif
    endif

  else (No)
    if (¿Reintentos < 3 dentro de 15 min? RN-08) then (Sí)
      :Permitir nuevo intento de pago;
      stop
    else (No)
      :Estado: CANCELADO_POR_PAGO_NO_CONFIRMADO (RN-10);
      :Liberar Reserva de Stock;
      stop
    endif
  endif
else (No)
  :Presentar 3 Opciones (Eliminar, Esperar Restock, Sustituir) (RN-06);
  stop
endif
@enduml
```

---

## Resumen de Puntos de Decisión Clave
1. **RN-05 (Revalidación)**: Ocurre antes de enviar el cobro a la pasarela.
2. **RN-09 (Antifraude)**: Detiene temporalmente el pedido si excede \$15,000 MXN.
3. **RN-16 (División)**: Sub-envíos independientes con folios derivados y guías propias.
4. **RN-17/18 (Entrega Fallida)**: Límite de 2 intentos antes de retornar a almacén y proceder a reembolso por inactividad.
