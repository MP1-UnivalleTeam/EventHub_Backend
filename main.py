import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from database import supabase, supabase_admin, supabase_auth
from modelos import LoginRequest, RegistroRequest
from routers import eventos, hoy, subtareas, usuario


app = FastAPI(
    title="EventHub API",
    version="1.1.0",
    redirect_slashes=False
)


# ============================================================
# CORS
# ============================================================

origenes_permitidos = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "https://eventhub-frontend-odh5ligps-univalleteam-4136.vercel.app",
]

# Agregar orígenes adicionales desde variables de entorno
origenes_env = [
    origen.strip()
    for origen in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origen.strip()
]

origenes_permitidos.extend(origenes_env)


# Permitir previews de Vercel si está habilitado
allow_vercel_previews = (
    r"https://.*\.vercel\.app"
    if os.getenv("ALLOW_VERCEL_PREVIEWS") == "true"
    else None
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos,
    allow_origin_regex=allow_vercel_previews,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=["*"],
)


# ============================================================
# ROUTERS
# ============================================================

app.include_router(eventos.router)
app.include_router(subtareas.router)
app.include_router(hoy.router)
app.include_router(usuario.router)


# ============================================================
# REGISTRO DE USUARIO
# ============================================================

@app.post(
    "/auth/registro",
    status_code=status.HTTP_201_CREATED,
    tags=["Autenticación"]
)
def registro(datos: RegistroRequest):
    """
    Registra un nuevo usuario en Supabase Auth y crea
    su perfil en public.usuarios.
    """

    try:
        # ----------------------------------------------------
        # 1. Crear usuario en Supabase Auth
        # ----------------------------------------------------

        response = supabase_admin.auth.admin.create_user(
            {
                "email": datos.email,
                "password": datos.password,
                "email_confirm": True,
            }
        )

        user = response.user

        if not user or not user.id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No fue posible crear el usuario."
            )

        usuario_id = str(user.id)

        # ----------------------------------------------------
        # 2. Crear perfil en public.usuarios
        # ----------------------------------------------------

        perfil = {
            "usuario_id": usuario_id,
            "nombre": datos.nombre,
            "apellido": datos.apellido,
            "email": datos.email,
            "telefono": datos.telefono,
        }

        try:
            supabase.table("usuarios").insert(perfil).execute()

            configuracion = {
                "usuario_id": usuario_id,
                "horas_dia": 6,
            }

            supabase.table("usuario_configuracion").insert(
                configuracion
            ).execute()

        except Exception as error_perfil:

            print(
                f"ERROR CREANDO PERFIL DEL USUARIO: "
                f"{repr(error_perfil)}"
            )

            # Si falla el perfil, eliminar el usuario de Auth
            # para evitar dejar una cuenta incompleta.
            try:
                supabase_admin.auth.admin.delete_user(usuario_id)
            except Exception as error_delete:
                print(
                    f"ERROR ELIMINANDO USUARIO DE AUTH: "
                    f"{repr(error_delete)}"
                )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "El usuario fue creado en Auth, "
                    "pero no fue posible crear su perfil."
                ),
            ) from error_perfil

        # ----------------------------------------------------
        # 3. Respuesta exitosa
        # ----------------------------------------------------

        return {
            "message": "Usuario registrado correctamente.",
            "usuario": {
                "id": usuario_id,
                "nombre": datos.nombre,
                "apellido": datos.apellido,
                "email": datos.email,
                "telefono": datos.telefono,
            },
        }

    # --------------------------------------------------------
    # Errores HTTP controlados
    # --------------------------------------------------------

    except HTTPException:
        raise

    # --------------------------------------------------------
    # Errores generales
    # --------------------------------------------------------

    except Exception as error:

        print(
            f"ERROR REAL EN REGISTRO: "
            f"{repr(error)}"
        )

        mensaje = str(error).lower()

        # Correo ya registrado
        if (
            "already registered" in mensaje
            or "already exists" in mensaje
            or "duplicate" in mensaje
            or "email_exists" in mensaje
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El correo electrónico ya está registrado.",
            ) from error

        # Devolver temporalmente el error real para poder
        # identificar problemas de configuración de Supabase.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al registrar usuario: {str(error)}",
        ) from error


# ============================================================
# LOGIN
# ============================================================

@app.post(
    "/auth/login",
    tags=["Autenticación"]
)
def login(credenciales: LoginRequest):
    """
    Inicia sesión con Supabase Auth y devuelve
    el access token.
    """

    try:

        response = supabase_auth.auth.sign_in_with_password(
            {
                "email": credenciales.email,
                "password": credenciales.password,
            }
        )

        session = response.session
        user = response.user

        if not session or not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Correo o contraseña incorrectos.",
            )

        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "token_type": "bearer",
            "expires_in": session.expires_in,
            "usuario": {
                "id": str(user.id),
                "email": user.email,
            },
        }

    except HTTPException:
        raise

    except Exception as error:

        print(
            f"ERROR EN LOGIN: "
            f"{repr(error)}"
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        ) from error


# ============================================================
# ROOT
# ============================================================

@app.get(
    "/",
    tags=["Sistema"]
)
def read_root():
    return {
        "mensaje": "Backend de EventHub con FastAPI",
        "documentacion": "/docs"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get(
    "/health",
    tags=["Sistema"]
)
def healthcheck():
    """
    Comprueba que Render puede consultar Supabase
    sin revelar secretos.
    """

    try:

        supabase.table("eventos") \
            .select("id") \
            .limit(1) \
            .execute()

        return {
            "status": "ok",
            "database": "connected"
        }

    except Exception as error:

        print(
            f"ERROR EN HEALTHCHECK: "
            f"{repr(error)}"
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay conexión disponible con la base de datos.",
        ) from error
