import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import get_current_user
from database import supabase
from modelos import MensajeErrorResponse

# Estas utilidades viven ahora en `servicios.py` para que /hoy, la
# reprogramación y la resolución de conflictos usen la misma regla de
# sobrecarga. Se importan aquí para conservar los nombres públicos del
# módulo (`routers.hoy.es_completada`, etc.).
from servicios import (  # noqa: F401
    ESTADOS_COMPLETADOS,
    LIMITE_HORAS_DIA_POR_DEFECTO,
    ZONA_HORARIA_EVENTHUB,
    construir_resumen_sobrecarga,
    es_completada,
    es_vencida,
    extraer_fecha,
    nota_canonica,
    normalizar_estado,
    obtener_fecha_hoy,
    obtener_horas_dia,
    sincronizar_estados_vencimiento,
    total_horas,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hoy", tags=["Hoy"])


def clasificar_subtarea(subtarea: dict, hoy: date) -> str:
    """Agrupa la gestión con la regla de vencimiento del dominio.

    No se deduce del estado persistido: una pospuesta cuya fecha
    reprogramada ya pasó también está vencida.
    """
    if es_vencida(subtarea, hoy):
        return "vencida"

    if extraer_fecha(subtarea.get("dia_objetivo")) == hoy:
        return "urgente"

    return "proxima"


def ordenar_grupo(subtareas: list[dict], prioridad: str) -> list[dict]:
    if prioridad == "vencida":
        # Las vencidas más antiguas primero; en empate, menor esfuerzo.
        return sorted(
            subtareas,
            key=lambda item: (
                str(item["dia_objetivo"])[:10],
                float(item.get("horas_estimadas") or 0),
                str(item.get("id") or ""),
            ),
        )

    if prioridad == "urgente":
        # Todas son del día actual; desempate por menor esfuerzo.
        return sorted(
            subtareas,
            key=lambda item: (
                float(item.get("horas_estimadas") or 0),
                str(item.get("id") or ""),
            ),
        )

    # Próximas: fecha más cercana primero; en empate, menor esfuerzo.
    return sorted(
        subtareas,
        key=lambda item: (
            str(item["dia_objetivo"])[:10],
            float(item.get("horas_estimadas") or 0),
            str(item.get("id") or ""),
        ),
    )


def preparar_hoy(
    subtareas: list[dict],
    hoy: date,
    horas_dia: int = LIMITE_HORAS_DIA_POR_DEFECTO,
) -> dict:
    vencidas: list[dict] = []
    urgentes: list[dict] = []
    proximas: list[dict] = []

    for subtarea in subtareas:
        # /hoy solo trabaja con subtareas que tienen fecha objetivo.
        # La fecha es obligatoria al crear una subtarea, pero esta protección
        # evita que un registro antiguo/nulo rompa el endpoint.
        if not subtarea.get("dia_objetivo"):
            continue

        if es_completada(subtarea.get("estado")):
            continue

        grupo = clasificar_subtarea(subtarea, hoy)
        # `nota` es la nota ya resuelta: el cliente no tiene que decidir de qué
        # columna leerla.
        item = {
            **subtarea,
            "prioridad": grupo,
            "nota": nota_canonica(subtarea),
        }

        if grupo == "vencida":
            vencidas.append(item)
        elif grupo == "urgente":
            urgentes.append(item)
        else:
            proximas.append(item)

    vencidas = ordenar_grupo(vencidas, "vencida")
    urgentes = ordenar_grupo(urgentes, "urgente")
    proximas = ordenar_grupo(proximas, "proxima")

    # La sobrecarga se calcula con las gestiones no completadas programadas
    # para hoy. La regla (horas > límite) y el exceso salen de
    # `servicios.construir_resumen_sobrecarga`, la misma fuente de verdad
    # que usan la reprogramación y la resolución de conflictos.
    resumen_sobrecarga = construir_resumen_sobrecarga(
        dia=hoy.isoformat(),
        horas_planificadas=total_horas(urgentes),
        limite_horas_dia=horas_dia,
    )

    return {
        "fecha": hoy.isoformat(),
        "resumen": {
            "vencidas": len(vencidas),
            "urgentes": len(urgentes),
            "proximas": len(proximas),
            "total": len(vencidas) + len(urgentes) + len(proximas),
            "horas_programadas_hoy": resumen_sobrecarga["horas_planificadas"],
            "limite_horas_dia": resumen_sobrecarga["limite_horas_dia"],
            "sobrecarga": resumen_sobrecarga["conflicto"],
            "exceso_horas": resumen_sobrecarga["exceso_horas"],
        },
        "vencidas": vencidas,
        "urgentes": urgentes,
        "proximas": proximas,
    }


@router.get("")
@router.get("/", responses={
    401: {
        "model": MensajeErrorResponse,
        "description": "Falta el token de autenticación.",
    },
    502: {
        "model": MensajeErrorResponse,
        "description": "No fue posible obtener las gestiones de hoy.",
    },
})
def obtener_hoy(
    evento_id: str | None = Query(
        default=None,
        description="Filtra las subtareas por el ID del evento.",
    ),
    estado: str | None = Query(
        default=None,
        description="Filtra las subtareas por estado de gestión.",
    ),
    current_user: dict = Depends(get_current_user),
):
    """Devuelve las subtareas del organizador autenticado agrupadas por prioridad."""
    try:
        usuario_id = current_user["id"]
        hoy = obtener_fecha_hoy()

        eventos_query = (
            supabase
            .table("eventos")
            .select("id")
            .eq("usuario_id", usuario_id)
        )

        if evento_id:
            eventos_query = eventos_query.eq("id", evento_id.strip())

        eventos_response = eventos_query.execute()
        eventos_usuario = eventos_response.data or []
        ids_eventos = [str(item["id"]) for item in eventos_usuario]

        if not ids_eventos:
            return preparar_hoy([], hoy, obtener_horas_dia(usuario_id))

        consulta = (
            supabase
            .table("subtareas")
            .select("*")
            .eq("usuario_id", usuario_id)
            .in_("evento_id", ids_eventos)
        )

        response = consulta.execute()

        subtareas = sincronizar_estados_vencimiento(
            response.data or [],
            usuario_id,
            hoy,
        )

        if estado and estado.strip():
            estado_filtrado = normalizar_estado(estado)
            if estado_filtrado in ESTADOS_COMPLETADOS:
                return preparar_hoy([], hoy, obtener_horas_dia(usuario_id))
            subtareas = [
                subtarea
                for subtarea in subtareas
                if normalizar_estado(subtarea.get("estado")) == estado_filtrado
            ]

        return preparar_hoy(subtareas, hoy, obtener_horas_dia(usuario_id))

    except Exception as error:
        logger.exception("No fue posible construir la vista Hoy")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible obtener las gestiones de hoy.",
        ) from error
