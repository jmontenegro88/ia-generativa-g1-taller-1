"""Interfaz web del agente de devoluciones de EcoMarket (Proyecto final, Fase 4).

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

import uuid

import streamlit as st

from src.agent import EcoMarketAgent
from src.config import OPENAI_MODEL, agent_reference_date
from src.retrieval import load_orders

st.set_page_config(page_title="EcoMarket · Asistente de devoluciones", page_icon="♻️", layout="wide")

EXAMPLES = {
    "Devolución elegible": "Quiero devolver el pedido ECO-10013, el pantalón está nuevo y sin uso.",
    "Falta información": "Quiero devolver mi pedido ECO-10024.",
    "No elegible (higiene abierto)": "¿Puedo devolver el pedido ECO-10020? Ya abrí el jabón.",
    "Fuera de plazo con defecto": "Quiero devolver ECO-10001, la botella no funciona, gotea.",
    "Pedido no entregado": "Quiero devolver ECO-10002, está nuevo.",
    "Pedido inexistente": "Quiero devolver el pedido ECO-99999, está nuevo.",
    "Estado de pedido": "¿Dónde está mi pedido ECO-10003?",
    "Pregunta de política (RAG)": "¿Cuántos días tengo para devolver un producto?",
    "Respuesta directa": "Hola, ¿qué puedes hacer por mí?",
    "Fuera de alcance": "¿Me recomiendas una película?",
}
TOOL_ICONS = {
    "consultar_estado_pedido": "📦",
    "verificar_elegibilidad_producto": "🔎",
    "generar_etiqueta_devolucion": "🏷️",
    "consultar_politicas": "📚",
    "escalar_a_agente_humano": "🧑‍💼",
}
MODE_LABELS = {
    "agente_llm": "Agente LLM",
    "router_reglas": "Router por reglas",
    "guardrail": "Guardrail de entrada",
    "error_llm": "Error del LLM",
}


@st.cache_resource(show_spinner="Inicializando el agente…")
def get_agent(mode: str) -> EcoMarketAgent:
    return EcoMarketAgent(mode=mode)  # type: ignore[arg-type]


@st.cache_data
def customer_options() -> list[str]:
    return sorted({order["customer_id"] for order in load_orders() if order.get("customer_id")})


def reset_conversation() -> None:
    st.session_state.messages = []
    st.session_state.session_id = uuid.uuid4().hex[:12]


if "messages" not in st.session_state:
    reset_conversation()

# ----------------------------------------------------------------- barra lateral
with st.sidebar:
    st.header("⚙️ Sesión")
    mode = st.radio(
        "Motor del agente",
        options=["auto", "llm", "reglas"],
        format_func={
            "auto": "Automático (LLM con respaldo)",
            "llm": "Solo LLM",
            "reglas": "Solo router por reglas",
        }.get,
        help="Automático usa GPT con herramientas y cae al router por reglas si el LLM no está disponible.",
    )
    agent = get_agent(mode)
    st.caption(f"Estado: **{agent.llm_status}**")
    st.caption(f"Modelo configurado: `{OPENAI_MODEL}` · Fecha de referencia: `{agent_reference_date()}`")

    customer = st.selectbox(
        "Cliente autenticado (simulado)",
        options=["(demo: sin validar titular)", *customer_options()],
        help="El agente solo puede actuar sobre pedidos del cliente de la sesión. "
        "El identificador lo fija el servidor, no el chat.",
    )
    customer_id = None if customer.startswith("(") else customer

    if st.button("🧹 Nueva conversación", use_container_width=True):
        reset_conversation()
        st.rerun()

    st.divider()
    st.subheader("💡 Ejemplos")
    for title, prompt in EXAMPLES.items():
        if st.button(title, key=f"ex-{title}", use_container_width=True, help=prompt):
            st.session_state.pending_prompt = prompt

    st.divider()
    st.subheader("📊 Monitoreo")
    metrics = agent.logger.summary()
    col1, col2 = st.columns(2)
    col1.metric("Turnos", metrics["turnos"])
    col2.metric("Herramientas", metrics["llamadas_herramientas"])
    col1.metric("Etiquetas", metrics["etiquetas_emitidas"])
    col2.metric("Escalamientos", metrics["escalamientos"])
    col1.metric("Errores tools", metrics["errores_herramientas"])
    col2.metric("Fallos LLM", metrics["fallos_llm"])
    with st.expander("Bitácora de acciones (últimas 15)"):
        for record in reversed(agent.logger.read_recent(15)):
            if record.get("evento") == "tool_call":
                st.markdown(
                    f"`{record['timestamp'][11:19]}` {TOOL_ICONS.get(record.get('herramienta'), '🔧')} "
                    f"**{record.get('herramienta')}** → `{record.get('codigo')}`"
                )
            elif record.get("evento") == "llm_error":
                st.markdown(f"`{record['timestamp'][11:19]}` ⚠️ LLM: `{record.get('tipo')}`")


# --------------------------------------------------------------------- chat
def render_trace(steps: list[dict]) -> None:
    if not steps:
        st.caption("Sin herramientas: respuesta directa.")
        return
    with st.expander(f"🔧 Herramientas usadas ({len(steps)})"):
        for index, step in enumerate(steps, start=1):
            result = step["resultado"]
            status = "✅" if result.get("ok") else "❌"
            st.markdown(
                f"**{index}. {TOOL_ICONS.get(step['herramienta'], '🔧')} `{step['herramienta']}`** "
                f"{status} `{result.get('codigo')}` · {step['latencia_ms']} ms"
            )
            st.json({"argumentos": step["argumentos"], "resultado": result}, expanded=False)


def render_assistant(message: dict, index: int) -> None:
    st.markdown(message["content"])
    meta = message.get("meta", {})
    caption = MODE_LABELS.get(meta.get("modo"), meta.get("modo", ""))
    if meta.get("latencia_ms") is not None:
        caption += f" · {meta['latencia_ms']} ms"
    st.caption(caption)
    if meta.get("aviso"):
        st.info(meta["aviso"], icon="ℹ️")
    label = meta.get("etiqueta")
    if label:
        with st.container(border=True):
            st.markdown(f"🏷️ **Etiqueta {label['numero_rma']}** · guía `{label['guia_devolucion']}`")
            st.code(label["contenido_texto"], language=None)
            st.download_button(
                "Descargar etiqueta (.txt)",
                data=label["contenido_texto"],
                file_name=f"{label['numero_rma']}.txt",
                key=f"dl-{index}",
            )
    render_trace(meta.get("herramientas", []))


st.title("♻️ EcoMarket · Asistente de devoluciones")
st.caption(
    "Agente de IA con herramientas: verifica la elegibilidad de una devolución, genera la etiqueta, "
    "consulta pedidos y políticas (RAG) y escala a una persona cuando hace falta."
)

for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            render_assistant(message, i)
        else:
            st.markdown(message["content"])

typed = st.chat_input("Escribe tu consulta, por ejemplo: «Quiero devolver el pedido ECO-10013»")
prompt = typed or st.session_state.pop("pending_prompt", None)

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    with st.chat_message("assistant"):
        with st.spinner("El agente está trabajando…"):
            try:
                result = agent.chat(
                    prompt,
                    history=history,
                    customer_id=customer_id,
                    session_id=st.session_state.session_id,
                )
                reply = {"role": "assistant", "content": result.respuesta, "meta": result.to_dict()}
            except Exception as exc:  # última barrera: la interfaz nunca se rompe
                reply = {
                    "role": "assistant",
                    "content": "Ocurrió un error inesperado al procesar tu solicitud. Intenta de nuevo.",
                    "meta": {"modo": "error", "aviso": type(exc).__name__},
                }
        render_assistant(reply, len(st.session_state.messages) + 1)
    st.session_state.messages += [{"role": "user", "content": prompt}, reply]
    # Refresca las métricas de la barra lateral.
    st.rerun()
