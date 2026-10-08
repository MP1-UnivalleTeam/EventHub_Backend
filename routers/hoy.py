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
    normalizar_estado,
    obtener_fecha_hoy,
    obtener_horas_dia,
    total_horas,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hoy", tags=["Hoy"])


def clasificar_subtarea(subtarea: dict, hoy: date) -> str:
    fecha_objetivo = date.fromisoformat(str(subtarea["dia_objetivo"])[:10])

    if fecha_objetivo < hoy:
        return "vencida"
    if fecha_objetivo == hoy:
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
        item = {**subtarea, "prioridad": grupo}

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


def _escapar_patron(valor: str) -> str:
    """Escapa los comodines de `ilike` en un valor de filtro."""
    return (
        valor
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


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

        if estado:
            estado_filtrado = estado.strip()

            if normalizar_estado(estado_filtrado) in ESTADOS_COMPLETADOS:
                return preparar_hoy([], hoy, obtener_horas_dia(usuario_id))

            # El estado se compara sin distinguir mayúsculas: las
            # subtareas creadas por la API usan "Pendiente" y las que
            # marca el organizador "pendiente"/"pospuesto". Con `eq` el
            # filtro devolvía vacío y rompía US-05.
            consulta = consulta.ilike(
                "estado",
                _escapar_patron(estado_filtrado),
            )

        response = consulta.execute()

        subtareas = response.data or []
        return preparar_hoy(subtareas, hoy, obtener_horas_dia(usuario_id))

    except Exception as error:
        logger.exception("No fue posible construir la vista Hoy")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible obtener las gestiones de hoy.",
        ) from error
