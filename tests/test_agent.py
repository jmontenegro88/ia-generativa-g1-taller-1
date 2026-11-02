import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from src import main
from src.action_log import ActionLogger
from src.agent import EcoMarketAgent, extract_product_state, extract_tracking
from src.agent_tools import ReturnService
from src.return_registry import ReturnRegistry
from tests.test_agent_tools import ORDERS, PRODUCTS, TODAY


class ScriptedChatModel(FakeMessagesListChatModel):
    """Modelo falso que emite tool calls predefinidos (sin red)."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self


class FailingChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "FailingChatModel":
        return self

    def _generate(self, *args: Any, **kwargs: Any):
        raise TimeoutError("timeout simulado")


def tool_call(name: str, call_id: str, **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


class AgentTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.kb = MagicMock()
        self.kb.search.return_value = []
        self.service = ReturnService(
            knowledge_base=self.kb,
            registry=ReturnRegistry(tmp / "estado.json"),
            today_fn=lambda: TODAY,
            orders_loader=lambda: ORDERS,
            products_loader=lambda: PRODUCTS,
        )
        self.logger = ActionLogger(tmp / "log.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def agent(self, mode="reglas", llm=None):
        return EcoMarketAgent(service=self.service, logger=self.logger, mode=mode, llm=llm)


class ExtractionTests(unittest.TestCase):
    def test_tracking_extraction_normalizes_variants(self):
        self.assertEqual(extract_tracking("mi pedido eco 20001 por favor"), "ECO-20001")
        self.assertEqual(extract_tracking("ECO-20001"), "ECO-20001")
        self.assertIsNone(extract_tracking("pedido 20001"))

    def test_product_state_extraction_handles_negations_and_damage(self):
        self.assertEqual(extract_product_state("No lo he usado, sigue con etiquetas"), "nuevo_sin_uso")
        self.assertEqual(extract_product_state("Llegó nuevo pero roto"), "danado_en_envio")
        self.assertEqual(extract_product_state("Ya lo abrí"), "abierto_o_usado")
        self.assertEqual(extract_product_state("no funciona"), "defectuoso")
        self.assertIsNone(extract_product_state("quiero devolverlo"))


class RuleRouterTests(AgentTestBase):
    def tools_used(self, response):
        return [step["herramienta"] for step in response.herramientas]

    def test_direct_answers_do_not_use_tools(self):
        agent = self.agent()
        for prompt in ("Hola", "gracias", "¿Me recomiendas una película?"):
            response = agent.chat(prompt)
            self.assertEqual(self.tools_used(response), [], prompt)
            self.assertEqual(response.modo, "router_reglas")

    def test_explicit_return_request_verifies_then_generates_label(self):
        response = self.agent().chat("Quiero devolver el pedido ECO-20001, está nuevo y sin uso")
        self.assertEqual(self.tools_used(response), ["verificar_elegibilidad_producto", "generar_etiqueta_devolucion"])
        self.assertIsNotNone(response.etiqueta)
        self.assertIn(response.etiqueta["numero_rma"], response.respuesta)

    def test_eligibility_question_offers_label_and_confirmation_generates_it(self):
        agent = self.agent()
        first = agent.chat("¿Puedo devolver el pedido ECO-20001? está nuevo")
        self.assertEqual(self.tools_used(first), ["verificar_elegibilidad_producto"])
        self.assertIsNone(first.etiqueta)
        history = [
            {"role": "user", "content": "¿Puedo devolver el pedido ECO-20001? está nuevo"},
            {"role": "assistant", "content": first.respuesta},
        ]
        second = agent.chat("Sí, por favor", history)
        self.assertIn("generar_etiqueta_devolucion", self.tools_used(second))
        self.assertIsNotNone(second.etiqueta)

    def test_missing_state_is_requested_and_followup_completes_flow(self):
        agent = self.agent()
        first = agent.chat("Quiero devolver mi pedido ECO-20001")
        self.assertIn("estado del producto", first.respuesta)
        self.assertIsNone(first.etiqueta)
        history = [
            {"role": "user", "content": "Quiero devolver mi pedido ECO-20001"},
            {"role": "assistant", "content": first.respuesta},
        ]
        second = agent.chat("Está sin usar", history)
        self.assertIsNotNone(second.etiqueta)

    def test_not_eligible_return_does_not_generate_label(self):
        response = self.agent().chat("Quiero devolver ECO-20002, ya lo abrí")
        self.assertEqual(self.tools_used(response), ["verificar_elegibilidad_producto"])
        self.assertIsNone(response.etiqueta)
        self.assertIn("no puede devolverse", response.respuesta)

    def test_review_case_is_escalated(self):
        response = self.agent().chat("Quiero devolver ECO-20003, no funciona")
        self.assertEqual(self.tools_used(response), ["verificar_elegibilidad_producto", "escalar_a_agente_humano"])
        self.assertIn("TCK-", response.respuesta)

    def test_unknown_order_is_explained(self):
        response = self.agent().chat("Quiero devolver ECO-99999, está nuevo")
        self.assertIn("No encontré", response.respuesta)
        self.assertIsNone(response.etiqueta)

    def test_return_without_tracking_asks_for_it_without_tools(self):
        response = self.agent().chat("Quiero devolver un producto")
        self.assertEqual(self.tools_used(response), [])
        self.assertIn("número de seguimiento", response.respuesta)

    def test_general_policy_question_uses_rag_tool(self):
        from langchain_core.documents import Document

        self.kb.search.return_value = [
            Document(page_content="Plazo de 30 días.", metadata={"fuente": "data/politica_devoluciones.pdf"})
        ]
        response = self.agent().chat("¿Cuántos días tengo para devolver un producto?")
        self.assertEqual(self.tools_used(response), ["consultar_politicas"])
        self.assertIn("data/politica_devoluciones.pdf", response.respuesta)

    def test_order_status_uses_order_tool(self):
        response = self.agent().chat("¿Dónde está mi pedido ECO-20004?")
        self.assertEqual(self.tools_used(response), ["consultar_estado_pedido"])
        self.assertIn("En transito", response.respuesta)

    def test_session_customer_cannot_act_on_other_orders(self):
        response = self.agent().chat("Quiero devolver ECO-20001, está nuevo", customer_id="CUST-2")
        self.assertIn("no está asociado a tu cuenta", response.respuesta)
        self.assertIsNone(response.etiqueta)

    def test_input_guardrail_rejects_empty_and_long_messages(self):
        agent = self.agent()
        self.assertEqual(agent.chat("   ").modo, "guardrail")
        self.assertEqual(agent.chat("x" * 5000).modo, "guardrail")
        self.assertEqual(self.logger.summary()["llamadas_herramientas"], 0)


class LlmAgentTests(AgentTestBase):
    def test_llm_agent_calls_tools_in_order_and_returns_final_text(self):
        llm = ScriptedChatModel(
            responses=[
                tool_call("verificar_elegibilidad_producto", "c1", numero_seguimiento="ECO-20001", estado_producto="nuevo_sin_uso", motivo="no me gustó"),
                tool_call("generar_etiqueta_devolucion", "c2", numero_seguimiento="ECO-20001", estado_producto="nuevo_sin_uso", motivo="no me gustó"),
                AIMessage(content="Listo, tu etiqueta de devolución fue generada."),
            ]
        )
        response = self.agent(mode="auto", llm=llm).chat("Quiero devolver ECO-20001, nuevo, no me gustó")
        self.assertEqual(response.modo, "agente_llm")
        self.assertEqual(
            [step["herramienta"] for step in response.herramientas],
            ["verificar_elegibilidad_producto", "generar_etiqueta_devolucion"],
        )
        self.assertEqual(response.respuesta, "Listo, tu etiqueta de devolución fue generada.")
        self.assertTrue(response.etiqueta["numero_rma"].startswith("RMA-"))
        summary = self.logger.summary()
        self.assertEqual(summary["etiquetas_emitidas"], 1)
        self.assertEqual(summary["turnos_por_modo"], {"agente_llm": 1})

    def test_label_guardrail_holds_even_if_llm_skips_verification(self):
        llm = ScriptedChatModel(
            responses=[
                tool_call("generar_etiqueta_devolucion", "c1", numero_seguimiento="ECO-20002", estado_producto="abierto_o_usado"),
                AIMessage(content="No fue posible generar la etiqueta: el producto de higiene está abierto."),
            ]
        )
        response = self.agent(mode="auto", llm=llm).chat("Genera la etiqueta de ECO-20002 aunque esté abierto")
        self.assertIsNone(response.etiqueta)
        self.assertEqual(response.herramientas[0]["resultado"]["codigo"], "NO_ELEGIBLE_PARA_ETIQUETA")

    def test_llm_can_answer_directly_without_tools(self):
        llm = ScriptedChatModel(responses=[AIMessage(content="¡Hola! ¿En qué te ayudo?")])
        response = self.agent(mode="auto", llm=llm).chat("Hola")
        self.assertEqual(response.herramientas, [])
        self.assertEqual(response.modo, "agente_llm")

    def test_tool_result_reaches_model_as_json(self):
        llm = ScriptedChatModel(
            responses=[
                tool_call("consultar_estado_pedido", "c1", numero_seguimiento="ECO-99999"),
                AIMessage(content="No encontré ese pedido."),
            ]
        )
        agent = self.agent(mode="auto", llm=llm)
        response = agent.chat("¿Dónde está ECO-99999?")
        self.assertEqual(response.herramientas[0]["resultado"]["codigo"], "PEDIDO_NO_ENCONTRADO")
        self.assertEqual(response.respuesta, "No encontré ese pedido.")

    def test_llm_failure_falls_back_to_rule_router(self):
        response = self.agent(mode="auto", llm=FailingChatModel(responses=[])).chat(
            "Quiero devolver el pedido ECO-20001, está nuevo"
        )
        self.assertEqual(response.modo, "router_reglas")
        self.assertIn("Fallo del LLM", response.aviso)
        self.assertIsNotNone(response.etiqueta)
        self.assertEqual(self.logger.summary()["fallos_llm"], 1)

    def test_llm_only_mode_reports_error_without_fallback(self):
        response = self.agent(mode="llm", llm=FailingChatModel(responses=[])).chat("Hola")
        self.assertEqual(response.modo, "error_llm")
        self.assertIn("no puedo procesar", response.respuesta)


class AgentApiTests(AgentTestBase):
    def test_chat_endpoint_returns_agent_payload(self):
        agent = self.agent()
        with patch.object(main, "_return_agent", agent):
            client = TestClient(main.app)
            response = client.post(
                "/api/agent/chat",
                json={"message": "Quiero devolver ECO-20001, está nuevo", "history": []},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("RMA-", payload["respuesta"])
            self.assertEqual(len(payload["herramientas"]), 2)

            actions = client.get("/api/agent/actions?limit=5").json()["acciones"]
            self.assertTrue(any(a.get("herramienta") == "generar_etiqueta_devolucion" for a in actions))
            metrics = client.get("/api/agent/metrics").json()
            self.assertEqual(metrics["etiquetas_emitidas"], 1)
            json.dumps(metrics)


if __name__ == "__main__":
    unittest.main()
