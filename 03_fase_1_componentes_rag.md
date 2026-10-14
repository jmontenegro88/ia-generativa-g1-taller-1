# Taller 2 - Fase 1: selección de componentes RAG

## Decisión

EcoMarket conserva `GPT-6 Sol` como modelo de generación. Esto mantiene continuidad con la arquitectura y la integración con la Responses API ya planteadas. La recuperación se realiza por separado con embeddings multilingües ejecutados localmente, adecuados para consultas en
español, y ChromaDB como índice persistente.

La propuesta separa generación y recuperación:

| Componente | Selección | Función |
| --- | --- | --- |
| LLM | `GPT-6 Sol` mediante Responses API | Redactar respuestas estructuradas con contexto recuperado |
| Embeddings | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Codificar preguntas y fragmentos en vectores multilingües |
| Base vectorial | ChromaDB local y persistente | Guardar e indexar los fragmentos de políticas y catálogo |
| Framework | LangChain | Cargar documentos, dividirlos y conectar el retriever con Chroma |

Se conserva GPT-6 Sol para generar las respuestas y se ejecutan localmente solo
los embeddings. Así se mantiene la integración definida en el Taller 1 sin
añadir y configurar un segundo modelo generativo, que no es necesario para este
flujo.

## Modelo de embeddings

Se elige un modelo multilingüe de Sentence Transformers porque el contenido y
las consultas de EcoMarket están en español. Es de pesos abiertos, se ejecuta
localmente y no factura una llamada de embeddings por consulta. Su tamaño
moderado es adecuado para el prototipo y evita enviar los documentos de negocio
a un segundo proveedor solo para vectorizarlos.

Frente a un embedding entrenado solo para inglés, el modelo multilingüe es una
mejor correspondencia inicial para recuperar consultas en español. La precisión
real para el vocabulario de EcoMarket aún no está medida y no se da por
garantizada: se debe comparar recall con consultas y fragmentos de referencia
antes de una decisión productiva.

La contrapartida es el uso de memoria y CPU local, además de una descarga inicial
de los pesos desde Hugging Face. El nombre del modelo se configura con
`RAG_EMBEDDING_MODEL`. Esta selección es una decisión razonada para el taller,
no el resultado de un benchmark propio; antes de producción se debe medir
recall con preguntas reales revisadas por EcoMarket.

Los embeddings no generan la respuesta y no sustituyen a `GPT-6 Sol`. Son una
representación usada para localizar texto semánticamente relacionado.

## Base vectorial: alternativas

| Opción | Ventajas para EcoMarket | Costos y limitaciones |
| --- | --- | --- |
| **ChromaDB (seleccionada)** | Fácil de ejecutar localmente, persistencia en disco, integración directa con LangChain; apropiada para el volumen de demostración del proyecto | La aplicación administra el almacenamiento y las copias; una instancia local no ofrece por sí sola escalado distribuido ni alta disponibilidad |
| Pinecone | Servicio administrado, útil para despliegues que requieren operar un índice remoto y escalar sin administrar el motor local | Depende de un servicio externo, de conectividad y de un plan/costo; requiere revisar transferencia y tratamiento de los documentos |
| Weaviate | Alternativa con despliegue autogestionado o administrado y capacidades de búsqueda configurables | Mayor superficie de configuración y operación que necesita justificar el volumen y requisitos de producción |

Chroma se elige por simplicidad y costo de infraestructura para un taller local.
El índice se persiste en `data/chroma/`, que no se versiona porque se puede
reconstruir desde los archivos fuente. Para producción se evaluaría una base
administrada o un servicio desplegado con respaldo, control de acceso y
disponibilidad definidos.

## Arquitectura

```text
Consulta
  -> búsqueda exacta si es un número de seguimiento
  -> retriever semántico LangChain para políticas o fichas de producto
  -> contexto de política con fragmentos y fuente; catálogo estructurado completo para comparar productos
  -> GPT-6 Sol / Responses API
  -> validación Pydantic y respuesta con fuentes
```

Los pedidos no se buscan por similitud semántica: su número requiere coincidencia
exacta y sus estados son operativos y cambiantes. Este flujo conserva la
arquitectura híbrida documentada en el Taller 1.

## Suposiciones

- Los datos de `data/` son de demostración y el equipo de EcoMarket es responsable
  de mantenerlos correctos.
- Las consultas factuales se limitan a la política y los atributos del catálogo
  disponibles en esos archivos.
- La API de OpenAI y la clave configurada son necesarias para generación normal.
  Sin ellas, el servicio usa las respuestas locales seguras documentadas en la
  Fase 3; no se simula una respuesta generada por el LLM.
