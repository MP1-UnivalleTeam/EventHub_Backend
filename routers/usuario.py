from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user
from database import supabase
from modelos import (
    ConfiguracionUsuarioRequest,
    ConfiguracionUsuarioResponse,
    MensajeErrorResponse,
)
from servicios import (
    LIMITE_HORAS_DIA_POR_DEFECTO,
    normalizar_horas_dia,
    obtener_horas_dia,
)


router = APIRouter(
    prefix="/usuario",
    tags=["Usuario"],
)


@router.get(
    "/configuracion",
    response_model=ConfiguracionUsuarioResponse,
    responses={
        401: {
            "model": MensajeErrorResponse,
            "description": "Falta el token de autenticación.",
        },
        502: {
            "model": MensajeErrorResponse,
            "description": "Error de la base de datos.",
        },
    },
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
            .limit(1)
            .execute()
        )

        if not response.data:
            # Sin configuración persistida se aplica el valor por defecto
            # de negocio (6 horas/día) solo para este organizador.
            return {
                "usuario_id": usuario_id,
                "horas_dia": LIMITE_HORAS_DIA_POR_DEFECTO,
            }

        return {
            "usuario_id": usuario_id,
            "horas_dia": normalizar_horas_dia(
                response.data[0].get("horas_dia")
            ),
        }

    except Exception as error:
        print(
            f"ERROR OBTENIENDO CONFIGURACION: "
            f"usuario_id={usuario_id} "
            f"error={repr(error)}"
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible obtener la configuración del usuario.",
        ) from error


@router.put(
    "/configuracion",
    response_model=ConfiguracionUsuarioResponse,
    responses={
        401: {
            "model": MensajeErrorResponse,
            "description": "Falta el token de autenticación.",
        },
        # El 422 lo documenta FastAPI automáticamente con el esquema de
        # validación: horas_dia es un entero entre 1 y 16.
        502: {
            "model": MensajeErrorResponse,
            "description": "Error de la base de datos.",
        },
    },
)
def actualizar_configuracion(
    configuracion: ConfiguracionUsuarioRequest,
    current_user: dict = Depends(get_current_user),
):
    # El PUT solo puede tocar la configuración del usuario autenticado:
    # el `usuario_id` sale de la sesión, nunca del cuerpo.
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