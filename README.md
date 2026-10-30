# EventHub Backend

API REST desarrollada con **FastAPI** y **Python** que gestiona eventos, subtareas y la planificación diaria de un organizador. Los datos se persisten en **Supabase (PostgreSQL)** y la autenticación se maneja a través de Supabase Auth.

Este backend está desplegado en **Render** y se comunica con el frontend de EventHub, que vive en un **repositorio separado**.

---

## 📋 Tabla de contenidos

- [Sobre el proyecto](#sobre-el-proyecto)
- [Stack tecnológico](#stack-tecnológico)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Requisitos previos](#requisitos-previos)
- [Instalación local](#instalación-local)
- [Variables de entorno](#variables-de-entorno)
- [Ejecutar en desarrollo](#ejecutar-en-desarrollo)
- [Endpoints principales](#endpoints-principales)
- [Despliegue en Render](#despliegue-en-render)
- [Relación con el frontend](#relación-con-el-frontend)
- [Contribución](#contribución)
- [Licencia](#licencia)

---

## Sobre el proyecto

EventHub Backend expone los recursos necesarios para:

- Autenticar organizadores (registro y login con Supabase Auth).
- Crear, editar y eliminar eventos.
- Gestionar subtareas asociadas a cada evento, incluyendo reprogramación y control de capacidad diaria.
- Consultar la vista "Hoy" con gestiones agrupadas en vencidas, urgentes y próximas.
- Consultar y actualizar el límite de horas por día del organizador.

Todas las consultas de eventos y subtareas están filtradas por el usuario autenticado (`usuario_id`), garantizando aislamiento entre organizadores.

---

## Stack tecnológico

| Capa | Tecnología | Propósito |
|------|-----------|-----------|
| Lenguaje | Python 3.10+ | Lógica del backend |
| Framework | FastAPI | API REST, validación con Pydantic v2 |
| Servidor | Uvicorn | Servidor ASGI de producción |
| Base de datos | Supabase (PostgreSQL) | Almacenamiento y autenticación |
| Cliente Supabase | `supabase` (Python) | Conexión a Supabase desde el backend |
| Variables de entorno | `python-dotenv` | Carga de `.env` en desarrollo |
| Zona horaria | `tzdata` | Fechas consistentes (zona de Colombia) |

---

## Estructura del repositorio

```text
EventHub_Backend/
├── main.py                 # Punto de entrada: app FastAPI, rutas raíz y auth
├── auth.py                 # Autenticación con Supabase Auth
├── database.py             # Cliente de Supabase
├── modelos.py              # Validaciones, mensajes y constantes de estado
├── servicios.py            # Lógica de negocio (vencimiento, sobrecarga, progreso)
├── routers/
│   ├── eventos.py          # CRUD de eventos
│   ├── subtareas.py        # CRUD de subtareas, reprogramar y resolver conflictos
│   ├── hoy.py              # Vista agrupada vencidas / urgentes / próximas
│   └── usuario.py          # Configuración de horas por día
├── supabase/
│   └── schema.sql          # Esquema SQL y políticas RLS
├── render.yaml             # Despliegue en Render
├── requirements.txt        # Dependencias de Python
├── .env.example            # Ejemplo de variables de entorno (no contiene secretos)
├── .gitignore              # Archivos ignorados por Git
└── README.md               # Este archivo
```

---

## Requisitos previos

- Python 3.10 o superior.
- `pip` (gestor de paquetes de Python).
- Una cuenta en [Supabase](https://supabase.com) con un proyecto creado.
- (Opcional) Cuenta en [Render](https://render.com) para desplegar.

---

## Instalación local

1. Clona este repositorio:

```bash
git clone https://github.com/MP1-UnivalleTeam/EventHub_Backend.git
cd EventHub_Backend
```

2. Crea y activa un entorno virtual:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate
```

3. Instala las dependencias:

```bash
pip install -r requirements.txt
```

4. Copia el archivo de ejemplo de variables de entorno:

```bash
# Windows (PowerShell):
Copy-Item .env.example .env

# macOS / Linux:
cp .env.example .env
```

5. Edita `.env` y completa los valores de tu proyecto de Supabase (ver sección [Variables de entorno](#variables-de-entorno)).

---

## Variables de entorno

Crea un archivo `.env` en la raíz del backend con las siguientes claves. **No subas este archivo a Git.**

```env
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=tu_clave_de_rol_de_servicio
ALLOWED_ORIGINS=https://tu-frontend.vercel.app
ALLOW_VERCEL_PREVIEWS=false
```

Puedes usar `.env.example` como referencia. Los valores reales se configuran como secretos en Render para producción.

---

## Ejecutar en desarrollo

```bash
uvicorn main:app --reload
```

La API estará disponible en:

- `http://127.0.0.1:8000/` — raíz
- `http://127.0.0.1:8000/docs` — documentación interactiva (Swagger UI)
- `http://127.0.0.1:8000/health` — estado del servicio y conexión a Supabase

---

## Endpoints principales

### Sistema
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Información del backend |
| GET | `/health` | Salud del servicio y base de datos |

### Autenticación
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/auth/registro` | Registrar nuevo organizador |
| POST | `/auth/login` | Iniciar sesión (devuelve `access_token`) |

### Eventos
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/eventos` | Listar eventos del organizador |
| GET | `/eventos/{id}` | Detalle de un evento |
| POST | `/eventos` | Crear evento |
| PUT | `/eventos/{id}` | Actualizar evento |
| DELETE | `/eventos/{id}` | Eliminar evento y sus subtareas |

### Subtareas
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/subtareas/` | Listar subtareas (filtra por `evento_id` y `estado`) |
| POST | `/subtareas/` | Crear subtarea |
| PUT | `/subtareas/{id}` | Actualizar subtarea completa |
| PATCH | `/subtareas/{id}` | Actualizar parcialmente una subtarea |
| DELETE | `/subtareas/{id}` | Eliminar una subtarea |
| PATCH | `/subtareas/{id}/reprogramar` | Reprogramar fecha y horas |
| PATCH | `/subtareas/{id}/resolver` | Resolver conflicto de sobrecarga |

### Vista Hoy
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/hoy` | Gestiones agrupadas en vencidas, urgentes y próximas |

### Usuario / Configuración
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/usuario/configuracion` | Obtener límite de horas por día |
| PUT | `/usuario/configuracion` | Actualizar límite de horas por día |

> Los estados válidos para subtareas son: `pendiente`, `pospuesto`, `hecho` y `vencido`.

---

## Despliegue en Render

El archivo `render.yaml` ya está configurado para desplegar automáticamente en Render:

- **Runtime:** Python
- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Health check:** `GET /health`

Configura las siguientes variables de entorno como **Secret Environment Variables** en el panel de Render:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ALLOWED_ORIGINS`
- `ALLOW_VERCEL_PREVIEWS`

---

## Relación con el frontend

Este backend está diseñado para consumirse desde el frontend de EventHub, que vive en un **repositorio separado**:

- Repositorio frontend: `https://github.com/MP1-UnivalleTeam/EventHub_Frontend.git` (React 19 + Vite, desplegado en Vercel).
- Documentación del contrato API: este repositorio incluye `README_FRONTEND_API.md` con la documentación de endpoints, payloads y errores.

Cada repositorio es independiente: clona, configura y despliega cada uno por separado.

---

## Contribución

1. Crea una rama desde `main` o `master`.
2. Realiza tus cambios y prueba localmente con `uvicorn main:app --reload`.
3. Abre un Pull Request describiendo el cambio y cómo se probó.

---

## Licencia

no definido.
