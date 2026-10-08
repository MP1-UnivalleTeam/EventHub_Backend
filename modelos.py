from datetime import date
from typing import Any, Literal, Optional

from pydantic import (
    BaseModel,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


# ============================================================
# MENSAJES DE VALIDACIÓN
#
# El detalle de un 422 es lo que el frontend muestra junto al campo
# (ver `api.js`: concatena `detail[].msg`). Los mensajes técnicos del
# validador no son aptos para UI, así que se validan antes y se
# devuelve el mensaje funcional de la historia.
# ============================================================

MENSAJE_FECHA_INVALIDA = (
    "La fecha no es válida. Usa el formato AAAA-MM-DD."
)

MENSAJE_HORAS_EVENTO = (
    "Las horas del evento deben ser mayores que 0."
)

MENSAJE_HORAS_SUBTAREA = (
    "Las horas estimadas de la gestión deben ser mayores que 0."
)

MENSAJE_HORAS_INVALIDAS = (
    "La nueva estimación de horas no es válida."
)

MENSAJE_ESTRATEGIA_INVALIDA = (
    "La estrategia debe ser 'reducir_horas'. Para mover la gestión a "
    "otro día usa la reprogramación de la fecha objetivo."
)

MENSAJE_RANGO_HORAS_DIA = (
    "El valor debe estar entre 1 y 16 horas diarias."
)

MENSAJE_TITULO_EVENTO = (
    "El título del evento es obligatorio y no puede estar vacío."
)

MENSAJE_TITULO_SUBTAREA = (
    "El nombre de la subtarea es obligatorio y no puede estar vacío."
)

MENSAJE_RESPONSABLE = (
    "Debes indicar el usuario responsable del evento."
)


def _validar_fecha_texto(valor: Any, campo: str) -> Any:
    """Deja pasar fechas ya parseadas y valida textos con formato ISO."""
    if valor is None or isinstance(valor, date):
        if valor is None:
            raise ValueError(f"El campo {campo} es obligatorio.")

        return valor

    if isinstance(valor, str):
        texto = valor.strip()

        if not texto:
            raise ValueError(f"El campo {campo} es obligatorio.")

        try:
            date.fromisoformat(texto[:10])
        except ValueError as error:
            raise ValueError(MENSAJE_FECHA_INVALIDA) from error

    return valor


class Evento(BaseModel):
    titulo: str = Field(..., max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    fecha: date
    horas: float = Field(..., gt=0, le=24)
    usuario_responsable: str = Field(..., min_length=1, max_length=150)

    @field_validator("titulo", mode="before")
    def titulo_no_vacio(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        titulo = value.strip()

        if not titulo:
            raise ValueError(MENSAJE_TITULO_EVENTO)

        return titulo

    @field_validator("descripcion")
    def limpiar_descripcion(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        return value.strip() or None

    @field_validator("usuario_responsable", mode="before")
    def limpiar_usuario_responsable(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        usuario = value.strip()
        if not usuario:
            raise ValueError(MENSAJE_RESPONSABLE)
        return usuario

    @field_validator("fecha", mode="before")
    def fecha_valida(cls, value: Any) -> Any:
        return _validar_fecha_texto(value, "fecha")

    @field_validator("horas", mode="before")
    def horas_validas(cls, value: Any) -> Any:
        if value is None:
            raise ValueError(MENSAJE_HORAS_EVENTO)

        try:
            horas = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(MENSAJE_HORAS_EVENTO) from error

        if horas <= 0:
            raise ValueError(MENSAJE_HORAS_EVENTO)

        return value


class EventoActualizarParcial(BaseModel):
    titulo: Optional[str] = Field(
        default=None,
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

    @field_validator("titulo", mode="before")
    def titulo_no_vacio(
        cls, value: Any
    ) -> Any:
        if not isinstance(value, str):
            return value

        titulo = value.strip()

        if not titulo:
            raise ValueError(MENSAJE_TITULO_EVENTO)

        return titulo

    @field_validator("descripcion")
    def limpiar_descripcion(
        cls, value: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None

        return value.strip() or None

    @field_validator("usuario_responsable", mode="before")
    def limpiar_usuario_responsable(
        cls, value: Any
    ) -> Any:
        if not isinstance(value, str):
            return value

        usuario = value.strip()
        if not usuario:
            raise ValueError(MENSAJE_RESPONSABLE)
        return usuario

    @field_validator("horas", mode="before")
    def horas_validas(cls, value: Any) -> Any:
        if value is None:
            return None

        try:
            horas = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(MENSAJE_HORAS_EVENTO) from error

        if horas <= 0:
            raise ValueError(MENSAJE_HORAS_EVENTO)

        return value


class Subtarea(BaseModel):
    evento_id: str  # UUID en formato string
    titulo: str = Field(..., max_length=120)
    dia_objetivo: date
    horas_estimadas: float = Field(..., gt=0)
    estado: Optional[str] = Field(default="Pendiente")
    notas: Optional[str] = Field(default=None, max_length=300)

    @field_validator("titulo", mode="before")
    def subtitulo_no_vacio(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        titulo = value.strip()

        if not titulo:
            raise ValueError(MENSAJE_TITULO_SUBTAREA)

        return titulo

    @field_validator("dia_objetivo", mode="before")
    def dia_objetivo_valido(cls, value: Any) -> Any:
        return _validar_fecha_texto(value, "día objetivo")

    @field_validator("horas_estimadas", mode="before")
    def horas_estimadas_validas(cls, value: Any) -> Any:
        try:
            horas = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(MENSAJE_HORAS_SUBTAREA) from error

        if horas <= 0:
            raise ValueError(MENSAJE_HORAS_SUBTAREA)

        return value


class SubtareaActualizarParcial(BaseModel):
    evento_id: Optional[str] = None

    titulo: Optional[str] = Field(
        default=None,
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

    motivo_posposicion: Optional[str] = Field(
        default=None,
        max_length=500
    )

    @field_validator("titulo", mode="before")
    def subtitulo_no_vacio(
        cls, value: Any
    ) -> Any:
        if not isinstance(value, str):
            return value

        titulo = value.strip()

        if not titulo:
            raise ValueError(MENSAJE_TITULO_SUBTAREA)

        return titulo

    @field_validator("horas_estimadas", mode="before")
    def horas_estimadas_validas(
        cls, value: Any
    ) -> Any:
        if value is None:
            return None

        try:
            horas = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(MENSAJE_HORAS_SUBTAREA) from error

        if horas <= 0:
            raise ValueError(MENSAJE_HORAS_SUBTAREA)

        return value

class RegistroRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    apellido: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=3, max_length=254)
    telefono: str = Field(..., min_length=7, max_length=20)
    password: str = Field(..., min_length=6, max_length=72)

    @field_validator("nombre", "apellido")
    def validar_nombre_apellido(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("El nombre y apellido son requeridos.")

        return value

    @field_validator("email")
    def limpiar_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("telefono")
    def limpiar_telefono(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("El número de teléfono es requerido.")

        return value


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1)

    @field_validator("email")
    def limpiar_email(cls, value: str) -> str:
        return value.strip().lower()

class ConfiguracionUsuarioRequest(BaseModel):
    horas_dia: StrictInt = Field(
        ...,
        ge=1,
        le=16,
        description="Límite diario de horas entre 1 y 16.",
    )

    @field_validator("horas_dia", mode="before")
    def validar_horas_dia(cls, value: Any) -> Any:
        """Aplica US-12 (rango 1-16) con el mensaje funcional del backlog.

        Se valida antes del `StrictInt` y de las restricciones de campo
        para que el 422 llegue a la interfaz con un mensaje comprensible
        y no con el texto técnico del validador.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(MENSAJE_RANGO_HORAS_DIA)

        if value < 1 or value > 16:
            raise ValueError(MENSAJE_RANGO_HORAS_DIA)

        return value


class ConfiguracionUsuarioResponse(BaseModel):
    usuario_id: str
    horas_dia: int


# ============================================================
# BE-01 / BE-03 / BE-04 — reprogramación y resolución de conflictos
# ============================================================

class ReprogramarSubtareaRequest(BaseModel):
    """Cuerpo de PATCH /subtareas/{id}/reprogramar."""

    dia_objetivo: date = Field(
        ...,
        description="Nueva fecha objetivo (YYYY-MM-DD). No puede ser anterior a hoy.",
    )

    horas_estimadas: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Nueva estimación de horas. Si se omite se conserva la actual."
        ),
    )

    motivo_posposicion: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Motivo opcional de la reprogramación.",
    )


class ResolverConflictoSubtareaRequest(BaseModel):
    """Cuerpo de PATCH /subtareas/{id}/resolver.

    Este endpoint resuelve el conflicto reduciendo las horas estimadas.
    Mover la gestión a otro día se hace con
    `PATCH /subtareas/{id}/reprogramar`, que es la única operación que
    cambia `dia_objetivo` (US-06).
    """

    estrategia: Literal["reducir_horas"] = Field(
        ...,
        description=(
            "Única estrategia de este endpoint. Para mover la gestión "
            "a otro día usar PATCH /subtareas/{id}/reprogramar."
        ),
    )

    horas_estimadas: float = Field(
        ...,
        gt=0,
        description=(
            "Nueva estimación de horas de la gestión. Obligatoria."
        ),
    )

    motivo_posposicion: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Motivo opcional de la resolución.",
    )

    @model_validator(mode="before")
    @classmethod
    def exigir_estrategia_y_horas(cls, data: Any) -> Any:
        """Evita el mensaje técnico "Field required" del 422.

        Se valida antes de que Pydantic revise los campos obligatorios
        para responder con el mensaje funcional en español.
        """
        if isinstance(data, dict):
            estrategia = data.get("estrategia")

            if estrategia is None:
                raise ValueError(MENSAJE_ESTRATEGIA_INVALIDA)

            if estrategia != "reducir_horas":
                raise ValueError(MENSAJE_ESTRATEGIA_INVALIDA)

            if data.get("horas_estimadas") is None:
                raise ValueError(MENSAJE_HORAS_INVALIDAS)

        return data

    @field_validator("horas_estimadas", mode="before")
    def horas_validas(cls, value: Any) -> Any:
        try:
            horas = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(MENSAJE_HORAS_INVALIDAS) from error

        if horas <= 0:
            raise ValueError(MENSAJE_HORAS_INVALIDAS)

        return value


class ResumenSobrecargaDia(BaseModel):
    """Resultado del cálculo de sobrecarga de un día.

    Las claves en español siguen la convención que ya usa `GET /hoy`
    (`horas_planificadas_hoy`, `limite_horas_dia`, `sobrecarga`,
    `exceso_horas`).
    """

    conflicto: bool = Field(
        ...,
        description="True cuando las horas planificadas exceden el límite.",
    )
    horas_planificadas: float = Field(
        ...,
        description="Total de horas planificadas del día resultante.",
    )
    limite_horas_dia: int = Field(
        ...,
        description="Límite diario configurado por el organizador.",
    )
    exceso_horas: float = Field(default=0.0, description="Horas por encima del límite.")
    dia: str = Field(..., description="Fecha evaluada en formato YYYY-MM-DD.")
    horas_previas_dia: float = Field(
        default=0.0,
        description="Horas ya planificadas en el día sin la subtarea modificada.",
    )
    horas_subtarea: float = Field(
        default=0.0,
        description="Horas de la subtarea que se reprograma o reduce.",
    )


class SubtareaReprogramadaResponse(BaseModel):
    message: str
    subtarea: dict[str, Any]
    resumen: ResumenSobrecargaDia
    resumen_origen: Optional[ResumenSobrecargaDia] = Field(
        default=None,
        description="Estado del día de origen cuando la fecha cambia.",
    )


class ConflictoSobreCargaResponse(ResumenSobrecargaDia):
    """Respuesta 409: la reprogramación dejaría el día sobrecargado."""

    detail: str = Field(
        ...,
        description="Mensaje funcional del conflicto.",
    )
    subtarea: Optional[dict[str, Any]] = Field(
        default=None,
        description="Subtarea sin cambios: no se persistió la reprogramación.",
    )
    estrategias_disponibles: list[str] = Field(
        default_factory=lambda: ["mover_fecha", "reducir_horas"],
        description=(
            "Opciones para resolver el conflicto. `mover_fecha`: "
            "llamar otra vez a PATCH /subtareas/{id}/reprogramar con otra "
            "fecha. `reducir_horas`: PATCH /subtareas/{id}/resolver."
        ),
    )


class ResolverConflictoResponse(BaseModel):
    """Respuesta de PATCH /subtareas/{id}/resolver.

    Reducir horas no cambia la fecha objetivo, así que no hay estado del
    día de origen: ese dato solo aplica a /reprogramar.
    """

    message: str
    conflicto_resuelto: bool = Field(
        ...,
        description="False cuando el conflicto persiste tras el ajuste.",
    )
    subtarea: dict[str, Any]
    resumen: ResumenSobrecargaDia


class MensajeErrorResponse(BaseModel):
    detail: str = Field(..., description="Mensaje funcional del error.")

