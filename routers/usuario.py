import logging

from fastapi import APIRouter, Depends, File, HTTPException, status, UploadFile
from fastapi.responses import JSONResponse

from auth import get_current_user
from database import supabase
from modelos import (
    ConfiguracionUsuarioRequest,
    ConfiguracionUsuarioResponse,
    FotoPerfilResponse,
    MensajeErrorResponse,
    PerfilUsuarioResponse,
)
from servicios import (
    LIMITE_HORAS_DIA_POR_DEFECTO,
    normalizar_horas_dia,
    evaluar_dias_sobrecargados,
    obtener_horas_dia,
    obtener_subtareas_del_usuario,
)

BUCKET_PERFILES = "perfiles"


router = APIRouter(
    prefix="/usuario",
    tags=["Usuario"],
)

logger = logging.getLogger(__name__)


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
        409: {
            "description": (
                "El nuevo límite excedería las horas planificadas en uno o "
                "más días; la configuración no se guardó."
            ),
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

    try:
        subtareas = obtener_subtareas_del_usuario(usuario_id)
        dias_sobrecargados = evaluar_dias_sobrecargados(
            subtareas,
            configuracion.horas_dia,
        )
        if dias_sobrecargados:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": (
                        "El nuevo límite deja días con horas planificadas "
                        "por encima de la capacidad."
                    ),
                    "dias_sobrecargados": dias_sobrecargados,
                    "estrategias_disponibles": [
                        "reprogramar",
                        "reducir_horas",
                    ],
                },
            )

        datos = {
            "usuario_id": usuario_id,
            "horas_dia": configuracion.horas_dia,
        }

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
        logger.exception("No fue posible guardar la configuración del usuario")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible guardar la configuración del usuario.",
        ) from error


# ============================================================
# FOTO DE PERFIL (Supabase Storage)
# ============================================================

@router.get(
    "/perfil",
    response_model=PerfilUsuarioResponse,
    responses={
        401: {
            "model": MensajeErrorResponse,
            "description": "Falta el token de autenticación.",
        },
        404: {
            "model": MensajeErrorResponse,
            "description": "Perfil no encontrado.",
        },
        502: {
            "model": MensajeErrorResponse,
            "description": "Error consultando el perfil.",
        },
    },
)
def obtener_perfil(
    current_user: dict = Depends(get_current_user),
):
    usuario_id = current_user["id"]

    try:
        response = (
            supabase
            .table("usuarios")
            .select("nombre, apellido, email")
            .eq("usuario_id", usuario_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Perfil de usuario no encontrado.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error consultando el perfil de usuario")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible consultar el perfil del usuario.",
        ) from error


def _ruta_foto_perfil(usuario_id: str) -> str:
    """Ruta del archivo dentro del bucket de Supabase Storage."""
    return f"{usuario_id}/foto_perfil.jpg"


@router.get(
    "/foto-perfil",
    response_model=FotoPerfilResponse,
    responses={
        401: {
            "model": MensajeErrorResponse,
            "description": "Falta el token de autenticación.",
        },
        502: {
            "model": MensajeErrorResponse,
            "description": "Error de la base de datos o almacenamiento.",
        },
    },
)
def obtener_foto_perfil(
    current_user: dict = Depends(get_current_user),
):
    """
    Devuelve la URL pública de la foto de perfil del usuario autenticado,
    guardada en la columna `foto_perfil_url` de la tabla `usuarios`.
    """
    usuario_id = current_user["id"]

    try:
        response = (
            supabase
            .table("usuarios")
            .select("foto_perfil_url")
            .eq("usuario_id", usuario_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado.",
            )

        url = response.data[0].get("foto_perfil_url")

        return {
            "message": "Foto de perfil obtenida correctamente.",
            "foto_perfil_url": url or "",
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error obteniendo foto de perfil")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible obtener la foto de perfil.",
        ) from error


@router.post(
    "/foto-perfil",
    response_model=FotoPerfilResponse,
    responses={
        200: {
            "model": FotoPerfilResponse,
            "description": "Foto subida y URL guardada en Supabase Storage.",
        },
        401: {
            "model": MensajeErrorResponse,
            "description": "Falta el token de autenticación.",
        },
        502: {
            "model": MensajeErrorResponse,
            "description": "Error subiendo la imagen o guardando la URL.",
        },
    },
)
def subir_foto_perfil(
    current_user: dict = Depends(get_current_user),
    file: UploadFile = File(...),
):
    """
    Sube una imagen de foto de perfil al bucket `perfiles` de Supabase
    Storage y guarda la URL pública en la columna `foto_perfil_url` de
    la tabla `usuarios`.

    Si el usuario ya tiene una foto, se reemplaza automáticamente
    (upsert) en la misma ruta del bucket.
    """
    usuario_id = current_user["id"]
    ruta = _ruta_foto_perfil(usuario_id)

    try:
        # Leer el archivo en memoria
        contenido = file.file.read()

        # Subir a Supabase Storage con upsert para reemplazar si ya existe
        supabase.storage.from_(BUCKET_PERFILES).upload(
            ruta,
            contenido,
            file_options={
                "content-type": file.content_type or "image/jpeg",
                "upsert": "true",
            },
        )

        # Obtener URL pública del archivo
        url_publica = supabase.storage.from_(BUCKET_PERFILES).get_public_url(ruta)

        # Guardar la URL en la tabla usuarios
        response = (
            supabase
            .table("usuarios")
            .update({"foto_perfil_url": url_publica})
            .eq("usuario_id", usuario_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado para guardar la foto.",
            )

        return {
            "message": "Foto de perfil guardada correctamente.",
            "foto_perfil_url": url_publica,
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Error subiendo foto de perfil a Supabase Storage")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible subir la foto de perfil.",
        ) from error