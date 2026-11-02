# EcoMarket AI Assistant

Este proyecto implementa un asistente de demostración para EcoMarket con una arquitectura basada en IA generativa, recuperación de contexto y validación estructurada de respuestas. La solución cubre escenarios de soporte sobre pedidos, devoluciones, catálogo, políticas y clasificación de incidencias.

La idea principal es combinar datos operativos del negocio con prompts bien definidos y el modelo seleccionado en la parte documental, GPT-6 Sol, para responder con precisión, control y trazabilidad, evitando que el modelo invente información.

## Entrega del Proyecto Final: agente de IA para devoluciones

El asistente ahora ejecuta el proceso de devolución: verifica la elegibilidad
del producto y genera la etiqueta de devolución. Usa un agente LangChain con
herramientas y una interfaz web en Streamlit.

- [Fase 1: diseño de la arquitectura del agente](./06_proyecto_final_fase_1_arquitectura.md):
  herramientas, RAG como herramienta, router de respaldo, elección de LangChain
  y diagrama de flujo.
- [Fase 2: implementación y conexión de componentes](./07_proyecto_final_fase_2_implementacion.md):
  estructura del código, manejo de éxito y error, evaluación del comportamiento.
- [Fase 3: análisis crítico y propuestas de mejora](./08_proyecto_final_fase_3_analisis_critico.md):
  riesgos éticos y de seguridad, monitoreo y alertas, nuevas funcionalidades.
- [Fase 4: despliegue de la aplicación](./09_proyecto_final_fase_4_despliegue.md):
  elección de Streamlit, ejecución y guion del video.

Inicio rápido:

```bash
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py                      # interfaz web en http://localhost:8501
python scripts/evaluar_agente.py          # evaluación de comportamiento (17 casos)
python -m pytest -q                       # pruebas automatizadas
```

| Herramienta del agente | Función |
| --- | --- |
| `verificar_elegibilidad_producto` | Aplica las reglas de la política de devoluciones y garantías al pedido |
| `generar_etiqueta_devolucion` | Emite RMA, guía y etiqueta; re-verifica la elegibilidad antes de emitir |
| `consultar_estado_pedido` | Estado, fecha y transportadora del pedido |
| `escalar_a_agente_humano` | Crea un ticket para casos que requieren revisión |
| `consultar_politicas` | RAG del Taller 2 (Chroma) incorporado como herramienta |

## Entrega del Taller 2

- [Fase 1: componentes RAG](./03_fase_1_componentes_rag.md)
- [Fase 2: base de conocimiento y chunking](./04_fase_2_base_conocimiento.md)
- [Fase 3: integración, ejecución y limitaciones](./05_fase_3_integracion_y_limitaciones.md)

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

La aplicación implementa una arquitectura híbrida con estas capas:

- recuperación exacta de pedidos desde archivos JSON
- recuperación semántica con LangChain y Chroma para políticas y catálogo
- búsqueda exacta por nombre o categoría en el catálogo
- prompt engineering para cada caso de uso
- validación de salida con esquemas JSON estrictos
- escalamiento seguro si falta el contexto o no está disponible la generación
- endpoints específicos para cada flujo de soporte

El índice vectorial se crea de forma local en `data/chroma/` a partir de una
representación compatible de cada política y `data/productos.json`. Las
políticas se responden con fragmentos recuperados; para productos, el modelo
compara el catálogo completo tras comprobar que existen fichas indexadas. Los
pedidos no se vectorizan: se consultan por coincidencia exacta de su número de
seguimiento. Los detalles de selección, segmentación e indexación están en las
fases del Taller 2 enlazadas arriba.

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
- El cliente puede consultar productos por nombre, categoría o descripción en lenguaje natural
- Para consultas semánticas, Chroma comprueba la disponibilidad de fichas indexadas y el modelo compara la solicitud con el catálogo completo; la similitud vectorial no decide por sí sola qué producto se ofrece
- La identidad del producto se evalúa aparte de sus atributos: el sistema puede identificar el producto y aclarar cuando la ficha no confirma un detalle preguntado
- El sistema devuelve información útil sobre el producto y su contexto

#### Consulta de política
- El usuario puede hacer preguntas sobre reglas del negocio
- El asistente responde aplicando la política disponible y señala si requiere revisión humana

#### Triage o clasificación de incidencias
- Se clasifica la solicitud en tipos como devolución, entrega, problema de producto o caso general
- Se prioriza la incidencia y se indican pasos de resolución

#### Métricas del servicio
- Se expone un resumen demostrativo de KPIs; son valores fijos, no métricas obtenidas de conversaciones reales

---

## 3. Arquitectura general

El flujo general del sistema es:

1. El cliente hace una petición al backend y FastAPI valida la entrada.
2. El backend busca el pedido por número exacto, recupera fragmentos de una
   política o inicia la búsqueda semántica de productos.
3. El prompt recibe el contexto correspondiente: pedido estructurado, fragmentos
   de política o catálogo completo.
4. OpenAI responde en JSON estructurado y la salida se valida con Pydantic.
5. Se devuelven la respuesta y sus fuentes, o se aplica el manejo de fallback
   definido para ese flujo.

```text
Cliente HTTP
   ↓
FastAPI
   ├─ pedido: búsqueda exacta por seguimiento en pedidos.json
   ├─ política: LangChain + Chroma → fragmentos y fuentes
   └─ producto: Chroma → comprobación de fichas; catálogo completo al modelo
   ↓
Prompt específico del flujo
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
├── app.py                      # Proyecto final: interfaz Streamlit
├── scripts/
│   └── evaluar_agente.py       # Proyecto final: evaluación de comportamiento
├── runtime/                    # generado: etiquetas, tickets y bitácora (no se versiona)
├── data/
│   ├── pedidos.json
│   ├── productos.json
│   ├── politica_devoluciones.pdf
│   ├── politica_envios.docx
│   └── politica_garantias.json
├── src/
│   ├── agent.py                # Proyecto final: agente LangChain + router de respaldo
│   ├── agent_tools.py          # Proyecto final: herramientas y reglas de devolución
│   ├── action_log.py           # Proyecto final: bitácora y métricas
│   ├── return_registry.py      # Proyecto final: etiquetas y tickets simulados
│   ├── config.py
│   ├── knowledge_base.py
│   ├── main.py
│   ├── models.py
│   ├── openai_client.py
│   ├── prompts.py
│   └── retrieval.py
├── tests/
│   ├── test_agent.py
│   ├── test_agent_tools.py
│   ├── test_knowledge_base.py
│   └── test_rag_routes.py
├── 01_fase_1_modelo.md
├── 02_fase_2_riesgos.md
├── 03_fase_1_componentes_rag.md
├── 04_fase_2_base_conocimiento.md
├── 05_fase_3_integracion_y_limitaciones.md
├── 06_proyecto_final_fase_1_arquitectura.md
├── 07_proyecto_final_fase_2_implementacion.md
├── 08_proyecto_final_fase_3_analisis_critico.md
├── 09_proyecto_final_fase_4_despliegue.md
└── .venv/
```

### Papel de cada parte

- `src/main.py`: API principal con los endpoints
- `src/knowledge_base.py`: carga, segmentación, indexación y recuperación de documentos
- `src/models.py`: modelos Pydantic de entrada y salida
- `src/prompts.py`: construcción de prompts para cada flujo
- `src/openai_client.py`: cliente OpenAI y validación de schema JSON
- `src/retrieval.py`: lectura y búsqueda del contexto
- `data/pedidos.json`: datos de pedidos para el soporte operativo
- `data/productos.json`: catálogo de productos
- `data/politica_devoluciones.pdf`, `data/politica_envios.docx` y
  `data/politica_garantias.json`: fuentes de políticas que se cargan en la base
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
- fichas del catálogo con nombre, descripción, categoría, precio y otros datos
- comparación de la intención del cliente con todos los productos disponibles
- una aclaración cuando la ficha no documenta la característica preguntada

La búsqueda vectorial no confirma una coincidencia: la selección semántica la
realiza el modelo comparando el catálogo completo. El backend valida el nombre
seleccionado y devuelve los atributos y la fuente del registro correspondiente.

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

La data es fundamental porque el modelo no debe “memorizar” la lógica del
negocio. La información se recupera desde los archivos del proyecto.

### `data/pedidos.json`

Contiene 30 registros de ejemplo para probar el flujo de pedidos. Cada registro incluye:
- número de seguimiento
- estado
- fecha estimada
- transportista
- enlace de rastreo
- producto relacionado

Los códigos de seguimiento van de `ECO-10001` a `ECO-10030`. El archivo es una
fuente local de prueba, no una conexión a pedidos en operación; sus enlaces de
rastreo usan el dominio de ejemplo.

### `data/productos.json`

Contiene información del catálogo con:
- nombre
- descripción y uso principal
- categoría
- precio
- condición
- si es personalizado

El catálogo incluye jabones de distintos tipos, camisetas, pantalones,
botellas, termos y recipientes para alimentos, entre otras categorías. Sus
descripciones detallan el uso principal para mejorar la comparación de consultas
semánticas con cada producto. En esta versión contiene 68 fichas con SKU únicos.

### Políticas de conocimiento

Las fuentes oficiales de políticas son `data/politica_devoluciones.pdf`,
`data/politica_envios.docx` y `data/politica_garantias.json`, para devoluciones,
envíos y garantías, respectivamente. Se editan directamente en sus formatos
correspondientes; no dependen de copias Markdown ni de un paso de conversión.

La diferencia clave es que el LLM nunca debe tomar decisiones basadas solo en su memoria. Siempre debe trabajar con contexto explícito y fuente documental.

Las políticas y el catálogo se recuperan semánticamente con embeddings
multilingües locales. El índice se reconstruye al detectar cambios en los
archivos fuente. Los pedidos continúan en la consulta exacta y no se envían al
índice vectorial.

### Formatos de documentos de conocimiento

El cargador de la base admite políticas Markdown (`.md`), PDF (`.pdf`), Word
Open XML (`.docx`) y documentos JSON con un campo `contenido` de texto. El
catálogo de productos se carga como JSON. En esta entrega, las tres políticas
oficiales están directamente en PDF, DOCX y JSON, respectivamente.

Si para una categoría existen varias representaciones, se indexa solo una para
evitar duplicar la misma política. El orden de preferencia es PDF, DOCX, JSON y
Markdown. El índice de Chroma se reconstruye automáticamente en la siguiente
consulta cuando detecta cambios en los archivos fuente. Para ejecutar pruebas
con un índice limpio, detén la API y elimina el directorio `data/chroma/`; la
aplicación lo volverá a crear al procesar la siguiente consulta.

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
    "tracking_number": "ECO-10030",
    "customer_id": "CUST-1030",
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

### 7) Agente de devoluciones (Proyecto final)

`POST /api/agent/chat`: conversación con el agente. `history` lleva los turnos
anteriores y `customer_id` es el cliente de la sesión.

```bash
curl -X POST "http://127.0.0.1:8000/api/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quiero devolver el pedido ECO-10013, está nuevo y sin uso",
    "history": [],
    "customer_id": "CUST-1013"
  }'
```

`GET /api/agent/actions?limit=20` devuelve la bitácora reciente.
`GET /api/agent/metrics` devuelve métricas calculadas desde esa bitácora.

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

- Python 3.10+ (LangChain 1.x lo requiere)
- clave/modelo de OpenAI para generación normal (opcional para probar los fallbacks)
- conexión a internet la primera vez para descargar el modelo de embeddings
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

### Ejecutar pruebas

```bash
python -m pytest -q
# o bien
python -m unittest discover -s tests -v
```

### Configurar `.env`

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-6-sol
OPENAI_TIMEOUT=30
RAG_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
AGENT_REFERENCE_DATE=2026-10-27
```

`AGENT_REFERENCE_DATE` fija la fecha «de hoy» con la que el agente calcula los
plazos de devolución. Así la demostración da los mismos resultados con los
datos de ejemplo, sin depender del día en que se ejecute. Si no se define, se
usa la fecha del sistema.

Se puede copiar `.env.example` como punto de partida. No es necesario ejecutar
un modelo local de generación: se conserva GPT-6 Sol para mantener la
integración definida en el Taller 1, mientras que los embeddings multilingües
se calculan localmente para las consultas en español.

---

## 11. Cómo ejecutar la aplicación

Interfaz web del agente (Proyecto final):

```bash
source .venv/bin/activate
streamlit run app.py
```

API REST:

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

Si OpenAI no está disponible, el estado del pedido y las búsquedas exactas de
productos pueden responderse con datos locales. Una búsqueda semántica de
productos que requiere comparar el catálogo responde con error de servicio para
no elegir arbitrariamente. Las consultas de política muestran los fragmentos
recuperados y solicitan revisión humana; una devolución no se marca elegible sin
evaluación del modelo. Si no se recupera una política, el caso se escala en vez
de completar la respuesta con reglas supuestas.

La carga local de embeddings requiere descargar el modelo la primera vez. Si
falla esa inicialización o Chroma, el error de recuperación se muestra como un
fallo del endpoint; no se sustituye silenciosamente por datos inventados.

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
