# Taller 2 - Fase 2: base de conocimiento

## Fuentes disponibles y alcance

La base contiene tres tipos documentales de políticas relevantes, además del
catálogo y los registros operativos:

| Tipo | Fuente actual | Uso en la solución |
|---|---|---|
| Política de devoluciones | `data/politica_devoluciones.pdf` | Recuperación semántica para consultas de devolución |
| Política de envíos | `data/politica_envios.docx` | Recuperación semántica para preguntas sobre despacho, tiempos y seguimiento |
| Política de garantías | `data/politica_garantias.json` | Recuperación semántica para preguntas de cobertura, revisión y escalamiento |
| Catálogo de productos | `data/productos.json` | Un documento por producto; complementa la búsqueda exacta de producto |
| Registros de pedidos | `data/pedidos.json` | Búsqueda exacta por seguimiento en la API; no se vectoriza |

Los archivos PDF, DOCX y JSON de la tabla son las fuentes oficiales y se editan
directamente. El cargador también admite `.md` como formato compatible, aunque
las políticas de esta entrega no dependen de archivos Markdown. Si encuentra
copias de una categoría en varios formatos, elige una sola con esta prioridad:
PDF, DOCX, JSON y Markdown. Así se evitan fragmentos duplicados.

El catálogo actual contiene 68 productos con descripciones de uso y SKU únicos.
El archivo de pedidos contiene 30 registros de ejemplo para probar la consulta
operativa; no representa una integración con pedidos activos.

Las políticas de envíos y garantías describen los criterios definidos para el
caso de EcoMarket y se indexan junto con la política de devoluciones.

Los pedidos se excluyen intencionalmente del índice semántico: son datos
operativos que cambian, deben encontrarse por identificador exacto y contienen
identificadores de clientes. Se consultan desde el archivo estructurado.

El sistema admite el filtro opcional `category` en `POST /api/policies/answer`:
usa `devoluciones`, `envios` o `garantias` para restringir la recuperación a
una política y reducir la mezcla entre temas. La evaluación de devoluciones
aplica siempre el filtro `devoluciones`.

## Estrategia de segmentación

El código usa `RecursiveCharacterTextSplitter` de LangChain con fragmentos de
hasta 800 caracteres y solapamiento de 120 caracteres.

- **Políticas en PDF, DOCX y JSON:** el cargador extrae texto del PDF con
  `pypdf`, párrafos del DOCX con `python-docx` y el campo `contenido` del JSON.
  Tras extraer el texto, cada archivo es una categoría documental independiente;
  la división recursiva prioriza separaciones naturales
  (párrafos y líneas) para mantener juntas las reglas relacionadas. El
  solapamiento reduce el riesgo de perder contexto cuando una regla queda cerca
  del límite de un fragmento.
- **Markdown:** es un formato compatible para futuras fuentes o casos de prueba;
  no es necesario para cargar las tres políticas actuales.
- **Catálogo JSON:** se convierte cada registro en un documento independiente
  antes de dividir. Así, atributos de productos diferentes no quedan mezclados;
  los documentos cortos permanecen completos.
- **Pedidos JSON:** no se fragmentan para el índice vectorial. Se consultan como
  registros estructurados por número de seguimiento, evitando similitudes
  ambiguas y la indexación innecesaria de identificadores personales.

Un tamaño fijo que corte sin respetar separadores puede partir una excepción o
separar un atributo de su producto. La división solo por párrafos conserva
bien las reglas cortas, pero genera fragmentos desiguales y no limita los
párrafos largos. La estrategia recursiva respeta primero separadores naturales
y aplica el límite de tamaño cuando hace falta; junto con un documento por
producto, es un punto de partida para el tamaño actual de estas fuentes y
requiere reevaluación si crece el corpus.

## Indexación y actualización

1. Extraer una representación por política desde los archivos compatibles y
   leer el catálogo JSON en UTF-8.
2. Asociar tipo, categoría y fuente a cada política. Cada producto conserva su
   SKU.
3. Dividir el contenido y codificar los fragmentos con el modelo multilingüe
   elegido en la Fase 1.
4. Guardar vectores y fragmentos en la colección persistente
   `ecomarket_knowledge` de Chroma.
5. Recuperar hasta cuatro fragmentos para consultas de políticas, filtrando por
   tipo documental y, cuando corresponde, por categoría. Para una consulta
   semántica de producto, Chroma consulta las fichas indexadas; si hay
   resultados, el modelo compara la solicitud con el catálogo completo para que
   una paráfrasis no quede limitada por el orden de similitud vectorial.
6. Incluir en el prompt de políticas los fragmentos y sus fuentes. Para
   productos, se omiten los fragmentos vectoriales del prompt porque pueden
   sesgar la selección hacia un vecino débil; se proporciona el catálogo
   estructurado completo y la fuente de respuesta se fija al SKU seleccionado.

La aplicación calcula una firma de las políticas seleccionadas, el catálogo,
el modelo y los parámetros de fragmentación. Si cambia alguna de esas entradas,
reconstruye el índice local. Los archivos PDF, DOCX y JSON se actualizan
directamente; `data/chroma/` es un artefacto regenerable, no una nueva fuente de
verdad. Para probar desde cero, se puede borrar `data/chroma/` con la API
detenida; la siguiente consulta vuelve a crear el índice.

## Limitaciones de la base actual

- Las políticas describen el caso de estudio y no sustituyen la revisión de las
  condiciones legales y comerciales aplicables antes de su uso en producción.
- Las 68 fichas del catálogo son insuficientes para representar un catálogo
  comercial completo; sus precios, descripciones y disponibilidad deben
  mantenerse desde una fuente autorizada.
- No hay fuentes aprobadas para pagos, preguntas frecuentes ni inventario en
  tiempo real. El asistente no debe afirmar esos datos sin documentación nueva.
- La relevancia semántica debe evaluarse con consultas etiquetadas. El modelo
  compara el catálogo completo para evitar que un vecino vectorial débil se
  reporte como producto encontrado. Esta estrategia permite considerar
  paráfrasis que no estén entre los primeros vecinos, pero enviar el catálogo
  completo al modelo aumenta con el tamaño del catálogo y debe reevaluarse si
  crece considerablemente.
- Los 30 pedidos locales sirven para pruebas de búsqueda exacta; no deben
  interpretarse como información operativa vigente. Los enlaces usan un dominio
  de ejemplo y no consultan a una transportadora real.
- Una fuente desactualizada produce una recuperación desactualizada; RAG no
  valida por sí solo la autoridad de los documentos.
