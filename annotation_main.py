from __future__ import annotations

import json
from pathlib import Path

from scr.knowledge_graph.llm_client import call_kg_llm


PROJECT_ROOT = Path(__file__).resolve().parent

# 配置
PROMPT_FILE = PROJECT_ROOT / "artifacts" / "annotation" / "Prompt.md"
INPUT_MARKDOWN = PROJECT_ROOT / "artifacts" / "ocr" / "助剂对Ru_CeO2催化剂的表面性质及氨合成性能的影响" / "run_20260401_091545" / "document.md"
OUTPUT_JSON = PROJECT_ROOT / "artifacts" / "annotation" / "助剂对Ru_CeO2催化剂的表面性质及氨合成性能的影响_updated.json"


def load_prompt_template(prompt_file: Path) -> str:
    """加载prompt模板"""
    return prompt_file.read_text(encoding="utf-8")


def load_document_text(markdown_file: Path) -> str:
    """加载文档文本"""
    return markdown_file.read_text(encoding="utf-8")


def build_annotation_prompt(prompt_template: str, document_text: str) -> str:
    """构建标注prompt"""
    return prompt_template.replace("{{PAPER_TEXT}}", document_text)


def process_llm_output(raw_output: str) -> dict:
    """处理LLM输出"""
    # 清理输出
    cleaned = raw_output.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    
    # 解析JSON
    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("LLM输出必须是一个JSON对象")
        return parsed
    except json.JSONDecodeError as e:
        raise ValueError(f"无法解析LLM输出为JSON: {e}")


def save_annotation_result(output_path: Path, annotation_data: dict) -> None:
    """保存标注结果"""
    output_path.write_text(json.dumps(annotation_data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """主函数"""
    print("[annotation] 加载prompt模板...")
    prompt_template = load_prompt_template(PROMPT_FILE)
    
    print("[annotation] 加载文档文本...")
    document_text = load_document_text(INPUT_MARKDOWN)
    
    print("[annotation] 构建标注prompt...")
    prompt = build_annotation_prompt(prompt_template, document_text)
    
    print("[annotation] 调用LLM进行标注...")
    raw_output = call_kg_llm(prompt, verbose=True)
    
    print("[annotation] 处理LLM输出...")
    annotation_data = process_llm_output(raw_output)
    
    print("[annotation] 保存标注结果...")
    save_annotation_result(OUTPUT_JSON, annotation_data)
    
    print(f"[annotation] 标注完成，结果保存至: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
