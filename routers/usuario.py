from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user
from database import supabase
from modelos import ConfiguracionUsuarioRequest, ConfiguracionUsuarioResponse


router = APIRouter(
    prefix="/usuario",
    tags=["Usuario"],
)


@router.get(
    "/configuracion",
    response_model=ConfiguracionUsuarioResponse,
)
@router.get(
    "/configuracion",
    response_model=ConfiguracionUsuarioResponse,
)
def obtener_configuracion(
    current_user: dict = Depends(get_current_user),
):
    usuario_id = current_user["id"]

    try:
        response = (
            supabase
            .table("usuario_configuracion")
            .select("usuario_id, horas_dia")
            .eq("usuario_id", usuario_id)
            .maybe_single()
            .execute()
        )

        if response.data:
            return response.data

        configuracion = {
            "usuario_id": usuario_id,
            "horas_dia": 6,
        }

        creada = (
            supabase
            .table("usuario_configuracion")
            .insert(configuracion)
            .execute()
        )

        if creada.data:
            return creada.data[0]

        return configuracion

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible obtener la configuración del usuario.",
        ) from error


@router.put(
    "/configuracion",
    response_model=ConfiguracionUsuarioResponse,
)
def actualizar_configuracion(
    configuracion: ConfiguracionUsuarioRequest,
    current_user: dict = Depends(get_current_user),
):
    usuario_id = current_user["id"]

    datos = {
        "usuario_id": usuario_id,
        "horas_dia": configuracion.horas_dia,
    }

    try:
        response = (
            supabase
            .table("usuario_configuracion")
            .upsert(
                datos,
                on_conflict="usuario_id",
            )
            .select("usuario_id, horas_dia")
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="La configuración no pudo ser guardada.",
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No fue posible guardar la configuración del usuario: {str(error)}",
        ) from error

def obtener_horas_dia(usuario_id: str) -> int:
    try:
        response = (
            supabase
            .table("usuario_configuracion")
            .select("horas_dia")
            .eq("usuario_id", usuario_id)
            .maybe_single()
            .execute()
        )

        if not response.data:
            return 6

        return response.data["horas_dia"]

    except Exception:
        return 6