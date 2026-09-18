import logging

from fastapi import APIRouter, HTTPException, status

from database import supabase
from modelos import Evento

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/eventos", tags=["Eventos"])


@router.get("")
def obtener_eventos():
    """Devuelve los eventos persistidos, del más reciente al más antiguo."""
    try:
        response = supabase.table("eventos").select("*").order("id", desc=True).execute()
        return response.data
    except Exception as error:
        logger.exception("No fue posible consultar eventos")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible consultar los eventos.") from error


@router.post("", status_code=status.HTTP_201_CREATED)
def crear_evento(evento: Evento):
    """Persiste un evento y devuelve el registro creado para actualizar la interfaz."""
    try:
        datos_evento = evento.model_dump()
        datos_evento["fecha"] = evento.fecha.isoformat()
        response = supabase.table("eventos").insert(datos_evento).execute()
        if not response.data:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="La base de datos no devolvió el evento creado.")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("No fue posible crear el evento")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible guardar el evento.") from error
