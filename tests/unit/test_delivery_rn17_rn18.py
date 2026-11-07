"""RN-17 (doble intento fallido -> retorno + contacto) y
RN-18 (reembolso automático tras 5 días hábiles de silencio)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from src.domain.entities.delivery import (Delivery, dias_habiles_entre)
from src.domain.value_objects.delivery_status import DeliveryStatus

# ---------------- RN-17 ----------------

def test_intento_exitoso_entrega_el_paquete():
    d = Delivery.create("SUB-1", "GUIA-777").value
    r = d.registrar_intento(exitoso=True)
    assert not r.is_failure and d.status == DeliveryStatus.ENTREGADO

def test_primer_intento_fallido_permite_segundo_intento():
    """El 1er fallo NO retorna el paquete; el 2do intento es al día hábil siguiente."""
    d = Delivery.create("SUB-1", "GUIA-777").value
    r1 = d.registrar_intento(exitoso=False, motivo="Cliente ausente")
    assert r1.value == DeliveryStatus.EN_TRANSITO
    assert len(d.intentos) == 1

def test_segundo_intento_fallido_retorna_a_almacen_rn17():
    d = Delivery.create("SUB-1", "GUIA-777").value
    d.registrar_intento(exitoso=False, motivo="Cliente ausente")
    r2 = d.registrar_intento(exitoso=False, motivo="Dirección incorrecta")
    assert r2.value == DeliveryStatus.REGRESO_ALMACEN
    assert d.intentos_fallidos == 2

def test_tercer_intento_es_prohibido_rn17():
    d = Delivery.create("SUB-1", "GUIA-777").value
    d.registrar_intento(exitoso=False, motivo="ausencia")
    d.registrar_intento(exitoso=False, motivo="ausencia")
    r = d.registrar_intento(exitoso=False, motivo="ausencia")
    assert r.is_failure  # paquete ya está en REGRESO_ALMACEN; jamás un 3er intento

def test_intento_fallido_sin_motivo_es_rechazado():
    d = Delivery.create("SUB-1", "GUIA-777").value
    with pytest.raises(ValueError, match="motivo"):
        d.registrar_intento(exitoso=False, motivo=None)

def test_contacto_solo_despues_del_retorno_rn17():
    d = Delivery.create("SUB-1", "GUIA-777").value
    r = d.registrar_contacto_cliente()
    assert r.is_failure  # aún en EN_TRANSITO: nada que contactar
    d.registrar_intento(exitoso=False, motivo="ausencia")
    d.registrar_intento(exitoso=False, motivo="ausencia")
    r = d.registrar_contacto_cliente(fecha=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc))
    assert not r.is_failure and d.status == DeliveryStatus.CONTACTO_CLIENTE

# ---------------- RN-18 ----------------

def _en_contacto(fecha_contacto: datetime) -> Delivery:
    d = Delivery.create("SUB-1", "GUIA-777").value
    d.registrar_intento(exitoso=False, motivo="ausencia")
    d.registrar_intento(exitoso=False, motivo="ausencia")
    d.registrar_contacto_cliente(fecha=fecha_contacto)
    return d

def test_reprograma_si_responde_dentro_del_plazo_rn17():
    contacto = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)  # lunes
    d = _en_contacto(contacto)
    r = d.reprogramar(fecha_respuesta=contacto + timedelta(days=2))
    assert not r.is_failure and d.status == DeliveryStatus.REPROGRAMADA

def test_reembolso_automatico_tras_5_dias_habiles_rn18():
    contacto = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)  # lunes
    d = _en_contacto(contacto)
    # 5 hábiles = lun..vie (2-6 nov); el 9 nov (segunda semana) ya expiró
    r = d.resolver_por_inactividad(fecha_actual=datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc))
    assert not r.is_failure
    assert d.status == DeliveryStatus.REEMBOLSADO_AUTOMATICO

def test_no_reembolsa_antes_de_que_expire_el_plazo_rn18():
    contacto = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)  # lunes
    d = _en_contacto(contacto)
    r = d.resolver_por_inactividad(fecha_actual=datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc))
    assert r.is_failure
    assert "vigente" in r.error
    assert d.status == DeliveryStatus.CONTACTO_CLIENTE

def test_respuesta_tardia_no_permite_reprogramar_rn18():
    """El punto fino de RN-18: si responde tarde, ya no hay reprogramación."""
    contacto = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)  # lunes
    d = _en_contacto(contacto)
    r = d.reprogramar(fecha_respuesta=datetime(2026, 11, 10, tzinfo=timezone.utc))
    assert r.is_failure and "RN-18" in r.error

def test_fin_de_semana_no_cuenta_como_dias_habiles_rn18():
    """Caso límite: contacto viernes, cierre el sábado de la SEMANA SIGUIENTE
    debe contar 5 hábiles y 7 naturales."""
    viernes = datetime(2026, 11, 6, tzinfo=timezone.utc)
    sabado = datetime(2026, 11, 13, tzinfo=timezone.utc)
    assert dias_habiles_entre(viernes.date(), sabado.date()) == 6  # 6,9,10,11,12,13
    assert dias_habiles_entre(viernes.date(), (viernes + timedelta(days=6)).date()) == 5

def test_reembolso_es_idempotente():
    contacto = datetime(2026, 11, 2, tzinfo=timezone.utc)
    d = _en_contacto(contacto)
    futura = datetime(2026, 11, 10, tzinfo=timezone.utc)
    d.resolver_por_inactividad(fecha_actual=futura)
    r = d.resolver_por_inactividad(fecha_actual=futura)  # re-run del job
    assert not r.is_failure and d.status == DeliveryStatus.REEMBOLSADO_AUTOMATICO