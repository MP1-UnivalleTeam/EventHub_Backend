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
- `GET /eventos/{id}`: devuelve el detalle del evento con `total_subtareas`
  y `total_ejecutadas`. Solo los estados que representan una ejecución
  finalizada cuentan como ejecutadas; `pospuesto` no cuenta.
- `GET /hoy/`: devuelve las subtareas pendientes agrupadas en vencidas, urgentes del día y próximas.
- `POST /eventos`: crea un evento y devuelve `201` con el registro creado.

Para Render se incluye [`render.yaml`](render.yaml). Las variables de Supabase se configuran como secretos del servicio, nunca en el frontend.

### Endpoint `GET /hoy`

Devuelve las subtareas no completadas agrupadas en `vencidas`, `urgentes` y `proximas`, ordenadas por prioridad temporal y menor esfuerzo como desempate. Al consultar `/hoy` o las subtareas, las tareas no completadas cuya fecha objetivo ya pasó se guardan en Supabase con `estado: "Vencido"`, y ese estado se incluye en la respuesta. Si una fecha vencida se actualiza a hoy o a futuro, el estado vuelve a `"Pendiente"`.

Admite filtros opcionales:

- `evento_id`: filtra por evento.
- `estado`: filtra por estado de gestión (sin distinguir mayúsculas: `Pendiente`, `Vencido`, `pospuesto`, `hecho`).

Ejemplos:

- `GET /hoy?evento_id=<id>`
- `GET /hoy?estado=Pendiente`
- `GET /hoy?evento_id=<id>&estado=Pendiente`

La estructura de respuesta se mantiene igual independientemente de los filtros. Las subtareas completadas siguen excluidas por la regla de negocio de la vista Hoy.

### Cambiar el estado de una subtarea

`PATCH /subtareas/{id}` permite actualizar parcialmente una subtarea. Los
estados admitidos son `pendiente`, `pospuesto` y `hecho`; la comparación no
distingue mayúsculas y el backend persiste el valor normalizado en minúsculas.
La nota opcional se envía en `notas` y admite hasta 300 caracteres.

```json
{
  "estado": "pospuesto",
  "notas": "Pendiente de confirmación del proveedor"
}
```

La ruta requiere autenticación y solo modifica subtareas del organizador
autenticado. Un estado o una nota inválidos responden `422`, una subtarea
inexistente o ajena responde `404`, y un fallo de persistencia responde `502`.
Si la actualización activa excedería el límite diario configurado, responde
`409` con el resumen de carga y no guarda ningún cambio.

### Progreso de un evento

El detalle `GET /eventos/{id}` incluye:

```json
{
  "total_subtareas": 0,
  "total_ejecutadas": 0
}
```

Los conteos se consultan de nuevo en cada petición, por lo que reflejan los
cambios de estado persistidos. Un evento sin subtareas devuelve ambos conteos
en cero. Los estados `hecho`, `hecha`, `completado`, `completada`, `ejecutado`
y `ejecutada` cuentan como ejecutados; `pospuesto` no.

### Eliminar eventos y subtareas

`DELETE /subtareas/{id}` elimina una subtarea únicamente si pertenece al
organizador autenticado. `DELETE /eventos/{id}` elimina primero las subtareas
del evento que pertenecen a ese organizador y después el evento. Ambos
endpoints solicitan a Supabase la representación de la fila eliminada para
confirmar que el borrado se persistió; responden `404` si el registro no
existe o no pertenece al usuario y `502` si la base de datos no confirma el
borrado o devuelve un error.

### Editar la planificación

La creación y edición de una subtarea comprueban que su fecha no esté en el
pasado ni después de la fecha del evento, y que el total de horas no exceda
el límite diario. Las fechas y horas inválidas responden `400` o `422`;
cuando el cambio excede el límite, la respuesta es `409` e incluye los datos
del día y las alternativas `mover_fecha` y `reducir_horas`. La actualización
no se persiste en ese caso.

`PATCH /subtareas/{id}/resolver` solo persiste la reducción si el día queda
dentro del límite; si todavía lo excede, responde `409` y conserva la
subtarea sin cambios. `PUT /usuario/configuracion` también comprueba todas
las fechas planificadas antes de reducir el límite; si alguna excedería la
nueva capacidad, responde `409` con el detalle por día y no cambia la
configuración.


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
- `horas_estimadas` es opcional: si se omite se conserva la actual. Debe ser mayor que 0 y no superar 24.
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

La respuesta es `200` con `conflicto_resuelto: true` y el resumen del día si
la reducción respeta el límite. Si sigue excediéndolo, responde `409` con el
detalle del conflicto y **no guarda ningún cambio**; reduce más horas o mueve
la subtarea antes de volver a intentar.

## Mensajes de validación

Los errores de validación (`422`) responden en el formato estándar de FastAPI y cada `msg` está redactado para mostrarse junto al campo en la interfaz:

| Situación | `detail[].msg` |
|---|---|
| Límite diario fuera de 1–16 | `El valor debe estar entre 1 y 16 horas diarias.` |
| Fecha vacía o con formato inválido | `El campo <campo> es obligatorio.` / `La fecha no es válida. Usa el formato AAAA-MM-DD.` |
| Horas inválidas | `Las horas del evento deben ser mayores que 0.` / `Las horas estimadas de la gestión deben ser mayores que 0.` / `Las horas estimadas de la gestión no pueden superar 24 horas.` |
| Título o nombre vacío | `El título del evento es obligatorio y no puede estar vacío.` / `El nombre de la subtarea es obligatorio y no puede estar vacío.` |
| Fecha anterior a hoy al reprogramar | `La fecha seleccionada no es válida o es anterior al día de hoy.` |
