import json
import tempfile
import unittest
from pathlib import Path

from scr.knowledge_graph.entity_storage import (
    build_storage_graph,
    clear_entity_graph_database,
    store_entity_graph,
)


class FakeSession:
    def __init__(self) -> None:
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        return None


class FakeDriver:
    def __init__(self) -> None:
        self.session_obj = FakeSession()
        self.closed = False
        self.database = None

    def session(self, database=None):
        self.database = database
        return self.session_obj

    def close(self):
        self.closed = True


class EntityStorageTestCase(unittest.TestCase):
    def test_clear_entity_graph_database_executes_detach_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            env_path = root / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "NEO4J_URI=bolt://localhost:7687",
                        "NEO4J_USERNAME=neo4j",
                        "NEO4J_PASSWORD=test-password",
                        "NEO4J_DATABASE=neo4j",
                    ]
                ),
                encoding="utf-8",
            )

            driver = FakeDriver()
            result = clear_entity_graph_database(
                env_file=env_path,
                verbose=False,
                driver_factory=lambda uri, auth: driver,
            )

            self.assertTrue(driver.closed)
            self.assertEqual(result["status"], "cleared")
            queries = "\n".join(query for query, _ in driver.session_obj.calls)
            self.assertIn("MATCH (n) DETACH DELETE n", queries)

    def test_build_storage_graph_keeps_minimal_properties(self) -> None:
        graph = {
            "document": {"doc_id": "doc-1"},
            "nodes": [
                {
                    "id": "fused:粒径:1",
                    "type": "粒径",
                    "level": "child",
                    "properties": {
                        "value": "9.3",
                        "unit": "nm",
                        "display_name": "9.3 nm",
                        "original_name": "9.3nm",
                        "doc_id": "doc-1",
                        "catalyst_name": "Ru/CeO₂",
                        "aliases": ["9.3 nm", "9.3nm"],
                        "source_node_ids": ["粒径:1"],
                        "fusion_status": "single",
                    },
                }
            ],
            "edges": [],
        }

        projected = build_storage_graph(graph)
        props = projected["nodes"][0]["properties"]

        self.assertEqual(
            props,
            {
                "value": "9.3",
                "unit": "nm",
                "display_name": "9.3 nm",
                "original_name": "9.3nm",
                "doc_id": "doc-1",
            },
        )

    def test_store_entity_graph_writes_report_and_executes_queries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            env_path = root / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "NEO4J_URI=bolt://localhost:7687",
                        "NEO4J_USERNAME=neo4j",
                        "NEO4J_PASSWORD=test-password",
                        "NEO4J_DATABASE=neo4j",
                    ]
                ),
                encoding="utf-8",
            )

            graph_path = root / "entity_graph_fused.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "document": {"doc_id": "doc-1"},
                        "nodes": [
                            {
                                "id": "fused:文档:1",
                                "type": "文档",
                                "level": "root",
                                "properties": {"title": "Example"},
                            },
                            {
                                "id": "fused:催化剂:2",
                                "type": "催化剂",
                                "level": "root",
                                "properties": {"display_name": "Ru/CeO₂"},
                            },
                        ],
                        "edges": [
                            {"source": "fused:文档:1", "relation": "提及", "target": "fused:催化剂:2"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            driver = FakeDriver()
            report_path = store_entity_graph(
                graph_path=graph_path,
                env_file=env_path,
                verbose=False,
                driver_factory=lambda uri, auth: driver,
            )

            self.assertTrue(driver.closed)
            self.assertEqual(driver.database, "neo4j")
            self.assertEqual(report_path, root / "entity_graph_storage_report.json")
            self.assertTrue(report_path.exists())
            self.assertTrue((root / "entity_graph_storage_ready.json").exists())

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["node_count"], 2)
            self.assertEqual(report["edge_count"], 1)
            self.assertEqual(report["status"], "stored")
            self.assertIn("storage_ready_path", report)

            queries = "\n".join(query for query, _ in driver.session_obj.calls)
            self.assertIn("CREATE CONSTRAINT IF NOT EXISTS", queries)
            self.assertIn("MERGE (n:`文档`", queries)
            self.assertIn("MERGE (n:`催化剂`", queries)
            self.assertIn("MERGE (a)-[r:`提及`]->(b)", queries)

    def test_store_entity_graph_drops_nested_properties_outside_storage_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            env_path = root / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "NEO4J_URI=bolt://localhost:7687",
                        "NEO4J_USERNAME=neo4j",
                        "NEO4J_PASSWORD=test-password",
                        "NEO4J_DATABASE=neo4j",
                    ]
                ),
                encoding="utf-8",
            )

            graph_path = root / "entity_graph_fused.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "document": {"doc_id": "doc-1"},
                        "nodes": [
                            {
                                "id": "fused:助剂:1",
                                "type": "助剂",
                                "level": "root",
                                "properties": {
                                    "display_name": "K",
                                    "助剂含量": [{"value": "1.5", "unit": "%"}],
                                },
                            }
                        ],
                        "edges": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            driver = FakeDriver()
            store_entity_graph(
                graph_path=graph_path,
                env_file=env_path,
                verbose=False,
                driver_factory=lambda uri, auth: driver,
            )

            props_payloads = [params["props"] for _, params in driver.session_obj.calls if "props" in params]
            self.assertEqual(len(props_payloads), 1)
            self.assertNotIn("助剂含量", props_payloads[0])
            self.assertEqual(props_payloads[0]["display_name"], "K")


if __name__ == "__main__":
    unittest.main()
