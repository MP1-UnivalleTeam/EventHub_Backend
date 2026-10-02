import os

from dotenv import load_dotenv
from supabase import Client, create_client


load_dotenv()


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError(
        "Faltan las credenciales de Supabase en las variables de entorno."
    )


def crear_cliente() -> Client:
    return create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY,
    )


# Cliente para operaciones de base de datos.
supabase: Client = crear_cliente()


# Cliente exclusivo para operaciones administrativas de Auth.
supabase_admin: Client = crear_cliente()


# Cliente exclusivo para login y validación de tokens.
supabase_auth: Client = crear_cliente()