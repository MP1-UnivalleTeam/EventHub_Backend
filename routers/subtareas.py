import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from database import supabase
from modelos import Subtarea, SubtareaActualizarParcial


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subtareas", tags=["Subtareas"])


@router.get("/")
def obtener_subtareas(evento_id: Optional[str] = None):
    try:
        query = supabase.table("subtareas").select("*")

        if evento_id:
            query = query.eq("evento_id", evento_id)

        response = query.execute()

        return response.data

    except Exception as error:
        logger.exception("Error al consultar subtareas")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al consultar subtareas."
        ) from error


@router.post("/", status_code=status.HTTP_201_CREATED)
def crear_subtarea(subtarea: Subtarea):
    try:
        datos = subtarea.model_dump(exclude_none=True)

        response = (
            supabase
            .table("subtareas")
            .insert(datos)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No se pudo crear la subtarea."
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as error:
        logger.exception("Error real al crear subtarea")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error)
        ) from error


@router.put("/{subtarea_id}")
def actualizar_subtarea(subtarea_id: str, subtarea: Subtarea):
    try:
        datos = subtarea.model_dump(exclude_none=True)

        response = (
            supabase
            .table("subtareas")
            .update(datos)
            .eq("id", subtarea_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subtarea no encontrada."
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as error:
        logger.exception("Error al actualizar subtarea")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al actualizar subtarea."
        ) from error


@router.patch("/{subtarea_id}")
def actualizar_subtarea_parcial(
    subtarea_id: str,
    subtarea: SubtareaActualizarParcial
):
    try:
        datos = subtarea.model_dump(exclude_none=True)

        response = (
            supabase
            .table("subtareas")
            .update(datos)
            .eq("id", subtarea_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subtarea no encontrada."
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as error:
        logger.exception("Error al actualizar parcialmente la subtarea")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al actualizar subtarea."
        ) from error


@router.delete("/{subtarea_id}")
def eliminar_subtarea(subtarea_id: str):
    try:
        response = (
            supabase
            .table("subtareas")
            .delete()
            .eq("id", subtarea_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subtarea no encontrada."
            )

        return {
            "message": "Subtarea eliminada correctamente."
        }

    except HTTPException:
        raise

    except Exception as error:
        logger.exception("Error al eliminar subtarea")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al eliminar subtarea."
        ) from error