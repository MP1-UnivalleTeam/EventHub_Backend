import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from database import supabase
from modelos import LoginRequest, RegistroRequest
from routers import eventos, hoy, subtareas, usuario

app = FastAPI(title="EventHub API", version="1.1.0", redirect_slashes=False)

# Definir orígenes permitidos de manera consolidada
origenes_permitidos = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "https://eventhub-frontend-odh5ligps-univalleteam-4136.vercel.app", # Tu URL exacta actual de Vercel
]

# Agregar orígenes adicionales desde variables de entorno si existen
origenes_env = [
    origen.strip()
    for origen in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origen.strip()
]
origenes_permitidos.extend(origenes_env)

# Única llamada a add_middleware para CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos,
    allow_origin_regex=r"https://.*\.vercel\.app" if os.getenv("ALLOW_VERCEL_PREVIEWS") == "true" else None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(eventos.router)
app.include_router(subtareas.router)
app.include_router(hoy.router)
app.include_router(usuario.router)


@app.post("/auth/registro", status_code=status.HTTP_201_CREATED, tags=["Autenticación"])
def registro(datos: RegistroRequest):
    """Crea un nuevo usuario en Supabase Auth."""
    try:
        response = supabase.auth.admin.create_user(
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
                detail="No fue posible crear el usuario.",
            )

        return {
            "message": "Usuario registrado correctamente.",
            "usuario": {
                "id": str(user.id),
                "email": user.email,
            },
        }

    except HTTPException:
        raise
    except Exception as error:
        mensaje = str(error).lower()

        if "already registered" in mensaje or "already exists" in mensaje or "duplicate" in mensaje:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El correo electrónico ya está registrado.",
            ) from error

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fue posible registrar el usuario. Verifica los datos enviados.",
        ) from error


@app.post("/auth/login", tags=["Autenticación"])
def login(credenciales: LoginRequest):
    """Inicia sesión con Supabase Auth y devuelve el access token."""
    try:
        response = supabase.auth.sign_in_with_password(
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        ) from error

@app.get("/", tags=["Sistema"])
def read_root():
    return {"mensaje": "Backend de EventHub con FastAPI", "documentacion": "/docs"}

@app.get("/health", tags=["Sistema"])
def healthcheck():
    """Comprueba que Render puede consultar Supabase sin revelar secretos."""
    try:
        supabase.table("eventos").select("id").limit(1).execute()
        return {"status": "ok", "database": "connected"}
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay conexión disponible con la base de datos.",
        ) from error