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
- `estado`: filtra por estado de gestión (sin distinguir mayúsculas: `Pendiente`, `pendiente`, `pospuesto`, `hecho`).

Ejemplos:

- `GET /hoy?evento_id=<id>`
- `GET /hoy?estado=Pendiente`
- `GET /hoy?evento_id=<id>&estado=Pendiente`

La estructura de respuesta se mantiene igual independientemente de los filtros. Las subtareas completadas siguen excluidas por la regla de negocio de la vista Hoy.


## Autenticación y aislamiento por organizador

El endpoint `POST /auth/registro` permite crear un nuevo organizador desde cero mediante Supabase Auth.

Ejemplo:

```json
{
  "email": "nuevo@ejemplo.com",
  "password": "clave123"
}
```

La contraseña debe tener entre 6 y 72 caracteres. El backend crea el usuario y confirma el correo para que pueda iniciar sesión inmediatamente. Si el correo ya existe, el endpoint responde `409`.

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

## Reprogramar una subtarea

`PATCH /subtareas/{id}/reprogramar` cambia la fecha objetivo de una gestión logística.

```json
{
  "dia_objetivo": "2026-05-10",
  "horas_estimadas": 2,
  "motivo_posposicion": "Proveedor sin disponibilidad"
}
```

- `dia_objetivo` es obligatorio. Una fecha inválida o anterior al día de hoy responde `400` con el detalle `La fecha seleccionada no es válida o es anterior al día de hoy`.
- `horas_estimadas` es opcional: si se omite se conserva la actual. Debe ser mayor que 0.
- Solo se pueden reprogramar subtareas del organizador autenticado; una subtarea ajena responde `404`.

Antes de guardar, el backend calcula las horas resultantes del día destino usando el límite configurado por el organizador. Si el total supera el límite **no se guarda nada** y se responde `409` con la información del conflicto:

```json
{
  "detail": "Quedarías con 7h de gestión planificadas (límite 6h)",
  "conflicto": true,
  "horas_planificadas": 7,
  "limite_horas_dia": 6,
  "exceso_horas": 1,
  "dia": "2026-05-10",
  "horas_previas_dia": 5,
  "horas_subtarea": 2,
  "subtarea": { "...": "la subtarea sin cambios" },
  "estrategias_disponibles": ["mover_fecha", "reducir_horas"]
}
```

Seis horas exactas no exceden el límite; seis horas y un décimo sí. Si no hay conflicto la respuesta es `200`:

```json
{
  "message": "Fecha reprogramada exitosamente",
  "subtarea": { "...": "la subtarea actualizada" },
  "resumen": { "...": "estado del día destino" },
  "resumen_origen": { "...": "estado del día de origen" }
}
```

Cuando el conflicto aparece, las dos opciones de `estrategias_disponibles` se resuelven así: `mover_fecha` es reprogramar otra vez con otra fecha, y `reducir_horas` es `PATCH /subtareas/{id}/resolver`.

## Resolver un conflicto

Un conflicto se resuelve por dos caminos, y cada uno tiene una única operación:

- **Mover la gestión a otro día** → volver a llamar `PATCH /subtareas/{id}/reprogramar` con la nueva fecha. Si esa fecha deja de sobrecargar el día, se guarda; si no, vuelve a responder `409` sin guardar.
- **Reducir las horas estimadas** → `PATCH /subtareas/{id}/resolver`.

```json
{ "estrategia": "reducir_horas", "horas_estimadas": 1 }
```

`estrategia` solo admite `reducir_horas` y `horas_estimadas` es obligatoria. Cualquier otra estrategia responde `422`.

La respuesta es `200` con `conflicto_resuelto` y el resumen del día:

- si el día queda dentro del límite, el conflicto queda resuelto y el mensaje es `Cronograma actualizado correctamente`;
- si sigue excediendo, la estimación **queda guardada**, `conflicto_resuelto` es `false` y el mensaje explica que aún hay que reducir más horas o cambiar la fecha.

## Mensajes de validación

Los errores de validación (`422`) responden en el formato estándar de FastAPI y cada `msg` está redactado para mostrarse junto al campo en la interfaz:

| Situación | `detail[].msg` |
|---|---|
| Límite diario fuera de 1–16 | `El valor debe estar entre 1 y 16 horas diarias.` |
| Fecha vacía o con formato inválido | `El campo <campo> es obligatorio.` / `La fecha no es válida. Usa el formato AAAA-MM-DD.` |
| Horas ≤ 0 | `Las horas del evento deben ser mayores que 0.` / `Las horas estimadas de la gestión deben ser mayores que 0.` |
| Título demasiado corto | `El título del evento debe tener al menos 3 caracteres.` / `El título de la gestión debe tener al menos 2 caracteres.` |
| Fecha anterior a hoy al reprogramar | `La fecha seleccionada no es válida o es anterior al día de hoy.` |

