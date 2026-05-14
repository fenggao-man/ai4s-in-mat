import os
import json
from pathlib import Path
from typing import List, Dict, Any

from scr.knowledge_graph.llm_client import call_kg_llm, load_env_file
from scr.knowledge_graph.sqlite_retrieval import search_knowledge_graph, DEFAULT_DB_PATH

# 路径配置
PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"
DB_PATH = PROJECT_ROOT / DEFAULT_DB_PATH

# 加载环境变量
load_env_file(ENV_FILE)

def extract_keywords(query: str, verbose: bool = False) -> List[str]:
    """
    使用 LLM 从用户问题中提取关键词
    """
    prompt = f"""
你是一个材料科学领域的搜索专家。请从以下用户问题中提取用于在知识图谱中检索的核心关键词。
关键词应包括：催化剂名称、元素、温度、压力、性能指标等。

用户问题：{query}

请直接返回关键词列表，用中文逗号分隔，不要有任何其他解释文字。
例如：Ru/CeO2, 400度, 氨合成活性
"""
    if verbose:
        print(f"[*] 正在为问题提取关键词: {query}")
    
    response = call_kg_llm(prompt, verbose=verbose)
    keywords = [k.strip() for k in response.replace("，", ",").split(",") if k.strip()]
    
    if verbose:
        print(f"[+] 提取到的关键词: {keywords}")
    return keywords

def retrieve_rag_context(keywords: List[str], verbose: bool = False) -> str:
    """
    基于关键词从 SQLite 和图谱中检索上下文
    """
    all_context = []
    seen_chunks = set()
    
    for kw in keywords:
        try:
            # 执行检索，获取 1 跳关联节点
            result = search_knowledge_graph(query=kw, db_path=DB_PATH, hops=1)
            
            # 收集节点属性
            for node in result.get("nodes", []):
                all_context.append(f"实体信息: {node['display_name']} - {node['properties_json']}")
            
            # 收集文本块，避免重复
            for chunk in result.get("chunks", []):
                chunk_id = f"{chunk['doc_id']}_{chunk['chunk_id']}"
                if chunk_id not in seen_chunks:
                    all_context.append(f"文献片段: {chunk['text']}")
                    seen_chunks.add(chunk_id)
                    
            # 收集子图信息
            subgraph = result.get("subgraph", {})
            for edge in subgraph.get("edges", []):
                all_context.append(f"关系: {edge['source_id']} --[{edge['relation']}]--> {edge['target_id']}")
                
        except Exception as e:
            if verbose:
                print(f"[!] 检索关键词 '{kw}' 时出错: {e}")
                
    return "\n".join(all_context[:20]) # 限制上下文长度

def generate_rag_answer(query: str, context: str, verbose: bool = False) -> str:
    """
    结合检索到的上下文，生成最终答案
    """
    prompt = f"""
你是一个专业的材料科学 AI 助手。请根据以下提供的背景知识，回答用户的提问。
如果背景知识中没有相关信息，请诚实回答“根据目前的知识库无法回答该问题”。

背景知识：
{context}

用户提问：
{query}

请给出专业、详细的回答：
"""
    if verbose:
        print("[*] 正在生成最终答案...")
    
    return call_kg_llm(prompt, verbose=verbose)

def rag_qa_pipeline(query: str, verbose: bool = True):
    """
    端到端 RAG 流水线
    """
    print(f"\n{'='*60}\n[RAG QA] 问题: {query}\n{'='*60}")
    
    # 1. 关键词提取
    keywords = extract_keywords(query, verbose=verbose)
    
    # 2. 知识检索
    context = retrieve_rag_context(keywords, verbose=verbose)
    
    if not context:
        print("[!] 未能在知识库中找到相关背景信息。")
        return "抱歉，知识库中暂无相关信息。"

    # 3. 生成回答
    answer = generate_rag_answer(query, context, verbose=verbose)
    
    print(f"\n[AI 回答]:\n{answer}")
    print(f"{'='*60}\n")
    return answer

if __name__ == "__main__":
    # 测试一个复杂问题
    test_query = "在400摄氏度时，Ru/CeO2催化剂的氨合成活性表现如何？它的主要优势是什么？"
    rag_qa_pipeline(test_query)
