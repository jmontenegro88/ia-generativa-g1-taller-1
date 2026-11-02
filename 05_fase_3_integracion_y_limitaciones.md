# Taller 2 - Fase 3: integración, ejecución y limitaciones

## Flujo implementado

`src/knowledge_base.py` extrae texto de políticas Markdown, PDF, DOCX y JSON,
crea documentos LangChain desde las políticas y el catálogo, los divide y
mantiene el índice persistente de Chroma. Las consultas
de políticas reciben fragmentos recuperados con sus fuentes; en productos, el
backend fija la fuente de respuesta al SKU seleccionado del catálogo.

- `/api/policies/answer`: recupera fragmentos de política antes de construir el
  prompt de generación; acepta `category` con valores `devoluciones`, `envios`
  o `garantias` para filtrar el documento.
- `/api/returns/evaluate`: combina el producto encontrado en el catálogo con
  fragmentos de la política de devoluciones.
- `/api/products/search`: resuelve nombres y categorías desde el catálogo. Para
  una consulta en lenguaje natural, usa Chroma para comprobar que hay fichas
  indexadas y el modelo compara la consulta con todo el catálogo; la cercanía
  vectorial no se considera confirmación. El backend valida el producto
  seleccionado y sus datos contra el registro canónico.
- `/api/orders/status`: continúa usando búsqueda exacta por número de
  seguimiento en los 30 registros de ejemplo de `data/pedidos.json`; no usa
  embeddings para decidir qué pedido consultar. No está conectado a un sistema
  de pedidos en tiempo real.
- `/api/support/triage`: clasifica solicitudes; no tiene una base documental de
  quejas o procedimientos adicional que se pueda citar en este proyecto.

En todos los flujos con documentos, la lista de `fuentes` de la respuesta se
reemplaza por las fuentes recuperadas por el backend, no por texto libre que el
modelo pudiera inventar.

## Requisitos y arranque

Se requiere Python 3.10 o superior, dependencias de `requirements.txt` (incluidos
los lectores de PDF y DOCX), acceso a Hugging Face durante la primera carga del
modelo de embeddings y, para generación normal, una clave/modelo válidos de
OpenAI.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Configurar `OPENAI_API_KEY` en `.env` si se dispone de credenciales y ejecutar:

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

La descarga inicial del modelo de embeddings puede tardar y requiere conexión a
internet. Ejemplos de consultas y documentación interactiva están en el
`README.md` y en `/docs`.

Las políticas oficiales se mantienen directamente en PDF, DOCX y JSON dentro de
`data/`. Al modificarlas, Chroma detecta el cambio y reconstruye el índice al
recibir la siguiente consulta. Para comenzar una prueba con el índice vacío,
detén la API y elimina `data/chroma/`; la aplicación lo crea de nuevo al
procesar una consulta.

## Pruebas locales

Desde el directorio del proyecto:

```bash
python -m unittest discover -s tests -v
```

Las pruebas unitarias validan la preparación de documentos y los flujos de API
con recuperación/generación simuladas. No sustituyen una evaluación de
recuperación semántica con el modelo real ni una prueba de la Responses API.

## Limitaciones y supuestos

- El índice es local a una instancia y no coordina cambios entre varias
  réplicas. Es adecuado para el taller, no para alta disponibilidad.
- El modelo de embeddings se ejecuta en CPU para mantener el comportamiento
  portable; el primer uso requiere descargar sus pesos.
- El cargador soporta los formatos concretos `.md`, `.pdf`, `.docx` y `.json`;
  esto demuestra interoperabilidad entre tipos comunes, no lectura automática
  de cualquier formato imaginable. JSON de política debe incluir un campo
  `contenido` de texto.
- `GPT-6 Sol` depende de la disponibilidad, versión y credenciales configuradas
  para la Responses API. No se ha hecho una llamada real durante las pruebas.
- Si OpenAI no está disponible, una consulta de política muestra fragmentos
  recuperados y pide revisión humana; una devolución no se declara elegible sin
  evaluación del modelo. Los pedidos y las búsquedas exactas de productos
  pueden usar respuestas locales. Una consulta semántica que requiere comparar
  el catálogo no selecciona un producto sin generación disponible y responde
  con error de servicio.
- Si no se recupera una política, las consultas de política y devolución se
  escalan; no se rellena el vacío con una regla inventada.
- No hay umbral de similitud calibrado, conjunto de evaluación, monitoreo de
  deriva, autenticación, autorización por cliente ni integración con un sistema
  de pedidos productivo. Los pedidos y métricas presentes son de demostración.
- Antes de producción hacen falta validación de fuentes, revisión de privacidad,
  pruebas de acceso, respaldo del índice, métricas reales y revisión humana de
  excepciones.
