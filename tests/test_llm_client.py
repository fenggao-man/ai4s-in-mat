import unittest

from scr.knowledge_graph.llm_client import strip_reasoning_blocks


class LlmClientTestCase(unittest.TestCase):
    def test_strip_reasoning_blocks_removes_think_content(self) -> None:
        text = "<think>先分析一下，不能给下游。</think>\n\nRu/CeO2, 400度, 氨合成活性"

        self.assertEqual(strip_reasoning_blocks(text), "Ru/CeO2, 400度, 氨合成活性")

    def test_strip_reasoning_blocks_preserves_plain_content(self) -> None:
        text = "Ru/CeO2, 400度, 氨合成活性"

        self.assertEqual(strip_reasoning_blocks(text), text)

    def test_strip_reasoning_blocks_handles_multiline_and_attributes(self) -> None:
        text = "<think type=\"reasoning\">第一行\n第二行</think>\n答案正文"

        self.assertEqual(strip_reasoning_blocks(text), "答案正文")


if __name__ == "__main__":
    unittest.main()
