import os
import json
from pathlib import Path
from typing import List, Dict

from scr.knowledge_graph.llm_client import call_kg_llm, load_env_file
from rag_qa import extract_keywords, retrieve_rag_context, generate_rag_answer

# 路径配置
PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"

# 加载环境变量
load_env_file(ENV_FILE)

def auto_generate_ground_truth(query: str, verbose: bool = False) -> List[str]:
    """
    让 LLM 充当“出题人”，根据问题预测应该找回的核心知识点
    """
    prompt = f"""
你是一个材料科学专家。针对以下用户提出的问题，请列出要在知识库中回答该问题所必须找回的“核心知识点”（Golden Entities）。
这些知识点应包括：
1. 具体的催化剂化学式（如 Ru/CeO2）
2. 关键的实验参数（如 400度）
3. 预期的性能指标名称（如 氨合成活性、TOF）

用户问题：{query}

请直接返回知识点列表，用中文逗号分隔，不要有任何解释。
例如：Ru/CeO2, 400度, 氨合成活性, TOF
"""
    if verbose:
        print("[*] 正在自动生成预期知识点...")
    
    response = call_kg_llm(prompt, verbose=verbose)
    ground_truth = [g.strip() for g in response.replace("，", ",").split(",") if g.strip()]
    return ground_truth

def auto_eval_qa_pipeline():
    """
    全自动问答与召回率评估
    """
    print(f"\n{'='*60}")
    print("  AI4S 全自动 RAG 问答与自我评估系统")
    print(f"{'='*60}")
    
    query = input("\n请输入你的材料学问题: ").strip()
    if not query:
        print("问题不能为空。")
        return

    print(f"\n{'-'*20} 正在分析 {'-'*20}")
    
    # 1. 自动生成预期知识点 (Ground Truth)
    golden_entities = auto_generate_ground_truth(query, verbose=True)
    print(f"[+] 专家系统设定的预期目标: {golden_entities}")
    
    # 2. 提取搜索关键词
    keywords = extract_keywords(query, verbose=False)
    print(f"[*] 搜索关键词: {keywords}")
    
    # 3. 检索上下文
    context = retrieve_rag_context(keywords, verbose=False)
    
    # 4. 自动计算召回率
    hits = []
    for golden in golden_entities:
        if golden.lower() in context.lower():
            hits.append(golden)
    
    recall = len(hits) / len(golden_entities) if golden_entities else 0
    
    print(f"\n{'-'*20} 评估报告 {'-'*20}")
    print(f"[*] 召回得分: {recall:.2%}")
    print(f"    - 命中目标: {hits}")
    print(f"    - 遗漏目标: {[g for g in golden_entities if g not in hits]}")

    # 5. 生成最终回答
    if context:
        answer = generate_rag_answer(query, context, verbose=False)
        print(f"\n[AI 最终回答]:\n{answer}")
    else:
        print("\n[!] 知识库中未找到相关背景，无法生成回答。")

    print(f"\n{'='*60}")

if __name__ == "__main__":
    auto_eval_qa_pipeline()
