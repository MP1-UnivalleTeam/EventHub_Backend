from fastapi import APIRouter, HTTPException
from database import supabase
from modelos import Evento

router = APIRouter(prefix="/eventos", tags=["Eventos"])

@router.get("/")
def obtener_eventos():
    response = supabase.table("eventos").select("*").execute()
    return response.data

@router.post("/")
def crear_evento(evento: Evento):
    response = supabase.table("eventos").insert(evento.dict()).execute()
    return {"mensaje": "Evento creado exitosamente", "data": response.data}