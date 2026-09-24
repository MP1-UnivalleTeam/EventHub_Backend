import logging
from fastapi import APIRouter, HTTPException, status
from database import supabase
from modelos import Evento, EventoActualizarParcial

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eventos", tags=["Eventos"])

@router.get("/")
def obtener_eventos():
    try:
        response = supabase.table("eventos").select("*").order("creado_en", desc=True).execute()
        return response.data
    except Exception as error:
        logger.exception("No fue posible consultar eventos")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible consultar los eventos.") from error

@router.get("/{evento_id}")
def obtener_evento(evento_id: str):
    try:
        response = supabase.table("eventos").select("*").eq("id", evento_id.strip()).execute()
        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento no encontrado")
        return response.data[0]
    except Exception as error:
        logger.exception("No fue posible consultar el evento")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible consultar el evento.") from error

@router.post("/", status_code=status.HTTP_201_CREATED)
def crear_evento(evento: Evento):
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

@router.put("/{evento_id}")
def actualizar_evento(evento_id: str, evento: Evento):
    try:
        datos_evento = evento.model_dump()
        datos_evento["fecha"] = evento.fecha.isoformat()
        
        response = supabase.table("eventos").update(datos_evento).eq("id", evento_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento no encontrado.")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("No fue posible actualizar el evento")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error al actualizar el evento.") from error

@router.patch("/{evento_id}")
def actualizar_parcial_evento(evento_id: str, evento: EventoActualizarParcial):
    try:
        datos = {k: v for k, v in evento.model_dump().items() if v is not None}
        if "fecha" in datos and datos["fecha"]:
            datos["fecha"] = datos["fecha"].isoformat()
            
        response = supabase.table("eventos").update(datos).eq("id", evento_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento no encontrado.")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("No fue posible actualizar parcialmente el evento")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error al actualizar parcialmente el evento.") from error

@router.delete("/{evento_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_evento(evento_id: str):
    try:
        # Elimina primero las subtareas asociadas para mantener la integridad referencial
        supabase.table("subtareas").delete().eq("evento_id", evento_id).execute()
        response = supabase.table("eventos").delete().eq("id", evento_id).execute()
        return {"ok": True}
    except Exception as error:
        logger.exception("No fue posible eliminar el evento")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error al eliminar el evento.") from error