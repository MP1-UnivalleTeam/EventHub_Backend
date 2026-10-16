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
    MENSAJE_REPROGRAMADA,
    evaluar_dia,
    evaluar_sobrecarga,
    es_completada,
    extraer_fecha,
    horas_a_float,
    mensaje_sobrecarga,
    obtener_fecha_hoy,
    obtener_subtarea_del_usuario,
    obtener_subtareas_del_usuario,
    sincronizar_estados_vencimiento,
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


def _validar_fecha_del_evento_o_error(fecha: date, evento: dict) -> None:
    fecha_evento = extraer_fecha(evento.get("fecha"))
    if fecha_evento is not None and fecha > fecha_evento:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha objetivo no puede ser posterior a la fecha del evento.",
        )


def _respuesta_conflicto_planificacion(
    usuario_id: str,
    subtarea_id: str | None,
    fecha: date,
    horas: float,
    estado: str | None,
    subtarea_sin_cambios: dict | None = None,
) -> JSONResponse | None:
    if es_completada(estado) or fecha < obtener_fecha_hoy():
        return None

    resumen = evaluar_sobrecarga(
        usuario_id,
        fecha,
        horas,
        excluir_subtarea_id=subtarea_id,
    )
    if not resumen["conflicto"]:
        return None

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": mensaje_sobrecarga(
                resumen["horas_planificadas"],
                resumen["limite_horas_dia"],
            ),
            **resumen,
            "subtarea": subtarea_sin_cambios,
            "estrategias_disponibles": list(ESTRATEGIAS_RESOLUCION),
        },
    )


def _cambia_planificacion(
    subtarea: dict,
    fecha: date,
    horas: float,
    estado: str | None,
) -> bool:
    fecha_actual = extraer_fecha(subtarea.get("dia_objetivo"))
    horas_actuales = round(
        horas_a_float(subtarea.get("horas_estimadas")),
        2,
    )
    return (
        fecha_actual != fecha
        or horas_actuales != round(horas, 2)
        or es_completada(subtarea.get("estado")) != es_completada(estado)
    )


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

    return sincronizar_estados_vencimiento(
        [subtarea],
        usuario_id,
        obtener_fecha_hoy(),
    )[0]


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

    return sincronizar_estados_vencimiento(
        [response.data[0]],
        usuario_id,
        obtener_fecha_hoy(),
    )[0]


def verificar_evento_del_usuario(evento_id: str, usuario_id: str) -> dict:
    response = (
        supabase
        .table("eventos")
        .select("id, fecha")
        .eq("id", evento_id)
        .eq("usuario_id", usuario_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )
    return response.data[0]


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
        return sincronizar_estados_vencimiento(
            response.data or [],
            current_user["id"],
            obtener_fecha_hoy(),
        )

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

        evento = verificar_evento_del_usuario(
            subtarea.evento_id,
            usuario_id
        )
        _fecha_valida_o_error(subtarea.dia_objetivo)
        _validar_fecha_del_evento_o_error(subtarea.dia_objetivo, evento)

        conflicto = _respuesta_conflicto_planificacion(
            usuario_id,
            None,
            subtarea.dia_objetivo,
            subtarea.horas_estimadas,
            subtarea.estado,
        )
        if conflicto:
            return conflicto

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

        return sincronizar_estados_vencimiento(
            [response.data[0]],
            usuario_id,
            obtener_fecha_hoy(),
        )[0]

    except HTTPException:
        raise

    except Exception as error:
        logger.exception("Error real al crear subtarea")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al crear subtarea.",
        ) from error


@router.put(
    "/{subtarea_id}",
    responses={
        400: {"model": MensajeErrorResponse},
        401: {"model": MensajeErrorResponse},
        404: {"model": MensajeErrorResponse},
        409: {
            "model": ConflictoSobreCargaResponse,
            "description": "La actualización excedería el límite diario y no se guardó.",
        },
        422: {"model": MensajeErrorResponse},
        502: {"model": MensajeErrorResponse},
    },
)
def actualizar_subtarea(
    subtarea_id: str,
    subtarea: Subtarea,
    current_user: dict = Depends(get_current_user),
):
    try:
        usuario_id = current_user["id"]
        existente = _subtarea_del_usuario_o_404(subtarea_id, usuario_id)
        evento = verificar_evento_del_usuario(subtarea.evento_id, usuario_id)

        # La fecha objetivo no puede quedar en el pasado.
        _fecha_valida_o_error(subtarea.dia_objetivo)
        _validar_fecha_del_evento_o_error(subtarea.dia_objetivo, evento)

        datos = subtarea.model_dump(exclude_none=True)
        datos["dia_objetivo"] = subtarea.dia_objetivo.isoformat()

        # Una nota enviada explícitamente se guarda aunque sea nula: es lo que
        # permite limpiarla. Si el cliente no manda `notas`, no se toca.
        if "notas" in subtarea.model_fields_set:
            datos["notas"] = subtarea.notas

        # Si el cliente no envía `estado`, no se toca: el valor por
        # defecto del esquema ("Pendiente") pisaba el estado real de
        # ejecución de la gestión (hecha/pospuesta) en cada edición.
        if "estado" not in subtarea.model_fields_set:
            datos.pop("estado", None)
        estado_resultante = (
            subtarea.estado
            if "estado" in subtarea.model_fields_set
            else existente.get("estado")
        )
        if _cambia_planificacion(
            existente,
            subtarea.dia_objetivo,
            subtarea.horas_estimadas,
            estado_resultante,
        ):
            conflicto = _respuesta_conflicto_planificacion(
                usuario_id,
                subtarea_id,
                subtarea.dia_objetivo,
                subtarea.horas_estimadas,
                estado_resultante,
                existente,
            )
            if conflicto:
                return conflicto

        return _actualizar_subtarea_del_usuario(
            subtarea_id,
            usuario_id,
            datos,
        )

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error al actualizar subtarea")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al actualizar subtarea.",
        ) from error


@router.patch(
    "/{subtarea_id}",
    responses={
        400: {"model": MensajeErrorResponse},
        401: {"model": MensajeErrorResponse},
        404: {"model": MensajeErrorResponse},
        409: {
            "model": ConflictoSobreCargaResponse,
            "description": "La actualización excedería el límite diario y no se guardó.",
        },
        422: {"model": MensajeErrorResponse},
        502: {"model": MensajeErrorResponse},
    },
)
def actualizar_subtarea_parcial(
    subtarea_id: str,
    subtarea: SubtareaActualizarParcial,
    current_user: dict = Depends(get_current_user),
):
    try:
        usuario_id = current_user["id"]
        existente = _subtarea_del_usuario_o_404(subtarea_id, usuario_id)
        datos = subtarea.model_dump(exclude_none=True)

        if "dia_objetivo" in datos and subtarea.dia_objetivo is not None:
            # La fecha objetivo no puede quedar en el pasado.
            _fecha_valida_o_error(subtarea.dia_objetivo)
            datos["dia_objetivo"] = subtarea.dia_objetivo.isoformat()

        if "notas" in subtarea.model_fields_set:
            datos["notas"] = subtarea.notas

        if not datos:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Debes indicar al menos un campo para actualizar.",
            )

        evento_id = datos.get("evento_id", existente.get("evento_id"))
        evento = verificar_evento_del_usuario(evento_id, usuario_id)
        fecha_resultante = (
            subtarea.dia_objetivo
            if "dia_objetivo" in subtarea.model_fields_set
            else extraer_fecha(existente.get("dia_objetivo"))
        )
        if (
            fecha_resultante is not None
            and (
                "dia_objetivo" in subtarea.model_fields_set
                or "evento_id" in subtarea.model_fields_set
            )
        ):
            _fecha_valida_o_error(fecha_resultante)
            _validar_fecha_del_evento_o_error(fecha_resultante, evento)

        estado_resultante = (
            subtarea.estado
            if "estado" in subtarea.model_fields_set
            and subtarea.estado is not None
            else existente.get("estado")
        )
        horas_resultantes = (
            subtarea.horas_estimadas
            if "horas_estimadas" in subtarea.model_fields_set
            and subtarea.horas_estimadas is not None
            else horas_a_float(existente.get("horas_estimadas"))
        )
        if fecha_resultante is not None and _cambia_planificacion(
            existente,
            fecha_resultante,
            horas_resultantes,
            estado_resultante,
        ):
            conflicto = _respuesta_conflicto_planificacion(
                usuario_id,
                subtarea_id,
                fecha_resultante,
                horas_resultantes,
                estado_resultante,
                existente,
            )
            if conflicto:
                return conflicto

        return _actualizar_subtarea_del_usuario(
            subtarea_id,
            usuario_id,
            datos,
        )

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
        usuario_id = current_user["id"]
        subtarea = (
            supabase
            .table("subtareas")
            .select("id")
            .eq("id", subtarea_id)
            .eq("usuario_id", usuario_id)
            .execute()
        )

        if not subtarea.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subtarea no encontrada.",
            )

        response = (
            supabase
            .table("subtareas")
            .delete()
            .eq("id", subtarea_id)
            .eq("usuario_id", usuario_id)
            .select("id")
            .execute()
        )

        if not response.data:
            logger.error(
                "Supabase no confirmó el borrado de subtarea %s para %s",
                subtarea_id,
                usuario_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No fue posible confirmar la eliminación de la subtarea.",
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

        # La nota es opcional: si no viene con contenido se conserva la que
        # ya tuviera guardada la subtarea.
        if reprogramacion.notas is not None:
            cambios["notas"] = reprogramacion.notas

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
        409: {
            "model": ConflictoSobreCargaResponse,
            "description": (
                "La reducción no alcanza a respetar el límite; no se guarda "
                "el cambio."
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

    Persiste la reducción solo cuando el resultado respeta el límite diario.
    Si no alcanza, responde 409 y deja la subtarea sin cambios.
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

        if resolucion.notas is not None:
            cambios["notas"] = resolucion.notas

        registros = obtener_subtareas_del_usuario(usuario_id)

        resumen = evaluar_sobrecarga(
            usuario_id,
            fecha_dia,
            cambios["horas_estimadas"],
            excluir_subtarea_id=subtarea_id,
            subtareas=registros,
        )

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

        subtarea_actualizada = _actualizar_subtarea_del_usuario(
            subtarea_id,
            usuario_id,
            cambios,
        )

        return {
            "message": MENSAJE_CONFLICTO_RESUELTO,
            "conflicto_resuelto": True,
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
