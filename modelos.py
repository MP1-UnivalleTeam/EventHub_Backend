from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, StrictInt, field_validator


class Evento(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    fecha: date
    horas: float = Field(..., gt=0, le=24)
    usuario_responsable: str = Field(..., min_length=1, max_length=150)

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

    @field_validator("usuario_responsable")
    def limpiar_usuario_responsable(cls, value: str) -> str:
        usuario = value.strip()
        if not usuario:
            raise ValueError("El usuario responsable es requerido.")
        return usuario


class EventoActualizarParcial(BaseModel):
    titulo: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=120
    )

    descripcion: Optional[str] = Field(
        default=None,
        max_length=500
    )

    fecha: Optional[date] = None

    horas: Optional[float] = Field(
        default=None,
        gt=0,
        le=24
    )

    usuario_responsable: Optional[str] = Field(
        default=None,
        max_length=150
    )

    @field_validator("titulo")
    def titulo_no_vacio(
        cls, value: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None

        titulo = value.strip()

        if not titulo:
            raise ValueError("El título no puede estar vacío.")

        return titulo

    @field_validator("descripcion")
    def limpiar_descripcion(
        cls, value: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None

        return value.strip() or None

    @field_validator("usuario_responsable")
    def limpiar_usuario_responsable(
        cls, value: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None

        return value.strip() or None


class Subtarea(BaseModel):
    evento_id: str  # UUID en formato string
    titulo: str = Field(..., min_length=2, max_length=120)
    dia_objetivo: date
    horas_estimadas: float = Field(..., gt=0)
    estado: Optional[str] = Field(default="Pendiente")
    notas: Optional[str] = Field(default=None, max_length=300)

    @field_validator("titulo")
    def subtitulo_no_vacio(cls, value: str) -> str:
        titulo = value.strip()

        if not titulo:
            raise ValueError(
                "El título de la subtarea no puede estar vacío."
            )

        return titulo


class SubtareaActualizarParcial(BaseModel):
    evento_id: Optional[str] = None

    titulo: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=120
    )

    dia_objetivo: Optional[date] = None

    horas_estimadas: Optional[float] = Field(
        default=None,
        gt=0
    )

    estado: Optional[str] = None

    notas: Optional[str] = Field(
        default=None,
        max_length=300
    )

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1)

    @field_validator("email")
    def limpiar_email(cls, value: str) -> str:
        return value.strip().lower()

class ConfiguracionUsuarioRequest(BaseModel):
    horas_dia: StrictInt = Field(..., ge=1, le=16)

    @field_validator("horas_dia")
    def validar_horas_dia(cls, value: int) -> int:
        if isinstance(value, bool):
            raise ValueError("Las horas por día deben ser un número entero entre 1 y 16.")
        return value


class ConfiguracionUsuarioResponse(BaseModel):
    usuario_id: str
    horas_dia: int

