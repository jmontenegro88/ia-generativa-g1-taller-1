"""Bitácora de acciones del agente (observabilidad).

Cada llamada a una herramienta y cada turno del agente se registra como una
línea JSON en ``runtime/agent_actions.jsonl``. El formato JSONL permite leer el
archivo con ``tail``/``jq``, cargarlo en pandas o enviarlo a un colector de logs
sin transformaciones.
"""
from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import AGENT_ACTION_LOG

MAX_TEXT_CHARS = 300


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
        return value[:MAX_TEXT_CHARS] + "…"
    if isinstance(value, dict):
        return {key: _truncate(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate(item) for item in value]
    return value


class ActionLogger:
    """Registro append-only y seguro entre hilos."""

    def __init__(self, path: Path = AGENT_ACTION_LOG) -> None:
        self.path = path
        self._lock = threading.Lock()

    def log(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "evento": event,
            **_truncate(fields),
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return record

    def read_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        records = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def summary(self) -> dict[str, Any]:
        """Indicadores calculados a partir de la bitácora real (no valores fijos)."""
        records = self.read_recent(limit=100_000)
        tool_calls = [r for r in records if r.get("evento") == "tool_call"]
        turns = [r for r in records if r.get("evento") == "agent_turn"]
        decisions = Counter(
            r.get("decision") for r in tool_calls if r.get("decision")
        )
        latencies = [r["latencia_ms"] for r in turns if isinstance(r.get("latencia_ms"), (int, float))]
        return {
            "turnos": len(turns),
            "turnos_por_modo": dict(Counter(r.get("modo") for r in turns)),
            "llamadas_herramientas": len(tool_calls),
            "llamadas_por_herramienta": dict(Counter(r.get("herramienta") for r in tool_calls)),
            "errores_herramientas": sum(1 for r in tool_calls if not r.get("ok")),
            "decisiones_elegibilidad": dict(decisions),
            "etiquetas_emitidas": sum(
                1
                for r in tool_calls
                if r.get("herramienta") == "generar_etiqueta_devolucion"
                and r.get("ok")
                and not r.get("ya_existia")
            ),
            "escalamientos": sum(
                1 for r in tool_calls if r.get("herramienta") == "escalar_a_agente_humano" and r.get("ok")
            ),
            "fallos_llm": sum(1 for r in records if r.get("evento") == "llm_error"),
            "latencia_promedio_turno_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        }
