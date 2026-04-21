from __future__ import annotations

import unittest

from scr.ocr.paddle_structured import build_structured_markdown


class PaddleStructuredMarkdownTestCase(unittest.TestCase):
    def test_build_structured_markdown_marks_images_and_tables(self) -> None:
        data = {
            "result": {
                "layoutParsingResults": [
                    {
                        "markdown": {
                            "text": "\n".join(
                                [
                                    "表 1 催化剂 XRF 测得实际组分含量",
                                    '<table border=1><tr><td>A</td></tr></table>',
                                    "图 1 助剂添加量对活性的影响",
                                    '<div style=\"text-align: center;\"><img src=\"imgs/a.jpg\" alt=\"Image\" /></div>',
                                    "Figure 1 Effect of promoters on activity",
                                ]
                            ),
                            "images": {"imgs/a.jpg": "http://example/a.jpg"},
                        },
                        "outputImages": {"layout_det_res": "http://example/chart.jpg"},
                        "prunedResult": {
                            "parsing_res_list": [
                                {
                                    "block_label": "figure_title",
                                    "block_content": "图 1 助剂添加量对活性的影响",
                                    "block_bbox": [100, 100, 400, 150],
                                },
                                {
                                    "block_label": "chart",
                                    "block_content": "助剂含量 | 氨浓度\n1.0 | 8.3\n2.0 | 10.5",
                                    "block_bbox": [120, 160, 420, 500],
                                },
                                {
                                    "block_label": "table",
                                    "block_content": "<table><tr><td>A</td></tr></table>",
                                    "block_bbox": [80, 520, 500, 700],
                                },
                            ]
                        },
                    }
                ]
            }
        }

        text = build_structured_markdown(data)

        self.assertIn("### IMAGE_BLOCK", text)
        self.assertIn("image_path: imgs/a.jpg", text)
        self.assertIn("## PAGE_IMAGES", text)
        self.assertNotIn("- layout_det_res", text)
        self.assertIn("## 图表结构化信息", text)
        self.assertNotIn("## PAGE_PARSED_BLOCKS", text)
        self.assertIn("### 图 1 助剂添加量对活性的影响", text)
        self.assertIn("<table><tr><td>A</td></tr></table>", text)
        self.assertIn("助剂含量 | 氨浓度", text)

    def test_chart_and_table_bind_to_matching_title_types(self) -> None:
        data = {
            "result": {
                "layoutParsingResults": [
                    {
                        "markdown": {"text": "", "images": {}},
                        "outputImages": {},
                        "prunedResult": {
                            "parsing_res_list": [
                                {
                                    "block_label": "figure_title",
                                    "block_content": "图 1 单助剂活性变化",
                                    "block_bbox": [100, 100, 400, 130],
                                },
                                {
                                    "block_label": "figure_title",
                                    "block_content": "表 1 XRF 实际组分含量",
                                    "block_bbox": [100, 500, 400, 530],
                                },
                                {
                                    "block_label": "chart",
                                    "block_content": "sample | value\nA | 1",
                                    "block_bbox": [100, 140, 420, 420],
                                },
                                {
                                    "block_label": "table",
                                    "block_content": "<table><tr><td>A</td></tr></table>",
                                    "block_bbox": [100, 540, 420, 780],
                                },
                            ]
                        },
                    }
                ]
            }
        }

        text = build_structured_markdown(data)
        self.assertIn("### 图 1 单助剂活性变化", text)
        self.assertIn("### 表 1 XRF 实际组分含量", text)
        self.assertNotIn("### 表 1 XRF 实际组分含量\n\nsample | value", text)


if __name__ == "__main__":
    unittest.main()
