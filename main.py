import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from database import supabase
from routers import eventos, subtareas

app = FastAPI(title="EventHub API", version="1.1.0")

origenes_locales = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

origenes_configurados = [
    origen.strip()
    for origen in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origen.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*origenes_locales, *origenes_configurados],
    allow_origin_regex=r"https://.*\.vercel\.app" if os.getenv("ALLOW_VERCEL_PREVIEWS") == "true" else None,
    allow_credentials=False,
    # ¡Actualizado para permitir todos los métodos requeridos por el frontend!
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(eventos.router)
app.include_router(subtareas.router)

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