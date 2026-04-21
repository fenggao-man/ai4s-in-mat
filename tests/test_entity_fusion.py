import json
import tempfile
import unittest
from pathlib import Path

from scr.knowledge_graph.entity_fusion import build_fused_graph, fuse_entity_graph


class EntityFusionTestCase(unittest.TestCase):
    def test_build_fused_graph_aggregates_aliases_and_sources(self) -> None:
        graph = {
            "document": {"doc_id": "doc-1", "title": "Example"},
            "nodes": [
                {
                    "id": "催化剂:1",
                    "type": "催化剂",
                    "level": "root",
                    "properties": {
                        "original_name": "Ru:CeO2",
                        "display_name": "Ru/CeO₂",
                    },
                },
                {
                    "id": "催化剂:2",
                    "type": "催化剂",
                    "level": "root",
                    "properties": {
                        "original_name": "Ru/CeO2",
                        "display_name": "Ru/CeO₂",
                    },
                },
            ],
            "edges": [
                {"source": "文档:1", "relation": "提及", "target": "催化剂:1"},
                {"source": "文档:1", "relation": "提及", "target": "催化剂:2"},
            ],
        }

        fused = build_fused_graph(graph)
        catalyst_nodes = [node for node in fused["nodes"] if node["type"] == "催化剂"]

        self.assertEqual(len(catalyst_nodes), 1)
        props = catalyst_nodes[0]["properties"]
        self.assertEqual(props["display_name"], "Ru/CeO₂")
        self.assertEqual(props["merged_from_count"], 2)
        self.assertEqual(props["fusion_status"], "merged")
        self.assertIn("Ru:CeO2", props["aliases"])
        self.assertIn("Ru/CeO2", props["aliases"])
        self.assertEqual(len(fused["edges"]), 1)

    def test_fuse_entity_graph_writes_fused_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph_path = root / "entity_graph_aligned.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "document": {"doc_id": "doc-1", "title": "Example"},
                        "nodes": [
                            {
                                "id": "表征方法:1",
                                "type": "表征方法",
                                "level": "root",
                                "properties": {
                                    "display_name": "H₂-TPR",
                                    "original_name": "H2-TPR",
                                },
                            }
                        ],
                        "edges": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output_path = fuse_entity_graph(graph_path, verbose=False)

            self.assertEqual(output_path, root / "entity_graph_fused.json")
            self.assertTrue(output_path.exists())
            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(data["nodes"][0]["properties"]["fusion_status"], "single")


if __name__ == "__main__":
    unittest.main()
