import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scr.knowledge_graph.sqlite_retrieval import (
    index_graph_for_retrieval,
    initialize_retrieval_database,
    search_knowledge_graph,
)


class SQLiteRetrievalTestCase(unittest.TestCase):
    def test_initialize_retrieval_database_creates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "kg.sqlite3"

            initialize_retrieval_database(db_path)

            with sqlite3.connect(db_path) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
            self.assertIn("documents", tables)
            self.assertIn("nodes", tables)
            self.assertIn("edges", tables)
            self.assertIn("chunks", tables)

    def test_index_graph_for_retrieval_upserts_graph_and_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph_path = root / "entity_graph_fused.json"
            markdown_path = root / "document.md"
            db_path = root / "kg.sqlite3"
            graph_path.write_text(json.dumps(_sample_graph(), ensure_ascii=False), encoding="utf-8")
            markdown_path.write_text("Ru/CeO2 catalyst shows ammonia synthesis activity.", encoding="utf-8")

            report = index_graph_for_retrieval(
                graph_path=graph_path,
                db_path=db_path,
                document_markdown_path=markdown_path,
            )

            self.assertEqual(report["status"], "indexed")
            self.assertEqual(report["node_count"], 3)
            self.assertEqual(report["edge_count"], 2)
            self.assertEqual(report["chunk_count"], 1)

            with sqlite3.connect(db_path) as conn:
                node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
                chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            self.assertEqual(node_count, 3)
            self.assertEqual(edge_count, 2)
            self.assertEqual(chunk_count, 1)

    def test_search_knowledge_graph_returns_hits_and_neighbor_subgraph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph_path = root / "entity_graph_fused.json"
            markdown_path = root / "document.md"
            db_path = root / "kg.sqlite3"
            graph_path.write_text(json.dumps(_sample_graph(), ensure_ascii=False), encoding="utf-8")
            markdown_path.write_text("Ru/CeO2 catalyst mentions CeO2 support.", encoding="utf-8")
            index_graph_for_retrieval(
                graph_path=graph_path,
                db_path=db_path,
                document_markdown_path=markdown_path,
            )

            result = search_knowledge_graph("Ru/CeO2", db_path=db_path, limit=5, hops=1)

            self.assertTrue(any(node["display_name"] == "Ru/CeO2" for node in result["nodes"]))
            self.assertTrue(any("Ru/CeO2" in chunk["text"] for chunk in result["chunks"]))
            subgraph_node_ids = {node["node_id"] for node in result["subgraph"]["nodes"]}
            self.assertIn("fused:催化剂:1", subgraph_node_ids)
            self.assertIn("fused:助剂:2", subgraph_node_ids)
            self.assertTrue(any(edge["relation"] == "有助剂" for edge in result["subgraph"]["edges"]))


def _sample_graph() -> dict:
    return {
        "document": {"doc_id": "doc-1", "title": "Example paper", "filename": "document.md"},
        "nodes": [
            {
                "id": "fused:催化剂:1",
                "type": "催化剂",
                "level": "root",
                "properties": {"display_name": "Ru/CeO2", "original_name": "Ru:CeO2"},
            },
            {
                "id": "fused:助剂:2",
                "type": "助剂",
                "level": "child",
                "properties": {"display_name": "CeO2", "original_name": "CeO2"},
            },
            {
                "id": "fused:温度:3",
                "type": "温度",
                "level": "child",
                "properties": {"display_name": "400 °C", "value": "400", "unit": "°C"},
            },
        ],
        "edges": [
            {"source": "fused:催化剂:1", "relation": "有助剂", "target": "fused:助剂:2"},
            {"source": "fused:催化剂:1", "relation": "有温度", "target": "fused:温度:3"},
        ],
    }


if __name__ == "__main__":
    unittest.main()
