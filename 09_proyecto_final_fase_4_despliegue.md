# Proyecto final - Fase 4: despliegue de la aplicación

## Selección de la herramienta: Streamlit

| Criterio | Streamlit (seleccionado) | Gradio |
| --- | --- | --- |
| Chat | `st.chat_message` y `st.chat_input` nativos, con historial en `st.session_state` | `gr.ChatInterface`, muy rápido para un chat básico |
| Mostrar más que texto | En el mismo flujo de chat: etiqueta generada, botón de descarga, traza de herramientas (`st.json`), métricas (`st.metric`) y bitácora en la barra lateral | Posible con `gr.Blocks`, pero cada componente extra exige cablear entradas y salidas |
| Facilidad | Un script Python lineal; el agente se cachea con `st.cache_resource` | También simple; su fuerte es compartir demos de modelos con un enlace público |
| Encaje con el proyecto | Todo el código es Python y el agente ya es un objeto Python, así que no hace falta un servidor intermedio | Igual |

**Decisión:** Streamlit. La demostración necesita mostrar en la misma pantalla
la respuesta del agente, qué herramientas usó, la etiqueta generada y las
métricas de monitoreo. Streamlit hace eso con componentes nativos y menos código
que Gradio con `Blocks`.

## La interfaz (`app.py`)

- **Área de chat**: campo de texto para el mensaje y el historial de la
  conversación. Cada respuesta del agente muestra:
  - el modo usado (agente LLM o router por reglas) y la latencia;
  - un aviso si se usó el respaldo;
  - la etiqueta generada, con botón «Descargar etiqueta (.txt)»;
  - un desplegable «Herramientas usadas», con argumentos y resultado de cada
    llamada.
- **Barra lateral**:
  - motor del agente: automático, solo LLM o solo reglas;
  - cliente autenticado (simulado), para demostrar la autorización;
  - botón «Nueva conversación»;
  - botones con prompts de ejemplo para cada escenario de la demo;
  - métricas y bitácora de acciones en vivo.

## Cómo ejecutarla

```bash
cd "proyecto taller 1"
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # completar OPENAI_API_KEY; AGENT_REFERENCE_DATE=2026-10-27
streamlit run app.py
```

Se abre en http://localhost:8501. Sin una clave válida la aplicación funciona
igual con el router por reglas y lo indica en la barra lateral.

El agente también está disponible por API, para integrarlo con otros canales:

```bash
uvicorn src.main:app --reload --port 8000
curl -X POST http://127.0.0.1:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Quiero devolver el pedido ECO-10013, está nuevo y sin uso", "history": []}'
curl http://127.0.0.1:8000/api/agent/metrics
```

## Verificación de extremo a extremo

Verificaciones realizadas el 27/10/2026:

- `streamlit run app.py` levanta el servidor y responde HTTP 200.
- Con `streamlit.testing.v1.AppTest` se simuló la interfaz: el usuario escribió
  «Quiero devolver el pedido ECO-10013, está nuevo y sin uso». El agente
  respondió con la aprobación, la tarjeta de la etiqueta `RMA-18BA375B` y su
  texto descargable, y las métricas laterales se actualizaron (2 llamadas a
  herramientas, 1 etiqueta). El turno siguiente («Hola») se respondió sin
  herramientas y sin excepciones.