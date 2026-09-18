from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import eventos, subtareas

app = FastAPI(
    title="EventHub API",
    version="1.0",
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(eventos.router)
app.include_router(subtareas.router)

@app.get("/")
def read_root():
    return {
        "mensaje": "Backend de EventHub con FastAPI",
    }