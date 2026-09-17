from pydantic import BaseModel
from typing import Optional

class Evento(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    fecha: str

class Subtarea(BaseModel):
    nombre: str
    completada: bool = False
    evento_id: int