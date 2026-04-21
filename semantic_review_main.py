from __future__ import annotations

from pathlib import Path

from scr.knowledge_graph.semantic_review_export import export_semantic_review_excel


PROJECT_ROOT = Path(__file__).resolve().parent

# Manual test target
TEST_JSON_PATH = PROJECT_ROOT / "artifacts" / "annotation" / "助剂对Ru_CeO2催化剂的表面性质及氨合成性能的影响.json"
TEST_OUTPUT_XLSX = PROJECT_ROOT / "artifacts" / "annotation" / "助剂对Ru_CeO2催化剂的表面性质及氨合成性能的影响_semantic_review_final.xlsx"


def test_semantic_review_export() -> None:
    print(f"[semantic_review] source json: {TEST_JSON_PATH}", flush=True)
    output_path = export_semantic_review_excel(
        json_path=TEST_JSON_PATH,
        output_path=TEST_OUTPUT_XLSX,
    )
    print(f"[semantic_review] output xlsx: {output_path}", flush=True)


if __name__ == "__main__":
    test_semantic_review_export()
