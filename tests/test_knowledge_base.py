from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import RAG_CHUNK_OVERLAP, RAG_CHUNK_SIZE
from src.knowledge_base import (
    KnowledgeBase,
    format_knowledge_context,
    knowledge_sources,
    load_knowledge_documents,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DeterministicEmbeddings:
    def embed_documents(self, texts):
        return [[float(len(text)), 1.0, 0.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0, 0.0]


class KnowledgeDocumentTests(unittest.TestCase):
    def test_search_passes_original_query_and_requested_candidate_count(self):
        bottle = Document(
            page_content="Botella reutilizable",
            metadata={"sku": "SKU-001"},
        )
        vector_store = Mock()
        vector_store.similarity_search.return_value = [bottle]
        knowledge_base = KnowledgeBase(embedding_model="test-embeddings")

        with patch.object(knowledge_base, "_ensure_index", return_value=vector_store):
            results = knowledge_base.search(
                "¿Tienen un recipiente para tomar?",
                document_type="producto",
                k=5,
            )

        self.assertEqual(results, [bottle])
        vector_store.similarity_search.assert_called_once_with(
            "¿Tienen un recipiente para tomar?",
            k=5,
            filter={"tipo": {"$eq": "producto"}},
        )

    def test_loads_policy_and_individual_products_without_orders(self):
        documents = load_knowledge_documents(PROJECT_ROOT / "data")

        policies = [document for document in documents if document.metadata["tipo"] == "politica"]
        products = [document for document in documents if document.metadata["tipo"] == "producto"]
        self.assertEqual(len(policies), 3)
        self.assertEqual(
            {document.metadata["categoria"] for document in policies},
            {"devoluciones", "envios", "garantias"},
        )
        self.assertEqual(len(products), 68)
        self.assertTrue(all(document.metadata["tipo"] == "producto" for document in products))
        self.assertEqual(
            {document.metadata["sku"] for document in products},
            {f"SKU-{number:03d}" for number in range(1, 69)},
        )
        product_names = {document.metadata["nombre"] for document in products}
        self.assertIn("Jabón artesanal de avena", product_names)
        self.assertIn("Pantalón cargo de algodón", product_names)
        self.assertIn("Recipiente hermético de vidrio de 1 litro", product_names)
        bottle = next(document for document in products if document.metadata["sku"] == "SKU-001")
        self.assertIn("beber agua", bottle.page_content)
        self.assertTrue(all("customer_id" not in document.page_content for document in documents))

    def test_policy_documents_have_clean_categories_and_sources(self):
        documents = load_knowledge_documents(PROJECT_ROOT / "data")
        policies = [document for document in documents if document.metadata["tipo"] == "politica"]
        shipping_policy = next(
            document for document in policies if document.metadata["categoria"] == "envios"
        )
        warranty_policy = next(
            document for document in policies if document.metadata["categoria"] == "garantias"
        )

        self.assertEqual(
            knowledge_sources([shipping_policy, warranty_policy]),
            ["data/politica_envios.docx", "data/politica_garantias.json"],
        )
        return_policy = next(
            document for document in policies
            if document.metadata["categoria"] == "devoluciones"
        )
        self.assertEqual(
            knowledge_sources([return_policy]),
            ["data/politica_devoluciones.pdf"],
        )
        self.assertIn("3 y 5 días hábiles", shipping_policy.page_content)
        self.assertIn("90 días calendario", warranty_policy.page_content)
        self.assertIn("30 días posteriores a la entrega", return_policy.page_content)
        self.assertNotIn("ficticio", format_knowledge_context([shipping_policy]).lower())

    def test_markdown_policy_is_supported_when_no_converted_copy_exists(self):
        with TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            (data_dir / "productos.json").write_text("[]", encoding="utf-8")
            (data_dir / "politica_devoluciones.md").write_text(
                "# Devoluciones\n\n- Plazo de 30 días.",
                encoding="utf-8",
            )

            documents = load_knowledge_documents(data_dir)

        policy = next(document for document in documents if document.metadata["tipo"] == "politica")
        self.assertEqual(policy.metadata["fuente"], "data/politica_devoluciones.md")
        self.assertIn("Plazo de 30 días", policy.page_content)

    def test_policy_split_keeps_source_metadata_and_bounded_chunks(self):
        documents = load_knowledge_documents(PROJECT_ROOT / "data")
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=RAG_CHUNK_SIZE,
            chunk_overlap=RAG_CHUNK_OVERLAP,
        )

        chunks = splitter.split_documents(documents)

        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk.page_content) <= RAG_CHUNK_SIZE for chunk in chunks))
        self.assertTrue(all(chunk.metadata.get("fuente") for chunk in chunks))

    def test_context_and_source_helpers_keep_auditable_paths(self):
        documents = load_knowledge_documents(PROJECT_ROOT / "data")

        return_policy = next(
            document
            for document in documents
            if document.metadata.get("categoria") == "devoluciones"
        )
        first_product = next(
            document for document in documents if document.metadata.get("sku") == "SKU-001"
        )
        context = format_knowledge_context([return_policy])
        sources = knowledge_sources([return_policy, first_product])

        self.assertIn("[Fuente: data/politica_devoluciones.pdf]", context)
        self.assertIn("30 días", context)
        self.assertEqual(
            sources,
            ["data/politica_devoluciones.pdf", "data/productos.json (SKU SKU-001)"],
        )

    def test_chroma_index_returns_filtered_policy_and_persists_manifest(self):
        with TemporaryDirectory() as temporary_directory:
            persist_directory = Path(temporary_directory) / "chroma"
            with patch(
                "langchain_huggingface.HuggingFaceEmbeddings",
                return_value=DeterministicEmbeddings(),
            ):
                knowledge_base = KnowledgeBase(
                    data_dir=PROJECT_ROOT / "data",
                    persist_directory=persist_directory,
                    embedding_model="test-embeddings",
                )
                results = knowledge_base.search(
                    "¿Cuál es el plazo de devolución?",
                    document_type="politica",
                    category="devoluciones",
                )

            self.assertTrue(results)
            self.assertTrue(
                all(
                    document.metadata["tipo"] == "politica"
                    and document.metadata["categoria"] == "devoluciones"
                    for document in results
                )
            )
            self.assertTrue(
                (persist_directory / "index_manifest.json").is_file()
            )

    def test_chroma_index_filters_shipping_policy_separately(self):
        with TemporaryDirectory() as temporary_directory:
            persist_directory = Path(temporary_directory) / "chroma"
            with patch(
                "langchain_huggingface.HuggingFaceEmbeddings",
                return_value=DeterministicEmbeddings(),
            ):
                knowledge_base = KnowledgeBase(
                    data_dir=PROJECT_ROOT / "data",
                    persist_directory=persist_directory,
                    embedding_model="test-embeddings",
                )
                results = knowledge_base.search(
                    "¿Cuánto tarda un envío?",
                    document_type="politica",
                    category="envios",
                )

            self.assertTrue(results)
            self.assertTrue(
                all(document.metadata["categoria"] == "envios" for document in results)
            )

    def test_chroma_index_loads_json_warranty_policy_and_keeps_its_source(self):
        with TemporaryDirectory() as temporary_directory:
            persist_directory = Path(temporary_directory) / "chroma"
            with patch(
                "langchain_huggingface.HuggingFaceEmbeddings",
                return_value=DeterministicEmbeddings(),
            ):
                knowledge_base = KnowledgeBase(
                    data_dir=PROJECT_ROOT / "data",
                    persist_directory=persist_directory,
                    embedding_model="test-embeddings",
                )
                results = knowledge_base.search(
                    "¿Cuánto dura la garantía?",
                    document_type="politica",
                    category="garantias",
                )

        self.assertTrue(results)
        self.assertTrue(all(document.metadata["categoria"] == "garantias" for document in results))
        self.assertEqual(
            knowledge_sources(results),
            ["data/politica_garantias.json"],
        )
        self.assertIn("90 días calendario", format_knowledge_context(results))


if __name__ == "__main__":
    unittest.main()
