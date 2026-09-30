import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user
from database import supabase
from modelos import Subtarea, SubtareaActualizarParcial

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subtareas", tags=["Subtareas"])


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
        verificar_evento_del_usuario(subtarea.evento_id, usuario_id)

        datos = subtarea.model_dump(
                mode="json",
                exclude_none=True
            )


        # Nunca se acepta usuario_id desde el frontend.
        datos["usuario_id"] = usuario_id

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

        datos = subtarea.model_dump(
                mode="json",
                exclude_none=True
            )

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
        datos = subtarea.model_dump(
            mode="json",
            exclude_none=True
        )

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
