# Documentacion Detallada de la API

## Resumen

Esta API implementa un flujo de voz a acciones sobre tareas en memoria.

Flujo principal:
1. El cliente envia audio a POST /transcribe.
2. El backend transcribe audio a texto con Groq Whisper.
3. El backend transforma la transcripcion a una instruccion estructurada con un LLM.
4. La instruccion se valida contra el contrato permitido de /tasks.
5. La accion se ejecuta en memoria y se devuelve el resultado.

Tambien existe POST /instruction para obtener solo el enrutamiento semantico sin ejecutar la accion.

## Base URL y herramientas de exploracion

- Base URL local habitual: http://localhost:8000
- Swagger UI: /docs
- ReDoc: /redoc

## Configuracion y entorno

Variables principales (archivo .env en la raiz):

- groq_api_key (requerida)
- groq_model (default: llama-3.1-8b-instant)
- groq_transcription_model (default: whisper-large-v3-turbo)
- request_timeout_seconds (default: 45.0)
- allowed_origins (lista o csv)
- allowed_origin_regex (default permite localhost y dominios de Codespaces)
- allow_credentials (default: true)

Notas:
- No hay autenticacion JWT/API key propia de la app.
- La seguridad actual depende del entorno y de CORS para navegador.

## CORS

La API usa CORS middleware con:
- allow_methods: ["*"]
- allow_headers: ["*"]
- allow_credentials configurable
- origenes permitidos por lista y regex

## Modelos de datos

### Task

```json
{
  "id": 1,
  "title": "Buy groceries",
  "done": false
}
```

### TaskCreate

```json
{
  "title": "Buy groceries",
  "done": false
}
```

Reglas:
- title: string, obligatorio, minimo 1 caracter
- done: bool, opcional, default false

### TaskReplace

```json
{
  "title": "Buy groceries",
  "done": true
}
```

Reglas:
- title: obligatorio, minimo 1 caracter
- done: obligatorio

### TaskUpdate

```json
{
  "title": "Buy groceries",
  "done": true
}
```

Reglas:
- title: opcional (si viene, minimo 1 caracter)
- done: opcional

### InstructionRequest

```json
{
  "transcription": "add buy groceries to my list"
}
```

Reglas:
- transcription: string obligatorio, minimo 1 caracter

### InstructionPayload

```json
{
  "endpoint": "/tasks",
  "method": "POST",
  "params": {
    "title": "Buy groceries"
  }
}
```

Reglas:
- endpoint: string no vacio, debe mapear a rutas soportadas
- method: string no vacio (el backend normaliza a uppercase)
- params: objeto JSON

### TranscribeFlowResponse

```json
{
  "transcription": "add buy groceries to my list",
  "instruction": {
    "endpoint": "/tasks",
    "method": "POST",
    "params": {
      "title": "Buy groceries"
    }
  },
  "result": {
    "id": 1,
    "title": "Buy groceries",
    "done": false
  }
}
```

## Endpoints

## 1) Healthcheck

Metodo: GET
Ruta: /

Respuesta 200:

```json
{
  "status": "ok"
}
```

## 2) Obtener tareas

Metodo: GET
Ruta: /tasks

Respuesta 200:

```json
[
  {
    "id": 1,
    "title": "Buy groceries",
    "done": false
  }
]
```

## 3) Crear tarea

Metodo: POST
Ruta: /tasks
Body: TaskCreate

Respuesta 201:

```json
{
  "id": 2,
  "title": "Read book",
  "done": false
}
```

## 4) Reemplazar tarea completa

Metodo: PUT
Ruta: /tasks/{task_id}
Body: TaskReplace

Respuesta 200:

```json
{
  "id": 2,
  "title": "Read clean architecture",
  "done": true
}
```

Errores:
- 404 si task_id no existe
- 422 si body no cumple contrato

## 5) Actualizar tarea parcial

Metodo: PATCH
Ruta: /tasks/{task_id}
Body: TaskUpdate

Respuesta 200:

```json
{
  "id": 2,
  "title": "Read clean architecture",
  "done": false
}
```

Errores:
- 404 si task_id no existe
- 422 si body no cumple contrato

## 6) Eliminar tarea

Metodo: DELETE
Ruta: /tasks/{task_id}

Respuesta 200:

```json
{
  "message": "Task 2 deleted successfully"
}
```

Errores:
- 404 si task_id no existe

## 7) Enrutamiento semantico de texto

Metodo: POST
Ruta: /instruction
Body: InstructionRequest

Descripcion:
- Usa Groq Chat Completions con response_format json_object.
- Devuelve solo el payload de enrutamiento, no ejecuta tareas.
- Incluye una pasada de reparacion semantica si la primera salida del LLM viola el contrato.

Respuesta 200:

```json
{
  "endpoint": "/tasks",
  "method": "POST",
  "params": {
    "title": "Buy groceries"
  }
}
```

Errores principales:
- 400 cuando endpoint/metodo no mapea a rutas permitidas
- 422 cuando params no cumple contrato de TaskCreate/TaskReplace/TaskUpdate
- 429 limite de Groq excedido
- 503 fallo de conexion a Groq
- 502 error de estado Groq o payload vacio/invalido

## 8) Flujo completo audio -> instruccion -> ejecucion

Metodo: POST
Ruta: /transcribe
Content-Type: multipart/form-data

Campos del formulario:
- file (requerido): archivo de audio
- language (opcional): codigo ISO 639-1 (ej: es, en). Si no se envia, auto-detect.

Validaciones:
- file debe tener content_type audio/*
- file no puede estar vacio
- language debe cumplir formato (es|en|pt ...), variantes como es-ES se normalizan a es

Respuesta 200 (TranscribeFlowResponse):

```json
{
  "transcription": "add buy groceries to my list",
  "instruction": {
    "endpoint": "/tasks",
    "method": "POST",
    "params": {
      "title": "Buy groceries"
    }
  },
  "result": {
    "id": 1,
    "title": "Buy groceries",
    "done": false
  }
}
```

Errores principales:
- 400 archivo no-audio
- 400 archivo vacio
- 400 language invalido
- 400 instruccion no soportada
- 422 params invalido para la ruta objetivo
- 429 limite Groq
- 503 conexion Groq
- 502 respuesta Groq invalida/vacia

## Contrato interno de instrucciones soportadas

El backend solo acepta estas combinaciones:

- GET /tasks con params {}
- POST /tasks con params {"title": string, "done"?: boolean}
- PUT /tasks/{id} con params {"title": string, "done": boolean}
- PATCH /tasks/{id} con params {"title"?: string, "done"?: boolean}
- DELETE /tasks/{id} con params {}

Si el LLM devuelve algo fuera de ese contrato, se rechaza con 400 o 422 segun el caso.

## Ejemplos curl

## Crear tarea manual

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Plan sprint","done":false}'
```

## Obtener tareas

```bash
curl http://localhost:8000/tasks
```

## Enviar instruccion textual

```bash
curl -X POST http://localhost:8000/instruction \
  -H "Content-Type: application/json" \
  -d '{"transcription":"add plan sprint to my tasks"}'
```

## Enviar audio para flujo completo

```bash
curl -X POST http://localhost:8000/transcribe \
  -F "file=@./sample.webm" \
  -F "language=es"
```

## Persistencia y estado

- Las tareas viven solo en memoria del proceso.
- Reiniciar la aplicacion borra el estado.

## Arquitectura de rutas

- /instruction: planificacion semantica de intencion
- /tasks: ejecucion CRUD en memoria
- /transcribe: orquestacion STT + planificacion + ejecucion

Esto permite depurar por capas:
1. Validar STT (transcription)
2. Validar decision semantica (instruction)
3. Validar ejecucion (result)
