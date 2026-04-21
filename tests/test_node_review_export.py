import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from scr.knowledge_graph.node_review_export import export_node_review_excel


NAMESPACE = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class NodeReviewExportTestCase(unittest.TestCase):
    def test_export_node_review_excel_writes_two_sheet_xlsx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            json_path = root / "annotation.json"
            output_path = root / "review.xlsx"
            json_path.write_text(
                json.dumps(
                    {
                        "document": {
                            "title": "Example Paper",
                            "source": "Example Journal",
                            "filename": "example.pdf",
                        },
                        "nodes": [
                            {
                                "id": "n1",
                                "type": "催化剂",
                                "properties": {
                                    "display_name": "Ru/CeO₂",
                                    "original_name": "Ru/CeO2",
                                    "evidence_text": "Ru/CeO2 catalyst",
                                },
                            },
                            {
                                "id": "n2",
                                "type": "粒径",
                                "properties": {
                                    "value": "9.3",
                                    "unit": "nm",
                                    "display_name": "9.3 nm",
                                    "original_name": "9.3nm",
                                    "evidence_text": "particle size was 9.3 nm",
                                },
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = export_node_review_excel(json_path=json_path, output_path=output_path)

            self.assertEqual(result, output_path)
            self.assertTrue(output_path.exists())

            with zipfile.ZipFile(output_path, "r") as archive:
                names = set(archive.namelist())
                self.assertIn("xl/workbook.xml", names)
                self.assertIn("xl/worksheets/sheet1.xml", names)
                self.assertIn("xl/worksheets/sheet2.xml", names)

                workbook = ET.fromstring(archive.read("xl/workbook.xml"))
                sheet_names = [
                    node.attrib["name"]
                    for node in workbook.findall(".//a:sheets/a:sheet", NAMESPACE)
                ]
                self.assertEqual(sheet_names, ["NodeSummary", "NodeReview"])

                sheet1 = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
                sheet2 = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")

                self.assertIn("paper_title", sheet1)
                self.assertIn("node_type", sheet1)
                self.assertIn("sample_values", sheet1)
                self.assertIn("Example Paper", sheet1)
                self.assertIn("催化剂", sheet1)

                self.assertIn("node_id", sheet2)
                self.assertIn("display_name", sheet2)
                self.assertIn("review_status", sheet2)
                self.assertIn("review_comment", sheet2)
                self.assertIn("corrected_value", sheet2)
                self.assertIn("Ru/CeO₂", sheet2)
                self.assertIn("9.3 nm", sheet2)


if __name__ == "__main__":
    unittest.main()
