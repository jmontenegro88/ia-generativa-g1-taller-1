import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from src import main


class RagRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.policy_document = Document(
            page_content="- Los productos nuevos y sin uso pueden devolverse dentro de los 30 días.",
            metadata={
                "tipo": "politica",
                "fuente": "data/politica_devoluciones.pdf",
            },
        )

    def test_policy_answer_uses_retrieved_context_and_backend_sources(self):
        generated = {
            "respuesta": "Se aplica el plazo de 30 días.",
            "regla_aplicada": "plazo_devolucion",
            "fuentes": ["fuente inventada por el modelo"],
            "requiere_agente": False,
        }
        with (
            patch.object(main.knowledge_base, "search", return_value=[self.policy_document]) as retriever,
            patch.object(main.openai_client, "generate", return_value={"fallback": False, "data": generated}) as llm,
        ):
            response = self.client.post(
                "/api/policies/answer",
                json={
                    "question": "¿Cuál es el plazo de devolución?",
                    "category": "devoluciones",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("30 días", llm.call_args.args[0])
        retriever.assert_called_once_with(
            "¿Cuál es el plazo de devolución?",
            document_type="politica",
            category="devoluciones",
        )
        self.assertEqual(
            response.json()["response"]["fuentes"],
            ["data/politica_devoluciones.pdf"],
        )

    def test_policy_answer_returns_shipping_policy_source(self):
        shipping_document = Document(
            page_content="El transporte estándar tarda entre 3 y 5 días hábiles.",
            metadata={
                "tipo": "politica",
                "categoria": "envios",
                "fuente": "data/politica_envios.docx",
            },
        )
        generated = {
            "respuesta": "El transporte estándar tarda entre 3 y 5 días hábiles.",
            "regla_aplicada": None,
            "fuentes": [],
            "requiere_agente": True,
        }
        with (
            patch.object(main.knowledge_base, "search", return_value=[shipping_document]) as retriever,
            patch.object(main.openai_client, "generate", return_value={"fallback": False, "data": generated}),
        ):
            response = self.client.post(
                "/api/policies/answer",
                json={
                    "question": "¿Cuánto tarda el transporte?",
                    "category": "envios",
                },
            )

        self.assertEqual(response.status_code, 200)
        retriever.assert_called_once_with(
            "¿Cuánto tarda el transporte?",
            document_type="politica",
            category="envios",
        )
        self.assertEqual(
            response.json()["response"]["fuentes"],
            [
                "data/politica_envios.docx"
            ],
        )

    def test_return_without_retrieved_policy_escalates_without_calling_llm(self):
        with (
            patch.object(main.knowledge_base, "search", return_value=[]),
            patch.object(main.openai_client, "generate") as llm,
        ):
            response = self.client.post(
                "/api/returns/evaluate",
                json={
                    "product_name": "Jabones artesanales",
                    "category": "higiene",
                    "condition": "nuevo",
                    "received_days_ago": 12,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["response"]
        self.assertTrue(payload["requiere_agente"])
        self.assertFalse(payload["es_elegible"])
        self.assertIn("No se recuperó la política", payload["motivo"])
        llm.assert_not_called()

    def test_return_prompt_uses_policy_retrieval(self):
        generated = {
            "es_elegible": True,
            "motivo": "La solicitud se encuentra dentro del plazo indicado.",
            "pasos_siguientes": [],
            "informacion_faltante": [],
            "requiere_agente": False,
            "respuesta_cliente": "La solicitud está dentro del plazo indicado.",
            "fuentes": ["fuente inventada por el modelo"],
        }
        with (
            patch.object(main.knowledge_base, "search", return_value=[self.policy_document]),
            patch.object(main.openai_client, "generate", return_value={"fallback": False, "data": generated}) as llm,
        ):
            response = self.client.post(
                "/api/returns/evaluate",
                json={
                    "product_name": "Botella reutilizable",
                    "category": "accesorios",
                    "condition": "nuevo",
                    "received_days_ago": 12,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("30 días", llm.call_args.args[0])
        self.assertEqual(
            response.json()["response"]["fuentes"],
            ["data/politica_devoluciones.pdf", "data/productos.json"],
        )

    def test_product_prompt_uses_retrieved_catalog_context(self):
        product_document = Document(
            page_content='{"name": "Botella reutilizable", "price": 18.5}',
            metadata={
                "tipo": "producto",
                "fuente": "data/productos.json",
                "sku": "SKU-001",
                "nombre": "Botella reutilizable",
            },
        )
        generated = {
            "encontrado": True,
            "nombre": "Botella reutilizable",
            "categoria": "accesorios",
            "precio": 18.5,
            "condicion": "nuevo",
            "personalizable": False,
            "mensaje_cliente": "Precio registrado: 18.5.",
            "requiere_agente": False,
            "fuentes": [],
        }
        with (
            patch.object(main.knowledge_base, "search", return_value=[product_document]),
            patch.object(main.openai_client, "generate", return_value={"fallback": False, "data": generated}) as llm,
        ):
            response = self.client.post(
                "/api/products/search",
                json={"product_name": "Botella reutilizable"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("18.5", llm.call_args.args[0])
        self.assertEqual(
            response.json()["response"]["fuentes"],
            ["data/productos.json (SKU SKU-001)"],
        )
        self.assertEqual(response.json()["product"]["sku"], "SKU-001")

    def test_product_search_returns_not_found_for_weak_semantic_matches(self):
        with (
            patch.object(main.knowledge_base, "search", return_value=[]) as retriever,
            patch.object(main.openai_client, "generate") as llm,
        ):
            response = self.client.post(
                "/api/products/search",
                json={"query": "¿Tienen una licuadora industrial?"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn(
            "No fue posible identificar un producto relacionado",
            response.json()["detail"]["mensaje_cliente"],
        )
        retriever.assert_called_once_with(
            "¿Tienen una licuadora industrial?",
            document_type="producto",
            k=68,
        )
        llm.assert_not_called()

    def test_semantic_product_match_compares_candidate_catalog_and_limits_sources(self):
        bottle_document = Document(
            page_content='{"name": "Botella reutilizable", "price": 18.5}',
            metadata={
                "tipo": "producto",
                "fuente": "data/productos.json",
                "sku": "SKU-001",
                "nombre": "Botella reutilizable",
            },
        )
        unrelated_document = Document(
            page_content='{"name": "Jabones artesanales", "price": 14.0}',
            metadata={
                "tipo": "producto",
                "fuente": "data/productos.json",
                "sku": "SKU-002",
                "nombre": "Jabones artesanales",
            },
        )
        generated = {
            "encontrado": True,
            "nombre": "Botella reutilizable",
            "categoria": "accesorios",
            "precio": 18.5,
            "condicion": "nuevo",
            "personalizable": False,
            "mensaje_cliente": (
                "Encontré una botella reutilizable en el catálogo. La ficha no "
                "especifica si es apta para bebidas; puedo solicitar confirmación."
            ),
            "requiere_agente": True,
            "fuentes": [],
        }
        with (
            patch.object(
                main.knowledge_base,
                "search",
                return_value=[unrelated_document, bottle_document],
            ),
            patch.object(
                main.openai_client,
                "generate",
                return_value={"fallback": False, "data": generated},
            ) as llm,
        ):
            response = self.client.post(
                "/api/products/search",
                json={"query": "¿Tienen un recipiente para tomar?"},
            )

        self.assertEqual(response.status_code, 200)
        prompt = llm.call_args.args[0]
        self.assertIn('"name": "Botella reutilizable"', prompt)
        self.assertIn("Jabones artesanales", prompt)
        self.assertIn("expresión del cliente puede ser una paráfrasis", prompt)
        self.assertIn("No uses la cercanía de un resultado vectorial", prompt)
        payload = response.json()["response"]
        self.assertTrue(payload["encontrado"])
        self.assertTrue(payload["requiere_agente"])
        self.assertEqual(payload["nombre"], "Botella reutilizable")
        self.assertEqual(payload["precio"], 18.5)
        self.assertEqual(
            payload["fuentes"],
            ["data/productos.json (SKU SKU-001)"],
        )
        self.assertEqual(response.json()["product"]["sku"], "SKU-001")

    def test_semantic_product_search_returns_not_found_when_llm_rejects_candidates(self):
        candidate_documents = [
            Document(
                page_content=f'{{"name": "{name}"}}',
                metadata={
                    "tipo": "producto",
                    "fuente": "data/productos.json",
                    "sku": sku,
                    "nombre": name,
                },
            )
            for sku, name in (
                ("SKU-001", "Botella reutilizable"),
                ("SKU-002", "Jabones artesanales"),
                ("SKU-003", "Camiseta de algodón orgánico"),
                ("SKU-004", "Compostera doméstica"),
                ("SKU-005", "Lámpara solar"),
            )
        ]
        generated = {
            "encontrado": False,
            "nombre": "¿Tienen una licuadora industrial?",
            "mensaje_cliente": "No encontré un producto que corresponda en el catálogo.",
            "requiere_agente": False,
        }
        with (
            patch.object(main.knowledge_base, "search", return_value=candidate_documents) as retriever,
            patch.object(
                main.openai_client,
                "generate",
                return_value={"fallback": False, "data": generated},
            ) as llm,
        ):
            response = self.client.post(
                "/api/products/search",
                json={"query": "¿Tienen una licuadora industrial?"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn("no encontré", response.json()["detail"]["mensaje_cliente"].lower())
        self.assertEqual(
            response.json()["detail"]["nombre"],
            "¿Tienen una licuadora industrial?",
        )
        retriever.assert_called_once_with(
            "¿Tienen una licuadora industrial?",
            document_type="producto",
            k=68,
        )
        self.assertIn("Botella reutilizable", llm.call_args.args[0])
        self.assertIn("Jabones artesanales", llm.call_args.args[0])
        self.assertNotIn("sources", response.json()["detail"])

    def test_semantic_product_candidate_is_not_confirmed_without_llm(self):
        product_document = Document(
            page_content='{"name": "Botella reutilizable", "price": 18.5}',
            metadata={
                "tipo": "producto",
                "fuente": "data/productos.json",
                "sku": "SKU-001",
                "nombre": "Botella reutilizable",
            },
        )
        with (
            patch.object(main.knowledge_base, "search", return_value=[product_document]) as retriever,
            patch.object(main.openai_client, "generate", return_value={"fallback": True}),
        ):
            response = self.client.post(
                "/api/products/search",
                json={"query": "¿Cuánto cuesta una botella para tomar agua?"},
            )

        self.assertEqual(response.status_code, 503)
        retriever.assert_called_once_with(
            "¿Cuánto cuesta una botella para tomar agua?",
            document_type="producto",
            k=68,
        )
        self.assertIn("No se pudo seleccionar un producto", response.json()["detail"]["mensaje_cliente"])

    def test_order_lookup_does_not_use_semantic_retrieval(self):
        with (
            patch.object(main.knowledge_base, "search") as retriever,
            patch.object(main.openai_client, "generate", return_value={"fallback": True}),
        ):
            response = self.client.post(
                "/api/orders/status",
                json={"tracking_number": "ECO-10001"},
            )

        self.assertEqual(response.status_code, 200)
        retriever.assert_not_called()

    def test_new_order_records_are_lookupable_by_exact_tracking_number(self):
        orders = main.load_orders()
        tracking_numbers = [order["tracking_number"] for order in orders]
        product_names = {product["name"] for product in main.load_products()}
        self.assertEqual(len(orders), 30)
        self.assertEqual(len(tracking_numbers), len(set(tracking_numbers)))
        self.assertTrue(all(order["product_name"] in product_names for order in orders[10:]))

        with (
            patch.object(main.knowledge_base, "search") as retriever,
            patch.object(main.openai_client, "generate", return_value={"fallback": True}),
        ):
            response = self.client.post(
                "/api/orders/status",
                json={"tracking_number": "ECO-10030"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["order"]["product_name"], "Botella reutilizable con filtro")
        self.assertEqual(response.json()["order"]["source"], "sistema_pedidos_demo")
        retriever.assert_not_called()


if __name__ == "__main__":
    unittest.main()
