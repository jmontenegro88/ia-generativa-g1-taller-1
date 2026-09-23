from __future__ import annotations

import json
from typing import Any, Dict, Optional

from src.config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TIMEOUT


def _strict_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a Pydantic JSON schema to the strict Responses API format."""
    normalized = dict(schema)
    if normalized.get("type") == "object":
        properties = normalized.get("properties", {})
        normalized["additionalProperties"] = False
        normalized["required"] = list(properties.keys())
        normalized["properties"] = {
            name: _strict_schema(value) if isinstance(value, dict) else value
            for name, value in properties.items()
        }
    if "$defs" in normalized:
        normalized["$defs"] = {
            name: _strict_schema(value) if isinstance(value, dict) else value
            for name, value in normalized["$defs"].items()
        }
    if "items" in normalized and isinstance(normalized["items"], dict):
        normalized["items"] = _strict_schema(normalized["items"])
    for key in ("anyOf", "oneOf", "allOf"):
        if key in normalized:
            normalized[key] = [
                _strict_schema(value) if isinstance(value, dict) else value
                for value in normalized[key]
            ]
    return normalized


class OpenAIClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.model = model or OPENAI_MODEL
        self._client = None

        if self.api_key and "your_openai_api_key_here" not in self.api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key, timeout=OPENAI_TIMEOUT)
            except Exception:
                self._client = None

    def generate(
        self,
        prompt: str,
        schema: Optional[Dict[str, Any]] = None,
        schema_name: str = "ecomarket_response",
    ) -> Dict[str, Any]:
        if not self.api_key or self._client is None:
            return {
                "fallback": True,
                "message": "No se pudo conectar con OpenAI. Se devolvió una respuesta local para la demostración.",
            }

        try:
            request = {
                "model": self.model,
                "input": prompt,
            }
            if schema:
                request["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": _strict_schema(schema),
                    }
                }
            response = self._client.responses.create(
                **request,
            )
            text = getattr(response, "output_text", "")
            if not text:
                raise ValueError("OpenAI devolvió una respuesta vacía")
            return {"fallback": False, "data": json.loads(text), "raw": text}
        except Exception as exc:  # pragma: no cover - defensive branch
            return {"fallback": True, "error": str(exc), "message": "La respuesta de OpenAI no pudo validarse."}
