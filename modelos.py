from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Evento(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    fecha: date

    @field_validator("titulo")
    def titulo_no_vacio(cls, value: str) -> str:
        titulo = value.strip()
        if not titulo:
            raise ValueError("El título no puede estar vacío.")
        return titulo

    @field_validator("descripcion")
    def limpiar_descripcion(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None


class Subtarea(BaseModel):
    nombre: str
    completada: bool = False
    evento_id: int
