from fastapi import APIRouter, HTTPException
from database import supabase
from modelos import Subtarea

router = APIRouter(prefix="/subtareas", tags=["Subtareas"])

@router.get("/")
def obtener_subtareas():
    response = supabase.table("subtareas").select("*").execute()
    return response.data

@router.post("/")
def crear_subtarea(subtarea: Subtarea):
    response = supabase.table("subtareas").insert(subtarea.dict()).execute()
    return {"mensaje": "Subtarea creada exitosamente", "data": response.data}