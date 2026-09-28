import logging
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import get_current_user
from database import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hoy", tags=["Hoy"])

ZONA_HORARIA_EVENTHUB = ZoneInfo("America/Bogota")
ESTADOS_COMPLETADOS = {"completada", "completado", "hecho", "hecha"}


def obtener_fecha_hoy() -> date:
    """Devuelve la fecha actual usando la zona horaria de Colombia."""
    from datetime import datetime

    return datetime.now(ZONA_HORARIA_EVENTHUB).date()


def normalizar_estado(estado: Any) -> str:
    if estado is None:
        return ""
    return str(estado).strip().lower()


def es_completada(estado: Any) -> bool:
    return normalizar_estado(estado) in ESTADOS_COMPLETADOS


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


def preparar_hoy(subtareas: list[dict], hoy: date) -> dict:
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

    return {
        "fecha": hoy.isoformat(),
        "resumen": {
            "vencidas": len(vencidas),
            "urgentes": len(urgentes),
            "proximas": len(proximas),
            "total": len(vencidas) + len(urgentes) + len(proximas),
        },
        "vencidas": vencidas,
        "urgentes": urgentes,
        "proximas": proximas,
    }


@router.get("")
@router.get("/")
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
            return preparar_hoy([], hoy)

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
                return preparar_hoy([], hoy)

            consulta = consulta.eq("estado", estado_filtrado)

        response = consulta.execute()

        subtareas = response.data or []
        return preparar_hoy(subtareas, hoy)

    except Exception as error:
        logger.exception("No fue posible construir la vista Hoy")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible obtener las gestiones de hoy.",
        ) from error
