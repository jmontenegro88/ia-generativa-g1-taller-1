# Fase 2 - Evaluación de fortalezas, limitaciones y riesgos éticos

## 1. Criterio de evaluación

La solución propuesta combina GPT-6 Sol, recuperación aumentada de información (RAG), búsqueda exacta para pedidos y supervisión humana. Por esa razón, sus beneficios y riesgos no dependen únicamente del modelo de lenguaje: también dependen de la calidad de los datos, el diseño de los prompts, los permisos, las reglas de negocio y la forma en que los agentes utilizan el sistema.

La evaluación debe considerar tres preguntas:

1. ¿Qué tareas puede mejorar la solución y bajo qué condiciones?
2. ¿En qué situaciones puede fallar o producir un resultado insuficiente?
3. ¿Qué controles deben existir antes de mostrar una respuesta al cliente?

Una respuesta automática no se considera exitosa solo porque sea rápida o esté bien redactada. También debe ser correcta, explicable, respetuosa, segura y apropiada para el nivel de riesgo de la solicitud.

## 2. Fortalezas

### Reducción del tiempo de respuesta

El asistente puede consultar automáticamente pedidos, políticas y catálogo. Esto evita que un agente tenga que responder manualmente cada solicitud repetitiva y permite que el cliente reciba una primera respuesta en segundos o minutos, en lugar de esperar hasta 24 horas.

El beneficio es especialmente importante para el 80 % de consultas repetitivas. Sin embargo, la velocidad solo representa una mejora real si la respuesta se basa en información actualizada. Una respuesta rápida pero incorrecta puede aumentar los reclamos y deteriorar la confianza del cliente.

### Disponibilidad continua

El servicio puede operar 24/7 en chat, correo y redes sociales, siempre que los canales se conecten al backend. Esto permite atender consultas fuera del horario laboral y absorber picos de demanda durante promociones, temporadas especiales o retrasos logísticos.

La disponibilidad continua no significa que todos los casos deban resolverse automáticamente. El sistema debe distinguir entre una respuesta informativa de bajo riesgo y una decisión que requiere la intervención de un agente.

### Cobertura del 80 % de consultas repetitivas

Las consultas de estado de pedido, devolución y características de productos tienen patrones frecuentes y pueden automatizarse con reglas claras y contexto actualizado. La búsqueda exacta puede resolver el número de seguimiento, mientras que RAG puede recuperar la política o la descripción de producto relevante.

Esta cobertura debe medirse con datos reales y no asumirse automáticamente. Algunas consultas aparentemente sencillas pueden ocultar un reclamo, un problema de seguridad o una solicitud de compensación.

### Respuestas consistentes

Las instrucciones de desarrollador, los esquemas JSON y las reglas de negocio ayudan a mantener un formato uniforme. El sistema puede utilizar un tono común, incluir los mismos campos y registrar la fuente de la información utilizada.

La consistencia también facilita la supervisión: los agentes pueden revisar respuestas con una estructura conocida y detectar más fácilmente cuándo falta un dato o cuándo debe activarse un escalamiento.

### Actualización sin reentrenamiento

Las políticas y datos se actualizan en las fuentes de recuperación. No es necesario reentrenar GPT-6 Sol cada vez que cambia un pedido o una política. Esto reduce el tiempo y el costo de mantenimiento frente a una solución que intentara almacenar toda la información dentro de los parámetros del modelo.

Esta fortaleza depende de que exista un proceso de actualización, versionado y validación de documentos. RAG no corrige por sí solo una fuente equivocada o desactualizada.

### Apoyo a los agentes

El sistema puede entregar resúmenes, fuentes y contexto al agente humano. El objetivo es aumentar su capacidad, no eliminar su criterio. Los agentes pueden dedicar más tiempo a quejas, problemas técnicos y casos que requieren empatía.

El diseño también puede mejorar la calidad del trabajo al presentar el historial relevante y sugerir una respuesta, pero la sugerencia no debe convertirse en una decisión automática. El agente debe poder editarla, rechazarla y conocer qué información la sustenta.

### Trazabilidad y medición

El uso de RAG permite registrar qué documentos o registros se recuperaron para construir una respuesta. Esto facilita auditorías, análisis de errores y correcciones de la base de conocimiento.

La trazabilidad debe incluir, como mínimo, el identificador de la conversación, la fuente consultada, la versión de la política utilizada, la decisión de escalar y la intervención final del agente, evitando almacenar datos personales innecesarios.

## 3. Limitaciones

### Dependencia de la calidad de los datos

Si el sistema de pedidos está equivocado o la política está desactualizada, el modelo puede redactar una respuesta incorrecta aunque siga bien las instrucciones. En este caso, el problema no se resuelve cambiando el prompt: se debe corregir la fuente y establecer responsables para mantenerla.

### Ambigüedad

Una consulta como "quiero devolverlo" no contiene suficiente información. El asistente debe pedir el número de pedido, el producto y el motivo cuando sean necesarios, no asumir datos ni seleccionar una política arbitraria.

### Casos complejos

Las quejas, problemas técnicos, compensaciones y situaciones emocionales pueden requerir empatía, autorización y criterio humano. El modelo puede redactar una respuesta amable, pero no tiene autoridad para decidir una excepción comercial ni para reemplazar la responsabilidad de un agente.

### Variabilidad del modelo

La generación de texto no es completamente determinista. Dos respuestas ante solicitudes similares pueden variar en tono o estructura. Se necesitan pruebas, validación, versiones fijadas del modelo y monitoreo continuo.

### Costos y dependencia externa

El uso de la API genera costos y requiere disponibilidad del proveedor. Deben existir límites de uso, manejo de errores y un plan de contingencia. También deben evaluarse latencia, límites de tasa, errores de red y aumentos de volumen durante campañas comerciales.

### Recuperación imperfecta

Un sistema RAG puede recuperar un fragmento irrelevante o no encontrar una regla si el documento fue dividido, etiquetado o indexado de forma deficiente. También puede recuperar dos versiones contradictorias de una política.

Por eso, la búsqueda semántica debe complementarse con filtros por versión y fecha, búsqueda por palabras clave y reglas deterministas para operaciones críticas.

### Límites de comprensión y lenguaje

El modelo puede interpretar de manera diferente expresiones regionales, errores de escritura, sarcasmo, mensajes breves o consultas en idiomas distintos. Esto puede afectar especialmente a clientes que utilizan accesibilidad asistida, traducción automática o formas no estándar de comunicación.

El sistema debe permitir que el cliente reformule la consulta y ofrecer un canal humano cuando no exista suficiente confianza.

### Falta de autoridad operativa

Generar una respuesta no equivale a ejecutar una acción. El modelo no debe cancelar pedidos, emitir reembolsos, cambiar direcciones ni modificar datos del cliente solamente porque lo solicite en lenguaje natural. Las operaciones con efectos reales deben pasar por funciones autorizadas, validaciones y, cuando corresponda, aprobación humana.

## 4. Riesgos éticos y controles

### Alucinaciones y desinformación

El modelo podría inventar un estado, una fecha, un enlace, una política o un beneficio. El riesgo es crítico cuando el cliente toma una decisión económica basándose en la respuesta o cuando la empresa adquiere una obligación que no puede cumplir.

**Controles:**

- Exigir evidencia recuperada para cada dato operativo.
- Usar salidas estructuradas y validar el esquema.
- Rechazar campos sin fuente o con información contradictoria.
- Incluir la versión o el identificador de la fuente.
- Derivar a un agente cuando no exista información suficiente.
- Probar explícitamente pedidos inexistentes, retrasados y contradictorios.

### Sesgo

El modelo o los datos históricos pueden producir diferencias injustificadas en el tono o en las soluciones ofrecidas a determinados grupos. El sesgo puede aparecer en los datos usados para entrenar el modelo, en las políticas de negocio, en el recuperador o en la interpretación de nombres, regiones, idiomas y estilos de escritura.

Por ejemplo, el sistema podría tratar con mayor sospecha una solicitud escrita con errores, ofrecer explicaciones menos completas a un cliente de determinada región o clasificar una expresión cultural como agresiva.

**Controles:**

- Probar casos con diferentes nombres, regiones, idiomas, tipos de clientes y estilos de comunicación.
- Comparar tasas de aprobación, escalamiento y tiempos de respuesta entre grupos.
- Revisar muestras con agentes y personas responsables de diversidad e inclusión.
- Evitar utilizar atributos sensibles para decidir beneficios o restricciones, salvo que exista una justificación legal y de negocio documentada.
- Permitir apelación y revisión humana.

### Privacidad

Las consultas pueden incluir nombres, direcciones, correos, historial de compras y datos de contacto. Enviar más información de la necesaria al modelo aumenta el impacto de una filtración, un error de configuración o un uso indebido.

**Controles:**

- Aplicar minimización de datos y enviar solo lo estrictamente necesario.
- Enmascarar datos no necesarios para redactar la respuesta.
- Separar identificadores internos de la conversación visible.
- Limitar registros, permisos de acceso y tiempo de retención.
- Cifrar datos en tránsito y en almacenamiento.
- Definir qué información puede aparecer en los registros de auditoría.
- Revisar las políticas vigentes de tratamiento y retención de datos del proveedor.
- Establecer mecanismos para atender solicitudes de acceso, corrección o eliminación cuando sean aplicables.
- Nunca incluir claves API en el repositorio.

### Seguridad, prompt injection y exfiltración de datos

Un cliente o documento podría incluir instrucciones que intenten cambiar las reglas del asistente, revelar información interna o hacer que el sistema ejecute una acción no autorizada. Este riesgo puede presentarse tanto en el mensaje del usuario como en documentos recuperados desde una fuente comprometida.

**Controles:**

- Separar instrucciones de desarrollador, entrada del usuario y contexto recuperado.
- Tratar los documentos recuperados como datos no confiables, no como instrucciones.
- Limitar las herramientas disponibles según el principio de mínimo privilegio.
- Validar parámetros antes de ejecutar cualquier función.
- No permitir que el modelo acceda a datos de otros clientes.
- Probar instrucciones de manipulación, solicitudes de secretos y contenido malicioso.
- Registrar y revisar intentos de abuso sin incluir información sensible innecesaria.

### Decisiones injustificadas sobre devoluciones

Una respuesta automática podría negar una devolución sin considerar un defecto, una excepción legal o una situación especial. Una clasificación incorrecta puede afectar económicamente al cliente y generar una experiencia injusta.

**Controles:** aplicar reglas explícitas, mostrar el motivo, citar la política aplicable, solicitar información faltante y escalar excepciones a una persona. El asistente debe diferenciar entre informar una política y ejecutar una decisión definitiva.

### Impacto laboral

Una automatización mal planteada podría aumentar la carga de supervisión, reducir la autonomía de los agentes o desplazar trabajadores sin capacitación ni participación en el diseño del sistema. También podría asignar a los agentes solo los casos más difíciles y emocionalmente desgastantes.

**Propuesta:** usar la IA para resolver solicitudes simples y preparar contexto. Los agentes deben conservar el control sobre escalamiento, compensaciones y casos sensibles. EcoMarket debe capacitar al personal, definir responsabilidades, medir la carga laboral y utilizar las correcciones de los agentes para mejorar el sistema, no para penalizarlos automáticamente.

### Falta de transparencia y consentimiento informado

El cliente puede no saber si conversa con una IA, qué datos se utilizan o por qué se tomó una decisión. Ocultar la automatización puede afectar la confianza y dificultar la reclamación de un error.

**Controles:** informar cuando interviene un asistente automático, explicar qué información se utilizó, ofrecer acceso a una persona y comunicar que una respuesta automática puede requerir revisión. Las decisiones con efectos económicos o contractuales deben tener una vía clara de apelación.

### Responsabilidad y rendición de cuentas

Una cadena automatizada puede dificultar determinar quién responde cuando una respuesta es incorrecta: el proveedor del modelo, el equipo de datos, el desarrollador, el área de servicio o la empresa. La responsabilidad frente al cliente no debe desaparecer por utilizar IA.

**Controles:** asignar un propietario del sistema, conservar registros de versión y fuente, documentar las reglas de negocio, aprobar cambios mediante revisión y mantener un procedimiento para corregir y notificar incidentes.

### Accesibilidad y trato digno

Una respuesta técnicamente correcta puede ser poco útil si usa lenguaje complejo, no contempla lectores de pantalla o no ofrece alternativas para clientes con necesidades específicas.

**Controles:** redactar con lenguaje claro, evitar tecnicismos innecesarios, probar diferentes canales y proporcionar alternativas de contacto humano. La accesibilidad debe formar parte de las pruebas de calidad, no ser una corrección posterior.

### Riesgo legal y regulatorio

Las respuestas sobre devoluciones, garantías, pagos o datos personales pueden tener implicaciones legales distintas según el país o la región. Una política interna no puede reemplazar las obligaciones legales aplicables.

**Control:** limitar el alcance del asistente, revisar los flujos con las áreas legal y de cumplimiento, identificar la región del pedido cuando sea necesario y escalar casos que impliquen derechos, disputas o reclamaciones formales.

### Dependencia tecnológica y continuidad del servicio

Una interrupción del proveedor, un cambio de modelo o una modificación de la API puede afectar la atención al cliente.

**Controles:** mantener una respuesta de contingencia, permitir la atención manual, fijar versiones del modelo cuando sea posible, monitorear cambios del proveedor y probar el sistema después de cada actualización.

## 5. Política de escalamiento

El sistema debe transferir la conversación cuando:

- No encuentra el pedido.
- Hay información contradictoria.
- El cliente expresa una queja grave.
- Se solicita una compensación no prevista.
- Existe riesgo legal, financiero o de seguridad.
- Se trata de un producto perecedero con posible defecto.
- La confianza de recuperación es baja.
- El cliente solicita hablar con una persona.
- La consulta puede producir una obligación económica o contractual.
- El modelo no puede producir una salida estructurada válida.
- El cliente manifiesta que la respuesta es incorrecta o insuficiente.

El escalamiento debe incluir el contexto utilizado, las fuentes consultadas, la respuesta propuesta y el motivo de transferencia. De esta manera, el agente no tiene que comenzar la conversación desde cero.

## 6. Métricas de control

- Tiempo promedio de primera respuesta.
- Porcentaje de consultas resueltas automáticamente.
- Porcentaje de escalamiento.
- Tasa de JSON inválido.
- Tasa de respuestas sin evidencia.
- Tasa de correcciones realizadas por agentes.
- Tasa de respuestas que contradicen la política vigente.
- Tasa de pedidos identificados incorrectamente.
- Satisfacción del cliente y tasa de recontacto.
- Diferencias de resultados entre grupos y canales.
- Costo promedio por conversación.
- Latencia y disponibilidad del servicio.
- Número y gravedad de incidentes de privacidad o seguridad.

Las métricas deben analizarse junto con muestras cualitativas. Una tasa alta de automatización no es positiva si aumenta los reclamos, las correcciones humanas o las diferencias injustificadas entre clientes.

## 7. Gobernanza y revisión continua

Antes de utilizar el sistema con clientes reales, EcoMarket debe definir:

- Quién es responsable de cada fuente de datos.
- Quién puede modificar prompts y políticas.
- Cómo se aprueban nuevas versiones.
- Qué casos requieren revisión humana obligatoria.
- Cuánto tiempo se conservarán las conversaciones.
- Cómo se reportan y corrigen errores.
- Qué pruebas deben ejecutarse antes de actualizar el modelo.

La evaluación debe repetirse cuando cambie el modelo, el prompt, la política de devoluciones, el esquema de datos o el proceso de atención. La solución no debe considerarse terminada después de una única prueba.

## 8. Conclusión de la Fase 2

La solución ofrece beneficios importantes: reduce tiempos de respuesta, amplía la disponibilidad, puede atender gran parte de las consultas repetitivas y ayuda a los agentes a concentrarse en casos complejos. No obstante, esos beneficios solo son aceptables si están acompañados de controles técnicos, humanos y organizacionales.

En la implementación, estas mismas consideraciones se aplican a los nuevos flujos de búsqueda de producto, consultas de política y clasificación de incidencias. La diferencia no está en el modelo ni en la arquitectura base, sino en la amplitud de casos que usa la misma capa de generación y la misma política de escalamiento humano para casos ambiguos o sensibles.

Las principales limitaciones son la dependencia de la calidad de los datos, la recuperación imperfecta, la variabilidad del modelo y la incapacidad de sustituir el criterio humano en decisiones sensibles. Los riesgos más importantes son las alucinaciones, los sesgos, la exposición de datos personales, la manipulación de instrucciones, las decisiones injustas y el impacto laboral.

Por esta razón, EcoMarket debe implementar la IA como un sistema de apoyo con límites claros, fuentes trazables y escalamiento humano. El objetivo no es automatizar el mayor número posible de conversaciones, sino automatizar de manera responsable las solicitudes de bajo riesgo y preservar la supervisión humana donde una respuesta incorrecta pueda afectar la dignidad, la privacidad, el dinero o los derechos del cliente.
