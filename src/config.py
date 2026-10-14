from __future__ import annotations

import os
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
