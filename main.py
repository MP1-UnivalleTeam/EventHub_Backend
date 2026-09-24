import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from database import supabase
from routers import eventos, subtareas

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