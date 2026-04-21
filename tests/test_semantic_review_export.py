from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from scr.knowledge_graph.semantic_review_export import (
    export_expert_review_excel,
    export_semantic_review_excel,
)


class SemanticReviewExportTestCase(unittest.TestCase):
    def test_export_semantic_review_excel_writes_expected_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "annotation.json"
            output_path = Path(tmpdir) / "semantic_review.xlsx"
            json_path.write_text(
                json.dumps(
                    {
                        "document": {
                            "title": "示例论文",
                            "source": "示例来源",
                            "filename": "demo.pdf",
                        },
                        "nodes": [
                            {
                                "id": "n1",
                                "type": "催化剂",
                                "properties": {
                                    "display_name": "Ru/CeO₂",
                                    "evidence_text": "表 1 中列出了 Ru/CeO2 样品。",
                                },
                            },
                            {
                                "id": "n2",
                                "type": "BET",
                                "properties": {
                                    "display_name": "BET",
                                    "evidence_text": "BET 用于测定比表面积和孔径分布。",
                                },
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = export_semantic_review_excel(json_path=json_path, output_path=output_path)

            self.assertEqual(result, output_path)
            self.assertTrue(output_path.exists())

            with zipfile.ZipFile(output_path) as archive:
                workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
                ns = {
                    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                }
                sheet_names = [sheet.attrib["name"] for sheet in workbook_xml.findall("a:sheets/a:sheet", ns)]
                self.assertEqual(
                    sheet_names,
                    ["PaperSummary", "CatalystSamples", "CharacterizationView", "MechanismView"],
                )

                catalyst_sheet = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
                self.assertIn("Ru/CeO₂", catalyst_sheet)
                self.assertIn("待补：催化性能", catalyst_sheet)

    def test_export_semantic_review_excel_supports_sample_assertion_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "annotation_v2.json"
            output_path = Path(tmpdir) / "semantic_review_v2.xlsx"
            json_path.write_text(
                json.dumps(
                    {
                        "document": {
                            "title": "示例论文V2",
                            "source": "structured markdown",
                            "filename": "document_structured.md",
                            "evidence_text": "标题来自 structured markdown",
                            "evidence_anchor": "标题",
                        },
                        "sample_inventory": [
                            {
                                "sample_id": "s1",
                                "display_name": "Ru/CeO₂",
                                "original_names": ["Ru/CeO₂"],
                                "sample_category": "base_sample",
                                "promoters": [],
                                "promoter_contents": [],
                                "sample_key_components": ["Ru", "CeO₂"],
                                "sample_identity_evidence": "表 1 列出 Ru/CeO₂ 样品。",
                                "evidence_anchor": "表 1",
                            }
                        ],
                        "sample_assertions": [
                            {
                                "assertion_id": "a1",
                                "sample_refs": ["s1"],
                                "assertion_type": "performance",
                                "property_name": "NH3 concentration",
                                "value_type": "numeric",
                                "property_value": "12.6",
                                "unit": "%",
                                "method": "",
                                "condition_context": "425 °C / 10 MPa",
                                "comparison_context": "",
                                "source_type": "table",
                                "support_level": "direct",
                                "evidence_text": "Ru/CeO₂ 在 425 °C、10 MPa 下氨浓度为 12.6%。",
                                "evidence_anchor": "表 3",
                            }
                        ],
                        "figure_assertions": [
                            {
                                "figure_assertion_id": "f1",
                                "figure_id": "图 1",
                                "sample_refs": ["s1"],
                                "figure_type": "performance_curve",
                                "visual_information": "展示活性趋势。",
                                "conclusion": "Cs 系列活性更高。",
                                "evidence_text": "图 1 显示 Cs 系列整体更高。",
                                "evidence_anchor": "图 1",
                            }
                        ],
                        "review_flags": [
                            {
                                "flag_id": "r1",
                                "related_sample_refs": ["s1"],
                                "issue_type": "text_figure_conflict",
                                "issue": "图表和正文存在差异",
                                "evidence_text": "图 1 与正文 2.2 的数值不同。",
                                "evidence_anchor": "图 1 + 正文 2.2",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = export_semantic_review_excel(json_path=json_path, output_path=output_path)

            self.assertEqual(result, output_path)
            self.assertTrue(output_path.exists())

            with zipfile.ZipFile(output_path) as archive:
                workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
                ns = {
                    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                }
                sheet_names = [sheet.attrib["name"] for sheet in workbook_xml.findall("a:sheets/a:sheet", ns)]
                self.assertEqual(
                    sheet_names,
                    ["PaperSummary", "Samples", "Assertions", "ReviewFlags", "FigureAssertions"],
                )

                samples_sheet = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
                assertions_sheet = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
                flags_sheet = archive.read("xl/worksheets/sheet4.xml").decode("utf-8")

                self.assertIn("Ru/CeO₂", samples_sheet)
                self.assertIn("NH3 concentration", assertions_sheet)
                self.assertIn("text_figure_conflict", flags_sheet)

    def test_export_expert_review_excel_supports_expert_friendly_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "annotation_v2.json"
            output_path = Path(tmpdir) / "expert_review.xlsx"
            json_path.write_text(
                json.dumps(
                    {
                        "document": {
                            "title": "示例论文V2",
                            "source": "structured markdown",
                            "filename": "document_structured.md",
                            "evidence_text": "标题来自 structured markdown",
                            "evidence_anchor": "标题",
                        },
                        "sample_inventory": [
                            {
                                "sample_id": "s1",
                                "display_name": "Ru/CeO₂",
                                "original_names": ["Ru/CeO₂"],
                                "sample_category": "base_sample",
                                "promoters": [],
                                "promoter_contents": [],
                                "sample_key_components": ["Ru", "CeO₂"],
                                "sample_identity_evidence": "表 1 列出 Ru/CeO₂ 样品。",
                                "evidence_anchor": "表 1",
                            }
                        ],
                        "sample_assertions": [
                            {
                                "assertion_id": "a1",
                                "sample_refs": ["s1"],
                                "assertion_type": "preparation",
                                "property_name": "preparation route",
                                "value_type": "text_conclusion",
                                "property_value": "coprecipitation + impregnation",
                                "unit": "",
                                "method": "",
                                "condition_context": "",
                                "comparison_context": "",
                                "source_type": "text",
                                "support_level": "direct",
                                "evidence_text": "样品经共沉淀和浸渍法制备。",
                                "evidence_anchor": "1.1",
                            },
                            {
                                "assertion_id": "a2",
                                "sample_refs": ["s1"],
                                "assertion_type": "performance",
                                "property_name": "NH3 concentration",
                                "value_type": "numeric",
                                "property_value": "12.6",
                                "unit": "%",
                                "method": "",
                                "condition_context": "425 °C / 10 MPa",
                                "comparison_context": "",
                                "source_type": "table",
                                "support_level": "direct",
                                "evidence_text": "Ru/CeO₂ 在 425 °C、10 MPa 下氨浓度为 12.6%。",
                                "evidence_anchor": "表 3",
                            },
                            {
                                "assertion_id": "a3",
                                "sample_refs": ["s1"],
                                "assertion_type": "characterization",
                                "property_name": "BET surface area",
                                "value_type": "numeric",
                                "property_value": "120",
                                "unit": "m2 g-1",
                                "method": "BET",
                                "condition_context": "",
                                "comparison_context": "",
                                "source_type": "table",
                                "support_level": "direct",
                                "evidence_text": "Ru/CeO₂ 的 BET 比表面积为 120 m2 g-1。",
                                "evidence_anchor": "表 2",
                            },
                            {
                                "assertion_id": "a4",
                                "sample_refs": ["s1"],
                                "assertion_type": "mechanism",
                                "property_name": "dominant catalytic factor",
                                "value_type": "text_conclusion",
                                "property_value": "electronic effect",
                                "unit": "",
                                "method": "",
                                "condition_context": "",
                                "comparison_context": "",
                                "source_type": "text",
                                "support_level": "direct",
                                "evidence_text": "电子效应是主要因素。",
                                "evidence_anchor": "摘要",
                            },
                        ],
                        "review_flags": [
                            {
                                "flag_id": "r1",
                                "related_sample_refs": ["s1"],
                                "issue_type": "text_figure_conflict",
                                "issue": "图表和正文存在差异",
                                "evidence_text": "图 1 与正文 2.2 的数值不同。",
                                "evidence_anchor": "图 1 + 正文 2.2",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = export_expert_review_excel(json_path=json_path, output_path=output_path)

            self.assertEqual(result, output_path)
            self.assertTrue(output_path.exists())

            with zipfile.ZipFile(output_path) as archive:
                workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
                ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                sheet_names = [sheet.attrib["name"] for sheet in workbook_xml.findall("a:sheets/a:sheet", ns)]
                self.assertEqual(
                    sheet_names,
                    ["PaperSummary", "SampleOverview", "PerformanceView", "CharacterizationView", "MechanismView", "ReviewFlags", "OntologyView"],
                )

                sample_sheet = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
                performance_sheet = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
                characterization_sheet = archive.read("xl/worksheets/sheet4.xml").decode("utf-8")
                mechanism_sheet = archive.read("xl/worksheets/sheet5.xml").decode("utf-8")
                flags_sheet = archive.read("xl/worksheets/sheet6.xml").decode("utf-8")
                ontology_sheet = archive.read("xl/worksheets/sheet7.xml").decode("utf-8")

                self.assertIn("Ru/CeO₂", sample_sheet)
                self.assertIn("NH3 concentration", performance_sheet)
                self.assertIn("BET surface area", characterization_sheet)
                self.assertIn("electronic effect", mechanism_sheet)
                self.assertIn("text_figure_conflict", flags_sheet)
                self.assertIn("活性组分", ontology_sheet)
                self.assertIn("晶相结构", ontology_sheet)


if __name__ == "__main__":
    unittest.main()
