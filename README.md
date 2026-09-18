# EventHub API

API FastAPI que recibe los eventos del frontend y los persiste en Supabase.

## Ejecutar localmente

1. Copia `.env.example` a `.env` y completa las credenciales de Supabase.
2. Instala dependencias con `pip install -r requirements.txt`.
3. Ejecuta `uvicorn main:app --reload`.
4. Abre `http://127.0.0.1:8000/docs`.

Endpoints principales:

- `GET /health`: comprueba la conexión a Supabase.
- `GET /eventos`: consulta registros persistidos.
- `POST /eventos`: crea un evento y devuelve `201` con el registro creado.

Para Render se incluye [`render.yaml`](render.yaml). Las variables de Supabase se configuran como secretos del servicio, nunca en el frontend.
