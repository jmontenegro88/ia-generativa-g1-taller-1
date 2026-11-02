import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from langchain_core.documents import Document

from src.action_log import ActionLogger
from src.agent_tools import AgentToolbox, ReturnService
from src.return_registry import ReturnRegistry

TODAY = date(2026, 10, 27)

ORDERS = [
    {"tracking_number": "ECO-20001", "order_id": "ORD-1", "status": "Entregado", "estimated_delivery": "2026-10-17",
     "customer_id": "CUST-1", "product_name": "Botella reutilizable"},
    {"tracking_number": "ECO-20002", "order_id": "ORD-2", "status": "Entregado", "estimated_delivery": "2026-10-17",
     "customer_id": "CUST-2", "product_name": "Jabones artesanales"},
    {"tracking_number": "ECO-20003", "order_id": "ORD-3", "status": "Entregado", "estimated_delivery": "2026-09-07",
     "customer_id": "CUST-3", "product_name": "Botella reutilizable"},
    {"tracking_number": "ECO-20004", "order_id": "ORD-4", "status": "En transito", "estimated_delivery": "2026-10-30",
     "customer_id": "CUST-4", "product_name": "Botella reutilizable"},
    {"tracking_number": "ECO-20005", "order_id": "ORD-5", "status": "Devuelto", "estimated_delivery": "2026-10-10",
     "customer_id": "CUST-5", "product_name": "Botella reutilizable"},
    {"tracking_number": "ECO-20006", "order_id": "ORD-6", "status": "Entregado", "estimated_delivery": "2026-10-20",
     "customer_id": "CUST-6", "product_name": "Taza grabada"},
    {"tracking_number": "ECO-20007", "order_id": "ORD-7", "status": "Entregado", "estimated_delivery": "2026-06-01",
     "customer_id": "CUST-7", "product_name": "Botella reutilizable"},
]
PRODUCTS = [
    {"sku": "SKU-001", "name": "Botella reutilizable", "category": "accesorios", "custom": False},
    {"sku": "SKU-002", "name": "Jabones artesanales", "category": "higiene", "custom": False},
    {"sku": "SKU-099", "name": "Taza grabada", "category": "accesorios", "custom": True},
]


class ReturnServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = ReturnRegistry(Path(self.tmp.name) / "estado.json")
        self.kb = MagicMock()
        self.service = ReturnService(
            knowledge_base=self.kb,
            registry=self.registry,
            today_fn=lambda: TODAY,
            orders_loader=lambda: ORDERS,
            products_loader=lambda: PRODUCTS,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, tracking, state="nuevo_sin_uso", motivo="", customer=None):
        return self.service.verificar_elegibilidad(tracking, state, motivo, customer)

    def test_new_unused_product_within_window_is_eligible(self):
        result = self.check("ECO-20001")
        self.assertTrue(result["ok"])
        self.assertEqual(result["decision"], "elegible")
        self.assertEqual(result["dias_desde_entrega"], 10)
        self.assertIn("data/politica_devoluciones.pdf", result["fuentes"])

    def test_opened_hygiene_product_is_not_eligible(self):
        result = self.check("ECO-20002", "abierto_o_usado")
        self.assertEqual(result["decision"], "no_elegible")
        self.assertIn("higiene", result["mensaje"])

    def test_defective_hygiene_product_is_eligible_with_evidence(self):
        result = self.check("ECO-20002", "defectuoso")
        self.assertEqual(result["decision"], "elegible")
        self.assertTrue(result["requiere_evidencia"])

    def test_used_regular_product_is_not_eligible(self):
        self.assertEqual(self.check("ECO-20001", "abierto_o_usado")["decision"], "no_elegible")

    def test_unknown_state_requests_missing_information(self):
        result = self.check("ECO-20001", "desconocido")
        self.assertEqual(result["decision"], "informacion_faltante")
        self.assertEqual(result["informacion_faltante"], ["estado_producto"])

    def test_outside_window_but_defective_within_warranty_requires_review(self):
        result = self.check("ECO-20003", "defectuoso")
        self.assertEqual(result["decision"], "requiere_revision")
        self.assertTrue(result["requiere_agente"])
        self.assertIn("data/politica_garantias.json", result["fuentes"])

    def test_outside_window_and_unused_is_not_eligible(self):
        self.assertEqual(self.check("ECO-20003")["decision"], "no_elegible")

    def test_outside_warranty_is_not_eligible_even_if_defective(self):
        self.assertEqual(self.check("ECO-20007", "defectuoso")["decision"], "no_elegible")

    def test_not_delivered_order_is_not_eligible(self):
        result = self.check("ECO-20004")
        self.assertEqual(result["decision"], "no_elegible")
        self.assertIn("En transito", result["mensaje"])

    def test_already_returned_order_is_not_eligible(self):
        self.assertEqual(self.check("ECO-20005")["decision"], "no_elegible")

    def test_custom_product_is_not_eligible_without_defect(self):
        self.assertEqual(self.check("ECO-20006")["decision"], "no_elegible")
        self.assertEqual(self.check("ECO-20006", "defectuoso")["decision"], "requiere_revision")

    def test_sensitive_reason_is_escalated(self):
        result = self.check("ECO-20001", motivo="Me causó una lesión y quiero una indemnización")
        self.assertEqual(result["decision"], "requiere_revision")
        self.assertTrue(result["requiere_agente"])

    def test_invalid_format_and_missing_order_are_reported_as_errors(self):
        self.assertEqual(self.check("12345")["codigo"], "FORMATO_INVALIDO")
        self.assertEqual(self.check("ECO-99999")["codigo"], "PEDIDO_NO_ENCONTRADO")
        self.assertFalse(self.check("ECO-99999")["ok"])

    def test_other_customer_cannot_access_order(self):
        result = self.check("ECO-20001", customer="CUST-2")
        self.assertEqual(result["codigo"], "NO_AUTORIZADO")
        self.assertNotIn("pedido", result)
        self.assertEqual(self.check("eco-20001", customer="cust-1")["decision"], "elegible")

    def test_label_is_generated_once_and_reused(self):
        first = self.service.generar_etiqueta("ECO-20001", "nuevo_sin_uso", "No me gustó")
        self.assertTrue(first["ok"])
        self.assertEqual(first["codigo"], "ETIQUETA_GENERADA")
        label = first["etiqueta"]
        self.assertTrue(label["numero_rma"].startswith("RMA-"))
        self.assertEqual(label["valida_hasta"], "2026-11-10")
        self.assertIn(label["numero_rma"], label["contenido_texto"])

        second = self.service.generar_etiqueta("ECO-20001", "nuevo_sin_uso", "")
        self.assertEqual(second["codigo"], "ETIQUETA_EXISTENTE")
        self.assertEqual(second["etiqueta"]["numero_rma"], label["numero_rma"])

    def test_label_tool_rechecks_eligibility(self):
        result = self.service.generar_etiqueta("ECO-20002", "abierto_o_usado")
        self.assertFalse(result["ok"])
        self.assertEqual(result["codigo"], "NO_ELEGIBLE_PARA_ETIQUETA")
        self.assertIsNone(self.registry.get_label("ECO-20002"))

    def test_policy_tool_wraps_rag_results_and_failures(self):
        self.kb.search.return_value = [
            Document(page_content="Plazo de 30 días.", metadata={"fuente": "data/politica_devoluciones.pdf", "categoria": "devoluciones"})
        ]
        result = self.service.consultar_politicas("¿plazo?", "devoluciones")
        self.assertEqual(result["codigo"], "FRAGMENTOS_RECUPERADOS")
        self.assertEqual(result["fuentes"], ["data/politica_devoluciones.pdf"])
        self.kb.search.assert_called_once_with("¿plazo?", document_type="politica", category="devoluciones")

        self.kb.search.side_effect = RuntimeError("chroma caído")
        failure = self.service.consultar_politicas("¿plazo?")
        self.assertFalse(failure["ok"])
        self.assertEqual(failure["codigo"], "ERROR_BASE_CONOCIMIENTO")

    def test_escalation_ticket_is_deduplicated_and_prioritized(self):
        first = self.service.escalar("Me causó una alergia", "ECO-20001")
        second = self.service.escalar("Me causó una alergia", "ECO-20001")
        self.assertEqual(first["prioridad"], "alta")
        self.assertEqual(first["numero_ticket"], second["numero_ticket"])
        self.assertTrue(second["ya_existia"])
        self.assertFalse(self.service.escalar("   ")["ok"])

    def test_toolbox_logs_calls_and_binds_session_customer(self):
        logger = ActionLogger(Path(self.tmp.name) / "log.jsonl")
        toolbox = AgentToolbox(self.service, logger, customer_id="CUST-2", session_id="s1")
        result = toolbox.verificar_elegibilidad_producto("ECO-20001", "nuevo_sin_uso")
        self.assertEqual(result["codigo"], "NO_AUTORIZADO")
        records = logger.read_recent()
        self.assertEqual(records[-1]["herramienta"], "verificar_elegibilidad_producto")
        self.assertEqual(records[-1]["cliente"], "CUST-2")
        self.assertFalse(records[-1]["ok"])
        self.assertEqual(logger.summary()["errores_herramientas"], 1)
        names = [tool.name for tool in toolbox.langchain_tools()]
        self.assertIn("verificar_elegibilidad_producto", names)
        self.assertIn("generar_etiqueta_devolucion", names)
        self.assertIn("consultar_politicas", names)


if __name__ == "__main__":
    unittest.main()
