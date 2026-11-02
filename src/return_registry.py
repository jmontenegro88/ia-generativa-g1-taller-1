"""Registro simulado de etiquetas de devolución y tickets de escalamiento.

Representa el "sistema externo" de logística inversa y la mesa de ayuda. Se
persiste en un JSON local para que las operaciones sean idempotentes entre
reinicios: generar dos veces la etiqueta de un mismo pedido devuelve la misma.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from src.config import AGENT_STATE_STORE


class ReturnRegistry:
    def __init__(self, path: Path = AGENT_STATE_STORE) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"etiquetas": {}, "tickets": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        data.setdefault("etiquetas", {})
        data.setdefault("tickets", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    def get_label(self, tracking_number: str) -> dict[str, Any] | None:
        with self._lock:
            return self._load()["etiquetas"].get(tracking_number)

    def save_label(self, tracking_number: str, label: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Guarda la etiqueta si no existe. Devuelve (etiqueta, ya_existia)."""
        with self._lock:
            data = self._load()
            existing = data["etiquetas"].get(tracking_number)
            if existing:
                return existing, True
            data["etiquetas"][tracking_number] = label
            self._save(data)
            return label, False

    def add_ticket(self, ticket: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with self._lock:
            data = self._load()
            existing = next(
                (t for t in data["tickets"] if t.get("clave") == ticket.get("clave")),
                None,
            )
            if existing:
                return existing, True
            ticket = {**ticket, "numero_ticket": f"TCK-{len(data['tickets']) + 1:05d}"}
            data["tickets"].append(ticket)
            self._save(data)
            return ticket, False
