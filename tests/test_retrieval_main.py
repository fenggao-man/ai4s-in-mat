import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from retrieval_main import index_knowledge_graph, main, retrieve_knowledge


class RetrievalMainTestCase(unittest.TestCase):
    def test_index_and_retrieve_knowledge_through_interfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph_path = root / "entity_graph_fused.json"
            markdown_path = root / "document.md"
            db_path = root / "kg.sqlite3"
            graph_path.write_text(json.dumps(_sample_graph(), ensure_ascii=False), encoding="utf-8")
            markdown_path.write_text("Ru/CeO2 catalyst has CeO2 support.", encoding="utf-8")

            index_report = index_knowledge_graph(
                graph_path=graph_path,
                db_path=db_path,
                document_markdown_path=markdown_path,
            )
            result = retrieve_knowledge("CeO2", db_path=db_path, limit=5, hops=1)

            self.assertEqual(index_report["status"], "indexed")
            self.assertTrue(any(node["display_name"] == "CeO2" for node in result["nodes"]))
            self.assertTrue(any("CeO2" in chunk["text"] for chunk in result["chunks"]))

    def test_main_indexes_and_searches_with_cli_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph_path = root / "entity_graph_fused.json"
            markdown_path = root / "document.md"
            db_path = root / "kg.sqlite3"
            graph_path.write_text(json.dumps(_sample_graph(), ensure_ascii=False), encoding="utf-8")
            markdown_path.write_text("Ru/CeO2 catalyst has CeO2 support.", encoding="utf-8")

            index_stdout = io.StringIO()
            with redirect_stdout(index_stdout):
                index_exit_code = main(
                    [
                        "index",
                        "--graph-path",
                        str(graph_path),
                        "--markdown-path",
                        str(markdown_path),
                        "--db-path",
                        str(db_path),
                    ]
                )
            index_payload = json.loads(index_stdout.getvalue())

            search_stdout = io.StringIO()
            with redirect_stdout(search_stdout):
                search_exit_code = main(["search", "Ru/CeO2", "--db-path", str(db_path)])
            search_payload = json.loads(search_stdout.getvalue())

            self.assertEqual(index_exit_code, 0)
            self.assertEqual(search_exit_code, 0)
            self.assertEqual(index_payload["status"], "indexed")
            self.assertTrue(any(node["display_name"] == "Ru/CeO2" for node in search_payload["nodes"]))


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
        ],
        "edges": [
            {"source": "fused:催化剂:1", "relation": "有助剂", "target": "fused:助剂:2"},
        ],
    }


if __name__ == "__main__":
    unittest.main()
