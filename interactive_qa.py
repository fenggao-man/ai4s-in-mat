import os
import json
from pathlib import Path
from typing import List

from scr.knowledge_graph.llm_client import load_env_file
from rag_qa import extract_keywords, retrieve_rag_context, generate_rag_answer

# 路径配置
PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"

# 加载环境变量
load_env_file(ENV_FILE)

def interactive_qa_with_recall():
    """
    交互式问答并计算召回率
    """
    print(f"\n{'='*60}")
    print("  AI4S 材料科学知识问答与召回率评测系统")
    print(f"{'='*60}")
    
    query = input("\n请输入你的材料学问题: ").strip()
    if not query:
        print("问题不能为空。")
        return

    golden_input = input("请输入预期找回的关键词 (用中文逗号分隔，如: Ru, 400度, 0.49): ").strip()
    golden_entities = [g.strip() for g in golden_input.replace("，", ",").split(",") if g.strip()]
    
    print(f"\n{'-'*20} 正在处理 {'-'*20}")
    
    # 1. 提取关键词
    keywords = extract_keywords(query, verbose=False)
    print(f"[*] 搜索关键词: {keywords}")
    
    # 2. 检索上下文
    context = retrieve_rag_context(keywords, verbose=False)
    
    # 3. 计算召回率
    hits = []
    for golden in golden_entities:
        if golden.lower() in context.lower():
            hits.append(golden)
    
    recall = len(hits) / len(golden_entities) if golden_entities else 0
    
    print(f"[*] 召回率分析:")
    print(f"    - 预期目标: {golden_entities}")
    print(f"    - 实际命中: {hits}")
    print(f"    - 召回得分: {recall:.2%}")

    # 4. 生成回答
    if context:
        answer = generate_rag_answer(query, context, verbose=False)
        print(f"\n[AI 回答]:\n{answer}")
    else:
        print("\n[!] 知识库中未找到相关信息。")

    print(f"\n{'='*60}")

if __name__ == "__main__":
    interactive_qa_with_recall()
