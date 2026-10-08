"""Servicios de dominio de EventHub.

Aqui viven las reglas de negocio compartidas por las rutas:

- fecha de referencia de la aplicacion (zona horaria de Colombia);
- lectura del limite diario configurado por cada organizador;
- calculo de horas planificadas por dia;
- deteccion de sobrecarga frente al limite diario.

El objetivo es que BE-03 use exactamente la misma regla en `/hoy`, al
reprogramar (BE-01) y al resolver un conflicto (BE-04), en lugar de
repetir consultas y sumar horas de forma distinta en cada ruta.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from database import supabase

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTES DE NEGOCIO
# ============================================================

ZONA_HORARIA_EVENTHUB = ZoneInfo("America/Bogota")

# Limite diario por defecto cuando el organizador todavia no tiene
# configuracion persistida (no es un valor global compartido: cada
# usuario puede tener el suyo).
LIMITE_HORAS_DIA_POR_DEFECTO = 6
LIMITE_HORAS_DIA_MINIMO = 1
LIMITE_HORAS_DIA_MAXIMO = 16

# Las horas admiten decimales. El total se redondea a dos decimales para
# que el ruido de coma flotante (0.1 + 0.2 = 0.30000000000000004) no
# genere un falso positivo de sobrecarga.
PRECISION_HORAS = 2

ESTADOS_COMPLETADOS = {"completada", "completado", "hecho", "hecha"}


# ============================================================
# MENSAJES FUNCIONALES
# ============================================================

MENSAJE_FECHA_INVALIDA = (
    "La fecha seleccionada no es válida o es anterior al día de hoy."
)

MENSAJE_REDUCCION_INSUFICIENTE = (
    "Las horas reducidas aún exceden el límite diario. "
    "Reduce más horas o cambia la fecha."
)

MENSAJE_CONFLICTO_SOBRECARGA = (
    "Quedarías con {horas}h de gestión planificadas (límite {limite}h)"
)

MENSAJE_REPROGRAMADA = "Fecha reprogramada exitosamente"

MENSAJE_CONFLICTO_RESUELTO = "Cronograma actualizado correctamente"

# Opciones que el frontend ofrece al organizer cuando hay conflicto.
# "mover_fecha" se ejecuta llamando de nuevo a
# PATCH /subtareas/{id}/reprogramar con otra fecha; "reducir_horas" usa
# PATCH /subtareas/{id}/resolver. El cálculo es el mismo en ambos casos.
ESTRATEGIAS_RESOLUCION = ["mover_fecha", "reducir_horas"]


# ============================================================
# FECHAS Y ESTADOS
# ============================================================

def obtener_fecha_hoy() -> date:
    """Devuelve la fecha actual usando la zona horaria de Colombia."""
    return datetime.now(ZONA_HORARIA_EVENTHUB).date()


def normalizar_estado(estado: Any) -> str:
    if estado is None:
        return ""
    return str(estado).strip().lower()


def es_completada(estado: Any) -> bool:
    return normalizar_estado(estado) in ESTADOS_COMPLETADOS


def extraer_fecha(valor: Any) -> Optional[date]:
    """Lee el campo de fecha objetivo sin asumir el tipo de la columna.

    `dia_objetivo` puede venir como `date`, como texto ISO o como
    marca de tiempo; en los tres casos los primeros 10 caracteres son
    la fecha (YYYY-MM-DD), igual que hace la vista /hoy.
    """
    if valor is None:
        return None

    if isinstance(valor, datetime):
        return valor.date()

    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()

    if not texto:
        return None

    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        return None


def horas_a_float(valor: Any) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def validar_fecha_objetivo(fecha: date, hoy: Optional[date] = None) -> date:
    """Valida la fecha objetivo de una reprogramacion.

    Levanta ValueError con el mensaje funcional del backlog cuando la
    fecha no existe o ya paso. La ruta convierte el error en HTTP 400.
    """
    referencia = hoy or obtener_fecha_hoy()

    if not isinstance(fecha, date) or isinstance(fecha, datetime):
        raise ValueError(MENSAJE_FECHA_INVALIDA)

    if fecha < referencia:
        raise ValueError(MENSAJE_FECHA_INVALIDA)

    return fecha


# ============================================================
# LIMITE DIARIO POR ORGANIZADOR (BE-02)
# ============================================================

def normalizar_horas_dia(valor: Any) -> int:
    """Devuelve un limite diario valido o el valor por defecto de negocio."""
    try:
        horas = int(valor)
    except (TypeError, ValueError):
        return LIMITE_HORAS_DIA_POR_DEFECTO

    if horas < LIMITE_HORAS_DIA_MINIMO or horas > LIMITE_HORAS_DIA_MAXIMO:
        logger.warning(
            "Limite diario fuera de rango (%s). Se usa el valor por defecto.",
            valor,
        )
        return LIMITE_HORAS_DIA_POR_DEFECTO

    return horas


def obtener_horas_dia(usuario_id: str) -> int:
    """Limite diario del organizador autenticado.

    Se consulta siempre por `usuario_id`: nunca hay un valor global
    compartido. Si la configuracion no existe todavia se aplica el
    default de negocio (6 horas/dia).
    """
    try:
        response = (
            supabase
            .table("usuario_configuracion")
            .select("horas_dia")
            .eq("usuario_id", usuario_id)
            .maybe_single()
            .execute()
        )

        if not response.data:
            return LIMITE_HORAS_DIA_POR_DEFECTO

        return normalizar_horas_dia(response.data.get("horas_dia"))

    except Exception as error:
        logger.warning(
            "No fue posible leer el limite diario de %s: %r",
            usuario_id,
            error,
        )
        return LIMITE_HORAS_DIA_POR_DEFECTO


# ============================================================
# CONSULTA DE SUBTAREAS
# ============================================================

def obtener_subtareas_del_usuario(usuario_id: str) -> list[dict]:
    """Subtareas del organizador, incluyendo solo las suyas."""
    try:
        response = (
            supabase
            .table("subtareas")
            .select("id, evento_id, dia_objetivo, horas_estimadas, estado")
            .eq("usuario_id", usuario_id)
            .execute()
        )

        return response.data or []

    except Exception as error:
        logger.exception(
            "No fue posible consultar las subtareas de %s", usuario_id
        )
        raise


def obtener_subtarea_del_usuario(
    subtarea_id: str,
    usuario_id: str,
) -> Optional[dict]:
    """Subtarea solo si pertenece al organizador autenticado.

    Devuelve None cuando no existe o pertenece a otro usuario: la
    respuesta para ambos casos es identica (404) para no filtrar
    informacion de otros organizadores.
    """
    response = (
        supabase
        .table("subtareas")
        .select("*")
        .eq("id", subtarea_id)
        .eq("usuario_id", usuario_id)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


# ============================================================
# CALCULO DE HORAS (BE-03)
# ============================================================

def total_horas(subtareas: Iterable[dict]) -> float:
    """Suma las horas estimadas de una lista de subtareas."""
    total = sum(horas_a_float(item.get("horas_estimadas")) for item in subtareas)
    return round(total, PRECISION_HORAS)


def calcular_horas_dia(
    usuario_id: str,
    fecha: date,
    excluir_subtarea_id: Optional[str] = None,
    subtareas: Optional[list[dict]] = None,
) -> float:
    """Horas planificadas del organizador en una fecha.

    Solo cuenta subtareas del propio usuario con `dia_objetivo` igual a
    la fecha indicada y que no estan completadas (misma regla de negocio
    que usa la vista /hoy).

    `excluir_subtarea_id` permite quitar la subtarea que se esta
    reprogramando para no contarla dos veces cuando el origen y el
    destino coinciden.
    """
    registros = (
        subtareas
        if subtareas is not None
        else obtener_subtareas_del_usuario(usuario_id)
    )

    total = 0.0

    for subtarea in registros:
        if excluir_subtarea_id is not None:
            if str(subtarea.get("id")) == str(excluir_subtarea_id):
                continue

        if es_completada(subtarea.get("estado")):
            continue

        if extraer_fecha(subtarea.get("dia_objetivo")) != fecha:
            continue

        total += horas_a_float(subtarea.get("horas_estimadas"))

    return round(total, PRECISION_HORAS)


def construir_resumen_sobrecarga(
    dia: str,
    horas_planificadas: float,
    limite_horas_dia: int,
    horas_previas_dia: float = 0.0,
    horas_subtarea: float = 0.0,
) -> dict:
    """Respuesta estructurada de conflicto.

    Los valores están redondeados a dos decimales y `conflicto` es True
    solo cuando las horas planificadas superan el límite (6h exactas no
    exceden).
    """
    horas = round(horas_planificadas, PRECISION_HORAS)
    limite = int(limite_horas_dia)
    conflicto = horas > limite
    exceso = round(max(0.0, horas - limite), PRECISION_HORAS)

    return {
        "conflicto": conflicto,
        "horas_planificadas": horas,
        "limite_horas_dia": limite,
        "exceso_horas": exceso,
        "dia": dia,
        "horas_previas_dia": round(horas_previas_dia, PRECISION_HORAS),
        "horas_subtarea": round(horas_subtarea, PRECISION_HORAS),
    }


def mensaje_sobrecarga(horas_planificadas: float, limite_horas_dia: int) -> str:
    """Mensaje funcional: "Quedarías con 7h ... (límite 6h)"."""
    horas = f"{round(horas_planificadas, PRECISION_HORAS):g}"
    limite = f"{int(limite_horas_dia):g}"

    return MENSAJE_CONFLICTO_SOBRECARGA.format(horas=horas, limite=limite)


def evaluar_sobrecarga(
    usuario_id: str,
    fecha: date,
    horas: float,
    excluir_subtarea_id: Optional[str] = None,
    subtareas: Optional[list[dict]] = None,
) -> dict:
    """Simula la reprogramacion de `horas` horas en `fecha`.

    total_resultante = horas actuales del dia destino (sin la subtarea que
    se mueve) + horas de la subtarea reprogramada.

    Regla del limite: 6 horas exactas NO exceden; 6.1 horas SI exceden.
    """
    limite = obtener_horas_dia(usuario_id)
    horas_subtarea = horas_a_float(horas)

    horas_previas = calcular_horas_dia(
        usuario_id,
        fecha,
        excluir_subtarea_id=excluir_subtarea_id,
        subtareas=subtareas,
    )

    return construir_resumen_sobrecarga(
        dia=fecha.isoformat(),
        horas_planificadas=horas_previas + horas_subtarea,
        limite_horas_dia=limite,
        horas_previas_dia=horas_previas,
        horas_subtarea=horas_subtarea,
    )


def evaluar_dia(
    usuario_id: str,
    fecha: date,
    excluir_subtarea_id: Optional[str] = None,
    subtareas: Optional[list[dict]] = None,
    limite_horas_dia: Optional[int] = None,
) -> dict:
    """Resumen de sobrecarga de un dia tal como esta, sin simulaciones."""
    total = calcular_horas_dia(
        usuario_id,
        fecha,
        excluir_subtarea_id=excluir_subtarea_id,
        subtareas=subtareas,
    )

    return construir_resumen_sobrecarga(
        dia=fecha.isoformat(),
        horas_planificadas=total,
        limite_horas_dia=(
            limite_horas_dia
            if limite_horas_dia is not None
            else obtener_horas_dia(usuario_id)
        ),
        horas_previas_dia=total,
    )