import json
import tempfile
import unittest
from pathlib import Path

from scr.knowledge_graph.entity_alignment import align_entity_graph, build_aligned_graph


class EntityAlignmentTestCase(unittest.TestCase):
    def test_build_aligned_graph_normalizes_display_name(self) -> None:
        graph = {
            "document": {"doc_id": "doc-1", "title": "Example"},
            "nodes": [
                {
                    "id": "催化剂:1",
                    "type": "催化剂",
                    "level": "root",
                    "properties": {"name": "Ru:CeO2-K"},
                },
                {
                    "id": "温度:2",
                    "type": "温度",
                    "level": "child",
                    "properties": {"value": "450", "unit": "C"},
                },
                {
                    "id": "表征方法:3",
                    "type": "表征方法",
                    "level": "root",
                    "properties": {"name": "H2-TPR"},
                },
            ],
            "edges": [],
        }

        aligned = build_aligned_graph(graph)
        catalyst = aligned["nodes"][0]
        temperature = aligned["nodes"][1]
        method = aligned["nodes"][2]

        self.assertEqual(catalyst["properties"]["display_name"], "Ru/CeO₂-K")
        self.assertEqual(catalyst["properties"]["original_name"], "Ru:CeO2-K")
        self.assertEqual(temperature["properties"]["display_name"], "450 °C")
        self.assertEqual(temperature["properties"]["unit"], "°C")
        self.assertEqual(method["properties"]["display_name"], "H₂-TPR")

    def test_build_aligned_graph_deduplicates_same_type_same_display_name(self) -> None:
        graph = {
            "document": {"doc_id": "doc-1", "title": "Example"},
            "nodes": [
                {
                    "id": "催化剂:1",
                    "type": "催化剂",
                    "level": "root",
                    "properties": {"name": "Ru:CeO2"},
                },
                {
                    "id": "催化剂:2",
                    "type": "催化剂",
                    "level": "root",
                    "properties": {"name": "Ru/CeO2"},
                },
            ],
            "edges": [
                {"source": "文档:0", "relation": "提及", "target": "催化剂:1"},
                {"source": "文档:0", "relation": "提及", "target": "催化剂:2"},
            ],
        }

        aligned = build_aligned_graph(graph)
        catalyst_nodes = [node for node in aligned["nodes"] if node["type"] == "催化剂"]

        self.assertEqual(len(catalyst_nodes), 1)
        self.assertEqual(catalyst_nodes[0]["properties"]["display_name"], "Ru/CeO₂")
        self.assertEqual(len(aligned["edges"]), 1)
        self.assertEqual(aligned["edges"][0]["target"], catalyst_nodes[0]["id"])

    def test_align_entity_graph_writes_aligned_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph_path = root / "entity_graph.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "document": {"doc_id": "doc-1", "title": "Example"},
                        "nodes": [
                            {
                                "id": "催化剂:1",
                                "type": "催化剂",
                                "level": "root",
                                "properties": {"name": "Ru:CeO2"},
                            }
                        ],
                        "edges": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output_path = align_entity_graph(graph_path, verbose=False)

            self.assertEqual(output_path, root / "entity_graph_aligned.json")
            self.assertTrue(output_path.exists())
            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(data["nodes"][0]["properties"]["display_name"], "Ru/CeO₂")


if __name__ == "__main__":
    unittest.main()
