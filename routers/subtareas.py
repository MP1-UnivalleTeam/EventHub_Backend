import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from auth import get_current_user
from database import supabase
from modelos import (
    ConflictoSobreCargaResponse,
    MensajeErrorResponse,
    ReprogramarSubtareaRequest,
    ResolverConflictoSubtareaRequest,
    ResolverConflictoResponse,
    Subtarea,
    SubtareaActualizarParcial,
    SubtareaReprogramadaResponse,
)
from servicios import (
    ESTRATEGIAS_RESOLUCION,
    MENSAJE_CONFLICTO_RESUELTO,
    MENSAJE_REDUCCION_INSUFICIENTE,
    MENSAJE_REPROGRAMADA,
    evaluar_dia,
    evaluar_sobrecarga,
    extraer_fecha,
    horas_a_float,
    mensaje_sobrecarga,
    obtener_fecha_hoy,
    obtener_subtarea_del_usuario,
    obtener_subtareas_del_usuario,
    validar_fecha_objetivo,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subtareas", tags=["Subtareas"])


def _fecha_valida_o_error(fecha: date) -> date:
    """Valida la fecha objetivo y devuelve HTTP 400 si no es válida."""
    try:
        return validar_fecha_objetivo(fecha)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


def _subtarea_del_usuario_o_404(
    subtarea_id: str,
    usuario_id: str,
) -> dict:
    subtarea = obtener_subtarea_del_usuario(subtarea_id, usuario_id)

    if not subtarea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subtarea no encontrada.",
        )

    return subtarea


def _actualizar_subtarea_del_usuario(
    subtarea_id: str,
    usuario_id: str,
    cambios: dict,
) -> dict:
    """Persiste los cambios solo sobre subtareas del usuario autenticado."""
    response = (
        supabase
        .table("subtareas")
        .update(cambios)
        .eq("id", subtarea_id)
        .eq("usuario_id", usuario_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subtarea no encontrada.",
        )

    return response.data[0]


def verificar_evento_del_usuario(evento_id: str, usuario_id: str) -> None:
    response = (
        supabase
        .table("eventos")
        .select("id")
        .eq("id", evento_id)
        .eq("usuario_id", usuario_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )


@router.get("/")
def obtener_subtareas(
    evento_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    try:
        query = (
            supabase
            .table("subtareas")
            .select("*")
            .eq("usuario_id", current_user["id"])
        )

        if evento_id:
            # Evita que un organizador consulte subtareas de un evento ajeno.
            verificar_evento_del_usuario(evento_id, current_user["id"])
            query = query.eq("evento_id", evento_id)

        response = query.execute()
        return response.data

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error al consultar subtareas")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al consultar subtareas.",
        ) from error


@router.post("/", status_code=status.HTTP_201_CREATED)
def crear_subtarea(
    subtarea: Subtarea,
    current_user: dict = Depends(get_current_user),
):
    try:
        usuario_id = current_user["id"]

        verificar_evento_del_usuario(
            subtarea.evento_id,
            usuario_id
        )

        datos = {
            "evento_id": subtarea.evento_id,
            "titulo": subtarea.titulo,
            "dia_objetivo": subtarea.dia_objetivo.isoformat(),
            "horas_estimadas": subtarea.horas_estimadas,
            "estado": subtarea.estado,
            "notas": subtarea.notas,
            "usuario_id": usuario_id,
        }

        response = (
            supabase
            .table("subtareas")
            .insert(datos)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No se pudo crear la subtarea.",
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as error:
        logger.exception("Error real al crear subtarea")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al crear subtarea.",
        ) from error


@router.put("/{subtarea_id}")
def actualizar_subtarea(
    subtarea_id: str,
    subtarea: Subtarea,
    current_user: dict = Depends(get_current_user),
):
    try:
        usuario_id = current_user["id"]
        verificar_evento_del_usuario(subtarea.evento_id, usuario_id)

        # La fecha objetivo no puede quedar en el pasado.
        _fecha_valida_o_error(subtarea.dia_objetivo)

        datos = subtarea.model_dump(exclude_none=True)
        datos["dia_objetivo"] = subtarea.dia_objetivo.isoformat()

        # Si el cliente no envía `estado`, no se toca: el valor por
        # defecto del esquema ("Pendiente") pisaba el estado real de
        # ejecución de la gestión (hecha/pospuesta) en cada edición.
        if "estado" not in subtarea.model_fields_set:
            datos.pop("estado", None)

        response = (
            supabase
            .table("subtareas")
            .update(datos)
            .eq("id", subtarea_id)
            .eq("usuario_id", usuario_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subtarea no encontrada.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error al actualizar subtarea")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al actualizar subtarea.",
        ) from error


@router.patch("/{subtarea_id}")
def actualizar_subtarea_parcial(
    subtarea_id: str,
    subtarea: SubtareaActualizarParcial,
    current_user: dict = Depends(get_current_user),
):
    try:
        usuario_id = current_user["id"]
        datos = subtarea.model_dump(exclude_none=True)

        if "dia_objetivo" in datos and subtarea.dia_objetivo is not None:
            # La fecha objetivo no puede quedar en el pasado.
            _fecha_valida_o_error(subtarea.dia_objetivo)
            datos["dia_objetivo"] = subtarea.dia_objetivo.isoformat()

        if "evento_id" in datos:
            verificar_evento_del_usuario(datos["evento_id"], usuario_id)

        # La subtarea que se modifica también debe pertenecer al usuario.
        response = (
            supabase
            .table("subtareas")
            .update(datos)
            .eq("id", subtarea_id)
            .eq("usuario_id", usuario_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subtarea no encontrada.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error al actualizar parcialmente la subtarea")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al actualizar subtarea.",
        ) from error


@router.delete("/{subtarea_id}")
def eliminar_subtarea(
    subtarea_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        response = (
            supabase
            .table("subtareas")
            .delete()
            .eq("id", subtarea_id)
            .eq("usuario_id", current_user["id"])
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subtarea no encontrada.",
            )

        return {"message": "Subtarea eliminada correctamente."}

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error al eliminar subtarea")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al eliminar subtarea.",
        ) from error


# ============================================================
# BE-01 — REPROGRAMAR SUBTAREA
# ============================================================

@router.patch(
    "/{subtarea_id}/reprogramar",
    response_model=SubtareaReprogramadaResponse,
    responses={
        400: {
            "model": MensajeErrorResponse,
            "description": (
                "La fecha seleccionada no es válida o es anterior al día de hoy."
            ),
        },
        401: {
            "model": MensajeErrorResponse,
            "description": "Falta el token de autenticación.",
        },
        404: {
            "model": MensajeErrorResponse,
            "description": "Subtarea no encontrada para el usuario autenticado.",
        },
        409: {
            "model": ConflictoSobreCargaResponse,
            "description": (
                "La reprogramación dejaría el día por encima del límite "
                "diario. La subtarea NO se modificó. Para resolver, elige "
                "otra fecha en `estrategias_disponibles` y vuelve a "
                "llamar este endpoint, o usa "
                "PATCH /subtareas/{id}/resolver para reducir las horas."
            ),
        },
        502: {
            "model": MensajeErrorResponse,
            "description": "Error de la base de datos.",
        },
    },
)
def reprogramar_subtarea(
    subtarea_id: str,
    reprogramacion: ReprogramarSubtareaRequest,
    current_user: dict = Depends(get_current_user),
):
    """Cambia la fecha objetivo de una subtarea validando la sobrecarga.

    Flujo: autenticar -> localizar subtarea -> comprobar ownership ->
    validar fecha -> calcular horas del día destino -> obtener el límite
    del usuario -> si no hay conflicto, persistir; si hay conflicto,
    responder 409 sin tocar la base de datos.
    """
    try:
        usuario_id = current_user["id"]

        subtarea = _subtarea_del_usuario_o_404(subtarea_id, usuario_id)

        # 1. Validar la fecha nueva.
        fecha_destino = _fecha_valida_o_error(reprogramacion.dia_objetivo)

        # 2. Horas efectivas: la nueva si viene en el body, si no la actual.
        horas = horas_a_float(
            reprogramacion.horas_estimadas
            if reprogramacion.horas_estimadas is not None
            else subtarea.get("horas_estimadas")
        )

        fecha_origen = extraer_fecha(subtarea.get("dia_objetivo"))

        # 3. Recalcular la carga del día destino y del día origen usando
        #    el límite configurado por este organizador.
        registros = obtener_subtareas_del_usuario(usuario_id)
        resumen = evaluar_sobrecarga(
            usuario_id,
            fecha_destino,
            horas,
            excluir_subtarea_id=subtarea_id,
            subtareas=registros,
        )

        resumen_origen = None
        if fecha_origen is not None and fecha_origen != fecha_destino:
            resumen_origen = evaluar_dia(
                usuario_id,
                fecha_origen,
                excluir_subtarea_id=subtarea_id,
                subtareas=registros,
                limite_horas_dia=resumen["limite_horas_dia"],
            )

        # 4. Conflicto: se informa y NO se persiste nada.
        if resumen["conflicto"]:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": mensaje_sobrecarga(
                        resumen["horas_planificadas"],
                        resumen["limite_horas_dia"],
                    ),
                    **resumen,
                    "subtarea": subtarea,
                    "estrategias_disponibles": list(ESTRATEGIAS_RESOLUCION),
                },
            )

        # 5. Sin conflicto: persistir la nueva fecha.
        cambios = {
            "dia_objetivo": fecha_destino.isoformat(),
        }

        if reprogramacion.horas_estimadas is not None:
            cambios["horas_estimadas"] = reprogramacion.horas_estimadas

        if reprogramacion.motivo_posposicion is not None:
            cambios["motivo_posposicion"] = reprogramacion.motivo_posposicion

        subtarea_actualizada = _actualizar_subtarea_del_usuario(
            subtarea_id,
            usuario_id,
            cambios,
        )

        return {
            "message": MENSAJE_REPROGRAMADA,
            "subtarea": subtarea_actualizada,
            "resumen": resumen,
            "resumen_origen": resumen_origen,
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error al reprogramar la subtarea")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al reprogramar la subtarea.",
        ) from error


# ============================================================
# BE-04 — RESOLUCIÓN DE CONFLICTO
# ============================================================

@router.patch(
    "/{subtarea_id}/resolver",
    response_model=ResolverConflictoResponse,
    responses={
        400: {
            "model": MensajeErrorResponse,
            "description": "Horas estimadas inválidas (≤ 0 o no numéricas).",
        },
        401: {
            "model": MensajeErrorResponse,
            "description": "Falta el token de autenticación.",
        },
        404: {
            "model": MensajeErrorResponse,
            "description": "Subtarea no encontrada para el usuario autenticado.",
        },
        422: {
            "model": MensajeErrorResponse,
            "description": (
                "Falta la estrategia o las horas estimadas, o la estrategia "
                "no es 'reducir_horas'."
            ),
        },
        502: {
            "model": MensajeErrorResponse,
            "description": "Error de la base de datos.",
        },
    },
)
def resolver_conflicto(
    subtarea_id: str,
    resolucion: ResolverConflictoSubtareaRequest,
    current_user: dict = Depends(get_current_user),
):
    """Resuelve un conflicto reduciendo las horas estimadas (US-08 E2).

    Mover la gestión a otro día no se hace aquí: la única operación que
    cambia `dia_objetivo` es `PATCH /subtareas/{id}/reprogramar` (US-06),
    que devuelve 409 sin persistir cuando la fecha destino seguiría
    sobrecargada.

    Reduce la estimación, persiste el cambio y recalcula la carga del
    día. Si la reducción no alcanza, la estimación queda guardada y el
    conflicto se mantiene activo.
    """
    try:
        usuario_id = current_user["id"]

        subtarea = _subtarea_del_usuario_o_404(subtarea_id, usuario_id)

        fecha_dia = (
            extraer_fecha(subtarea.get("dia_objetivo"))
            or obtener_fecha_hoy()
        )

        cambios = {
            "horas_estimadas": horas_a_float(resolucion.horas_estimadas),
        }

        if resolucion.motivo_posposicion is not None:
            cambios["motivo_posposicion"] = resolucion.motivo_posposicion

        registros = obtener_subtareas_del_usuario(usuario_id)

        resumen = evaluar_sobrecarga(
            usuario_id,
            fecha_dia,
            cambios["horas_estimadas"],
            excluir_subtarea_id=subtarea_id,
            subtareas=registros,
        )

        subtarea_actualizada = _actualizar_subtarea_del_usuario(
            subtarea_id,
            usuario_id,
            cambios,
        )

        return {
            "message": (
                MENSAJE_REDUCCION_INSUFICIENTE
                if resumen["conflicto"]
                else MENSAJE_CONFLICTO_RESUELTO
            ),
            "conflicto_resuelto": not resumen["conflicto"],
            "subtarea": subtarea_actualizada,
            "resumen": resumen,
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error al resolver el conflicto de la subtarea")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al resolver el conflicto.",
        ) from error
