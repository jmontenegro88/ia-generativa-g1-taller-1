# EcoMarket AI Assistant

Este proyecto implementa un asistente de atención al cliente para EcoMarket con una arquitectura basada en IA generativa, recuperación de contexto y validación estructurada de respuestas. La solución está pensada para atender consultas reales de soporte sobre pedidos, devoluciones, catálogo, políticas y clasificación de incidencias.

La idea principal es combinar datos operativos del negocio con prompts bien definidos y el modelo seleccionado en la parte documental, GPT-6 Sol, para responder con precisión, control y trazabilidad, evitando que el modelo invente información.

---

## 1. Objetivo del proyecto

El sistema está pensado para resolver varias tareas de soporte, no solo dos:

1. Estado de pedido
2. Evaluación de devoluciones
3. Búsqueda de productos por nombre o categoría
4. Consulta de políticas de negocio
5. Clasificación y priorización de incidencias
6. Métricas para medir rendimiento del asistente

---

## 2. Qué se implementó

La aplicación usa un enfoque RAG híbrido con estas capas:

- recuperación exacta de pedidos desde archivos JSON
- búsqueda de productos por catálogo
- lectura de la política de devoluciones como fuente normativa
- prompt engineering para cada caso de uso
- validación de salida con esquemas JSON estrictos
- fallback local si OpenAI no responde correctamente
- endpoints específicos para cada flujo de soporte

### Casos soportados

#### Estado del pedido
- Se busca el número de seguimiento en `data/pedidos.json`
- Se construye un prompt con el contexto actual del pedido
- El modelo responde con un JSON estructurado sobre el estado, la fecha estimada y el transporte

#### Devoluciones
- Se busca el producto en `data/productos.json`
- Se revisa la política de devoluciones
- El sistema decide si el caso es elegible, si faltan datos o si requiere agente humano

#### Búsqueda de productos
- El cliente puede consultar un producto por nombre o categoría
- El sistema devuelve información útil sobre el producto y su contexto

#### Consulta de política
- El usuario puede hacer preguntas sobre reglas del negocio
- El asistente responde aplicando la política disponible y señala si requiere revisión humana

#### Triage o clasificación de incidencias
- Se clasifica la solicitud en tipos como devolución, entrega, problema de producto o caso general
- Se prioriza la incidencia y se indican pasos de resolución

#### Métricas del servicio
- Se expone un resumen de KPIs para evaluar eficiencia, escalamiento y automatización

---

## 3. Arquitectura general

El flujo general del sistema es:

1. El cliente hace una petición al backend
2. FastAPI valida la entrada con Pydantic
3. El backend recupera el contexto relevante desde los datos
4. Se arma un prompt con instrucciones y contexto
5. OpenAI responde en JSON estructurado
6. La salida se valida con un esquema estricto
7. Se devuelve la respuesta final o se activa fallback local

```text
Cliente HTTP
   ↓
FastAPI
   ↓
Recuperación de datos
   ↓
Prompt builder
   ↓
OpenAI Responses API
   ↓
JSON schema validado
   ↓
Respuesta final
```

---

## 4. Estructura del proyecto

```text
proyecto taller 1/
├── .env
├── README.md
├── requirements.txt
├── data/
│   ├── pedidos.json
│   ├── productos.json
│   └── politica_devoluciones.md
├── src/
│   ├── config.py
│   ├── main.py
│   ├── models.py
│   ├── openai_client.py
│   ├── prompts.py
│   └── retrieval.py
├── 01_fase_1_modelo.md
├── 02_fase_2_riesgos.md
└── .venv/
```

### Papel de cada parte

- `src/main.py`: API principal con los endpoints
- `src/models.py`: modelos Pydantic de entrada y salida
- `src/prompts.py`: construcción de prompts para cada flujo
- `src/openai_client.py`: cliente OpenAI y validación de schema JSON
- `src/retrieval.py`: lectura y búsqueda del contexto
- `data/pedidos.json`: datos de pedidos para el soporte operativo
- `data/productos.json`: catálogo de productos
- `data/politica_devoluciones.md`: política normativa del negocio
- `.env`: configuración de credenciales y modelo

---

## 5. Cómo interactúan los prompts

Los prompts están construidos con tres bloques fundamentales:

1. rol del agente
2. contexto del negocio
3. formato de salida esperado

### Prompt de estado del pedido

Se usa para responder preguntas del tipo: “¿Dónde está mi pedido?” o “¿Cuándo llega?”

Incluye:
- el rol del asistente
- el contexto del pedido real
- instrucciones de no inventar datos
- el esquema JSON esperado

### Prompt de devolución

Se usa para decidir si un producto puede devolverse y qué pasos seguir.

Incluye:
- la política de devoluciones
- el producto concreto
- la solicitud del cliente
- reglas de negocio como plazo, defectos y excepciones

### Prompt de producto

Se usa para responder preguntas sobre el catálogo o las características del producto.

Incluye:
- nombre del producto
- categoría
- precio
- condiciones generales
- mensaje del cliente

### Prompt de política

Se usa para responder preguntas del tipo: “¿Puede devolver un producto de higiene abierto?”

Se basa en la política documentada y responde de forma limitada, sin inventar excepciones.

### Prompt de triage

Se usa para clasificar la solicitud y decidir si requiere agente humano.

Incluye:
- tipo de incidencia
- contexto del pedido si existe
- descripción del problema
- prioridad recomendada

---

## 6. Rol de los datos en la solución

La data es fundamental porque el modelo no debe “memorizar” la lógica del negocio. En esta solución, la información se recupera desde archivos reales del proyecto.

### `data/pedidos.json`

Contiene registros de pedidos con:
- número de seguimiento
- estado
- fecha estimada
- transportista
- enlace de rastreo
- producto relacionado

### `data/productos.json`

Contiene información del catálogo con:
- nombre
- categoría
- precio
- condición
- si es personalizado

### `data/politica_devoluciones.md`

Guarda la política de devoluciones del negocio y sirve como fuente normativa para decisiones automatizadas.

La diferencia clave es que el LLM nunca debe tomar decisiones basadas solo en su memoria. Siempre debe trabajar con contexto explícito y fuente documental.

---

## 7. Validación y control de la salida

La API no acepta respuestas libres del modelo. Cada endpoint exige una salida JSON con campos definidos.

Esto se hace con un esquema estricto en `src/openai_client.py` usando la API de OpenAI con `json_schema`.

### Beneficios

- respuesta consistente entre llamadas
- menos riesgo de texto libre o malformado
- integración más fácil con otras capas del sistema
- mayor trazabilidad y control del negocio

---

## 8. Endpoints disponibles

### 1) Estado del pedido

`POST /api/orders/status`

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/orders/status" \
  -H "Content-Type: application/json" \
  -d '{
    "tracking_number": "ECO-10003",
    "customer_id": "CUST-1003",
    "channel": "chat"
  }'
```

### 2) Evaluación de devolución

`POST /api/returns/evaluate`

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/returns/evaluate" \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Jabones artesanales",
    "category": "higiene",
    "condition": "nuevo",
    "received_days_ago": 12,
    "custom": false,
    "reason": "Quiero devolver un jabón que llegó bien"
  }'
```

### 3) Búsqueda de productos

`POST /api/products/search`

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/products/search" \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Jabones artesanales"
  }'
```

### 4) Consulta de política

`POST /api/policies/answer`

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/policies/answer" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Puedo devolver un producto de higiene abierto?",
    "category": "higiene"
  }'
```

### 5) Triage de incidencias

`POST /api/support/triage`

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/support/triage" \
  -H "Content-Type: application/json" \
  -d '{
    "issue_type": "devolucion",
    "customer_message": "Quiero devolver un jabón que llegó bien",
    "tracking_number": "ECO-10003"
  }'
```

### 6) Resumen de métricas

`GET /api/metrics/summary`

Ejemplo:

```bash
curl http://127.0.0.1:8000/api/metrics/summary
```

---

## 9. Métricas clave del sistema

La parte documental del proyecto planteaba métricas de evaluación. En la implementación también se refleja esa lógica con un endpoint de monitoreo.

Métricas importantes:

- tiempo promedio de primera respuesta
- tasa de resolución automática
- tasa de escalamiento a agente humano
- tasa de respuestas JSON válidas
- tasa de recontacto del cliente
- costo promedio por conversación

Estas métricas permiten evaluar si la IA está ayudando realmente a la operación y no solo generando respuestas genéricas/Dummy.

---

## 10. Configuración del entorno

### Requisitos

- Python 3.10+
- acceso a una API de OpenAI
- entorno virtual local

### Crear entorno virtual

```bash
cd "ruta/del/proyecto"
python3 -m venv .venv
source .venv/bin/activate
```

### Instalar dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Configurar .env

```env
OPENAI_API_KEY=tu_api_key_real
OPENAI_MODEL=gpt-6-sol
OPENAI_TIMEOUT=30
```

---

## 11. Cómo ejecutar la aplicación

```bash
source .venv/bin/activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Luego puedes abrir:

- Swagger UI: http://127.0.0.1:8000/docs
- Redoc: http://127.0.0.1:8000/redoc
- Estado de salud: http://127.0.0.1:8000/health

---

## 12. Modo de fallback

Si OpenAI no está disponible, la aplicación sigue respondiendo con una solución local. Esto ayuda a mantener la demo operativa y evitar un fallo total del sistema.

---

## 13. Valor del proyecto

Este repositorio no solo demuestra una integración básica con LLM. Demuestra una arquitectura de soporte realista porque:

- usa datos del negocio
- aplica reglas de negocio
- controla el formato de salida
- clasifica incidencias
- permite medición del desempeño
- define un camino claro para escalamiento humano

La diferencia importante es que aquí la IA actúa como apoyo a la operación, no como una caja negra sin control.

---

## 14. Resumen ejecutivo

EcoMarket AI Assistant es un sistema de atención al cliente que combina:

- data operativa
- prompts específicos para cada caso
- un modelo LLM
- validación estructurada
- métricas y escalamiento humano

Esto permite automatizar tareas repetitivas y hacer que el soporte sea más rápido, más claro y más controlado.

## 15. Autor

- Jhon Fredy Montenegro Rosero
- Estudiante MIAA
- A00411554
