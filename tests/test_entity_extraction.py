import json
import io
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout

from scr.knowledge_graph.entity_extraction import (
    build_graph_draft,
    extract_graph_from_ocr_run,
    load_runtime_ontology,
    parse_grouped_output,
)


class EntityExtractionTestCase(unittest.TestCase):
    def test_parse_grouped_output_parses_json_object(self) -> None:
        raw_output = """
        {
          "document": {"title": "Example paper"},
          "催化剂": [
            {
              "name": "Fe catalyst",
              "活性组分": [{"name": "Fe"}],
              "助剂": [
                {
                  "name": "K2O",
                  "助剂含量": [{"value": "1.0", "unit": "wt%"}]
                }
              ]
            }
          ]
        }
        """
        parsed = parse_grouped_output(raw_output)
        self.assertEqual(parsed["document"]["title"], "Example paper")
        self.assertEqual(parsed["催化剂"][0]["name"], "Fe catalyst")
        self.assertEqual(parsed["催化剂"][0]["助剂"][0]["name"], "K2O")

    def test_build_graph_draft_builds_nodes_and_edges_from_grouped_output(self) -> None:
        grouped_output = {
            "document": {"title": "Example paper"},
            "催化剂": [
                {
                    "name": "Fe catalyst",
                    "活性组分": [{"name": "Fe"}],
                    "助剂": [
                        {
                            "name": "K2O",
                            "助剂含量": [{"value": "1.0", "unit": "wt%"}],
                            "助剂种类": [{"name": "电子助剂"}],
                        }
                    ],
                    "反应条件": [
                        {
                            "name": "Condition A",
                            "温度": [{"value": "450", "unit": "C"}],
                            "压力": [{"value": "10", "unit": "MPa"}],
                        }
                    ],
                }
            ],
        }
        ontology_bundle = load_runtime_ontology()

        graph = build_graph_draft(
            grouped_output=grouped_output,
            ontology_bundle=ontology_bundle,
            doc_context={"doc_id": "doc-001", "filename": "paper.pdf"},
        )

        node_types = {node["type"] for node in graph["nodes"]}
        edge_types = {edge["relation"] for edge in graph["edges"]}

        self.assertIn("文档", node_types)
        self.assertIn("催化剂", node_types)
        self.assertIn("活性组分", node_types)
        self.assertIn("助剂", node_types)
        self.assertIn("助剂含量", node_types)
        self.assertIn("反应条件", node_types)
        self.assertIn("温度", node_types)
        self.assertIn("提及", edge_types)
        self.assertIn("有活性组分", edge_types)
        self.assertIn("有助剂", edge_types)
        self.assertIn("有助剂含量", edge_types)
        self.assertIn("有反应条件", edge_types)
        self.assertIn("有温度", edge_types)

    def test_extract_graph_from_ocr_run_writes_graph_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            run_dir = tmp_path / "artifacts" / "ocr" / "paper" / "run_20260331_050000"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "document.md").write_text("# OCR markdown", encoding="utf-8")

            raw_output = json.dumps(
                {
                    "document": {"title": "Example paper"},
                    "催化剂": [
                        {
                            "name": "Fe catalyst",
                            "活性组分": [{"name": "Fe"}],
                        }
                    ],
                },
                ensure_ascii=False,
            )

            result = extract_graph_from_ocr_run(
                run_dir=run_dir,
                llm_client=lambda prompt, model=None: raw_output,
                llm_model="Qwen3.5-27B",
                verbose=False,
            )

            output_dir = run_dir / "knowledge_graph"
            self.assertEqual(result, output_dir / "entity_graph.json")
            self.assertTrue((output_dir / "entity_graph.json").exists())
            self.assertTrue((output_dir / "entity_graph_raw.txt").exists())

            data = json.loads((output_dir / "entity_graph.json").read_text(encoding="utf-8"))
            self.assertEqual(data["document"]["title"], "Example paper")
            self.assertTrue(any(node["type"] == "催化剂" for node in data["nodes"]))
            self.assertTrue(any(edge["relation"] == "提及" for edge in data["edges"]))

    def test_extract_graph_from_ocr_run_prints_stage_logs_when_verbose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            run_dir = tmp_path / "artifacts" / "ocr" / "paper" / "run_20260331_050001"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "document.md").write_text("# OCR markdown", encoding="utf-8")

            raw_output = json.dumps(
                {
                    "document": {"title": "Example paper"},
                    "催化剂": [{"name": "Fe catalyst"}],
                },
                ensure_ascii=False,
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                extract_graph_from_ocr_run(
                    run_dir=run_dir,
                    llm_client=lambda prompt, model=None, verbose=False: raw_output,
                    llm_model="Qwen3.5-27B",
                    verbose=True,
                )

            output = buffer.getvalue()
            self.assertIn("[entity_extraction] loading ontology...", output)
            self.assertIn("[entity_extraction] calling KG LLM...", output)
            self.assertIn("[entity_extraction] completed:", output)


if __name__ == "__main__":
    unittest.main()
