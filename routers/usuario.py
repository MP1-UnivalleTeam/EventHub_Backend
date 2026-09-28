import logging

from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user
from database import supabase
from modelos import ConfiguracionUsuarioRequest, ConfiguracionUsuarioResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usuario", tags=["Usuario"])

HORAS_DIA_POR_DEFECTO = 6


def obtener_horas_dia(usuario_id: str) -> int:
    """Obtiene el límite diario del organizador; usa 6 si aún no lo configura."""
    response = (
        supabase
        .table("usuario_configuracion")
        .select("horas_dia")
        .eq("usuario_id", usuario_id)
        .maybe_single()
        .execute()
    )

    if not response.data:
        return HORAS_DIA_POR_DEFECTO

    return int(response.data["horas_dia"])


@router.get(
    "/configuracion",
    response_model=ConfiguracionUsuarioResponse,
)
def obtener_configuracion(
    current_user: dict = Depends(get_current_user),
):
    """Devuelve la configuración del organizador autenticado."""
    try:
        usuario_id = current_user["id"]
        horas_dia = obtener_horas_dia(usuario_id)

        return {
            "usuario_id": usuario_id,
            "horas_dia": horas_dia,
        }

    except Exception as error:
        logger.exception("No fue posible consultar la configuración del usuario")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible consultar la configuración del usuario.",
        ) from error


@router.put(
    "/configuracion",
    response_model=ConfiguracionUsuarioResponse,
)
def actualizar_configuracion(
    configuracion: ConfiguracionUsuarioRequest,
    current_user: dict = Depends(get_current_user),
):
    """Guarda el límite diario del organizador autenticado."""
    try:
        usuario_id = current_user["id"]

        datos = {
            "usuario_id": usuario_id,
            "horas_dia": configuracion.horas_dia,
        }

        response = (
            supabase
            .table("usuario_configuracion")
            .upsert(datos, on_conflict="usuario_id")
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No se pudo guardar la configuración.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("No fue posible guardar la configuración del usuario")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible guardar la configuración del usuario.",
        ) from error
