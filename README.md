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
- `GET /hoy/`: devuelve las subtareas pendientes agrupadas en vencidas, urgentes del día y próximas.
- `POST /eventos`: crea un evento y devuelve `201` con el registro creado.

Para Render se incluye [`render.yaml`](render.yaml). Las variables de Supabase se configuran como secretos del servicio, nunca en el frontend.

### Endpoint `GET /hoy`

Devuelve las subtareas no completadas agrupadas en `vencidas`, `urgentes` y `proximas`, ordenadas por prioridad temporal y menor esfuerzo como desempate.

Admite filtros opcionales que se aplican directamente sobre Supabase:

- `evento_id`: filtra por evento.
- `estado`: filtra por estado de gestión.

Ejemplos:

- `GET /hoy?evento_id=<id>`
- `GET /hoy?estado=Pendiente`
- `GET /hoy?evento_id=<id>&estado=Pendiente`

La estructura de respuesta se mantiene igual independientemente de los filtros. Las subtareas completadas siguen excluidas por la regla de negocio de la vista Hoy.


## Autenticación y aislamiento por organizador

El endpoint `POST /auth/login` autentica al organizador mediante Supabase Auth.

Ejemplo:

```json
{
  "email": "organizador@ejemplo.com",
  "password": "tu_clave"
}
```

La respuesta contiene un `access_token`. Para las rutas privadas se debe enviar:

```text
Authorization: Bearer <access_token>
```

Las consultas de eventos, subtareas y la vista `/hoy` se filtran por el `usuario_id` obtenido de la sesión. El cliente no puede escoger el `usuario_id` del registro que crea.

La base de datos debe tener `usuario_id uuid` en `eventos` y `subtareas`. Revisa `supabase/schema.sql` para la migración.

## Configuración de horas por día

La configuración del límite diario es privada por organizador y requiere autenticación.

- `GET /usuario/configuracion`: devuelve el límite del organizador autenticado.
- `PUT /usuario/configuracion`: actualiza el límite.

Body:

```json
{
  "horas_dia": 8
}
```

`horas_dia` debe ser un número entero entre `1` y `16`. Si el organizador todavía no tiene una configuración guardada, el valor devuelto es `6`.

La vista `GET /hoy` utiliza esta configuración para calcular la sobrecarga de las gestiones no completadas programadas para el día actual. En `resumen` devuelve `horas_programadas_hoy`, `limite_horas_dia`, `sobrecarga` y `exceso_horas`.

