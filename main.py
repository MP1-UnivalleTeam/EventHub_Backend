from fastapi import FastAPI
from routers import eventos, subtareas

app = FastAPI(title="EventHub API", version="1.0")

app.include_router(eventos.router)
app.include_router(subtareas.router)

@app.get("/")
def read_root():
    return {"backend supebase fastAPI"}