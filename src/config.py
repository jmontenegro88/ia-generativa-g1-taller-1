from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-sol")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "30"))

DATA_DIR = BASE_DIR / "data"
RAG_EMBEDDING_MODEL = os.getenv(
    "RAG_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
RAG_VECTOR_STORE_DIR = DATA_DIR / "chroma"
RAG_CHUNK_SIZE = 800
RAG_CHUNK_OVERLAP = 120
RAG_TOP_K = 4

# --- Proyecto final: agente de devoluciones ---------------------------------
# Directorio de estado generado en ejecución (etiquetas emitidas, bitácora de
# acciones). No se versiona.
RUNTIME_DIR = Path(os.getenv("AGENT_RUNTIME_DIR", str(BASE_DIR / "runtime")))
AGENT_ACTION_LOG = RUNTIME_DIR / "agent_actions.jsonl"
AGENT_STATE_STORE = RUNTIME_DIR / "estado_devoluciones.json"

# Reglas de negocio codificadas desde data/politica_devoluciones.pdf y
# data/politica_garantias.json.
RETURN_WINDOW_DAYS = 30
WARRANTY_DAYS = 90
LABEL_VALIDITY_DAYS = 14

AGENT_MAX_INPUT_CHARS = int(os.getenv("AGENT_MAX_INPUT_CHARS", "1500"))
AGENT_RECURSION_LIMIT = int(os.getenv("AGENT_RECURSION_LIMIT", "12"))


def agent_reference_date() -> date:
    """Fecha "de hoy" usada para calcular plazos.

    Se puede fijar con AGENT_REFERENCE_DATE=YYYY-MM-DD para que la demostración
    sea reproducible con los datos de ejemplo.
    """
    configured = os.getenv("AGENT_REFERENCE_DATE", "").strip()
    if configured:
        return date.fromisoformat(configured)
    return date.today()
