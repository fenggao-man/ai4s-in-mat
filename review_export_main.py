from __future__ import annotations

from pathlib import Path

from scr.knowledge_graph.node_review_export import export_node_review_excel


PROJECT_ROOT = Path(__file__).resolve().parent

# Manual test target
TEST_JSON_PATH = PROJECT_ROOT / "artifacts" / "annotation" / "Promotion of Nb2O5 on the wustite-based iron catalyst for ammonia synthesis.json"
TEST_OUTPUT_XLSX = PROJECT_ROOT / "artifacts" / "annotation" / "Promotion of Nb2O5 on the wustite-based iron catalyst for ammonia synthesis.xlsx"


def test_node_review_export() -> None:
    print(f"[review_export] source json: {TEST_JSON_PATH}", flush=True)
    output_path = export_node_review_excel(
        json_path=TEST_JSON_PATH,
        output_path=TEST_OUTPUT_XLSX,
    )
    print(f"[review_export] output xlsx: {output_path}", flush=True)


if __name__ == "__main__":
    test_node_review_export()
