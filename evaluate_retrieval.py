import json
import os
from pathlib import Path
from scr.knowledge_graph.sqlite_retrieval import search_knowledge_graph, DEFAULT_DB_PATH

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / DEFAULT_DB_PATH

# 增加干扰项与模糊搜索测试集
TEST_CASES = [
    {
        "id": "Q1-Exact",
        "query": "Ru/CeO2催化剂在400度时的氨合成活性",
        "search_keywords": ["Ru/CeO2", "400"],
        "golden_entities": ["Ru/CeO₂", "400", "0.49"],
        "description": "标准精确匹配测试"
    },
    {
        "id": "Q1-Fuzzy",
        "query": "Ru-CeO2催化剂在400℃时的活性",
        "search_keywords": ["Ru-CeO2", "400℃"], # 故意制造符号差异
        "golden_entities": ["Ru/CeO₂", "400", "0.49"],
        "description": "模糊匹配测试 (符号差异)"
    },
    {
        "id": "Q2-Distractor",
        "query": "寻找关于黄金(Gold)催化剂的Ba–Ru/N-MWNT-1数据",
        "search_keywords": ["Ba–Ru/N-MWNT-1", "Gold"], # "Gold" 是干扰项
        "golden_entities": ["Ba–Ru/N-MWNT-1"],
        "description": "干扰项测试 (加入不存在的关键词)"
    }
]

def evaluate():
    print(f"{'='*60}\n知识检索召回率测试报告\n{'='*60}")
    
    total_recall = 0
    
    for case in TEST_CASES:
        print(f"\n[Testing {case['id']}]: {case['query']}")
        
        # 模拟多关键词联合检索
        combined_text = ""
        for kw in case["search_keywords"]:
            try:
                result = search_knowledge_graph(query=kw, db_path=DB_PATH, hops=1)
                for node in result.get("nodes", []):
                    combined_text += str(node.get("properties_json", "")) + " "
                    combined_text += str(node.get("display_name", "")) + " "
                for chunk in result.get("chunks", []):
                    combined_text += chunk.get("text", "") + " "
                # Include subgraph for relation discovery
                for sub_node in result.get("subgraph", {}).get("nodes", []):
                    combined_text += str(sub_node.get("properties_json", "")) + " "
            except Exception as e:
                print(f"  - [ERROR] Keyword '{kw}' search failed: {e}")
                
        # 计算召回率
        hits = []
        for golden in case["golden_entities"]:
            if golden.lower() in combined_text.lower():
                hits.append(golden)
        
        recall = len(hits) / len(case["golden_entities"]) if case["golden_entities"] else 0
        total_recall += recall
        
        print(f"  - 检索关键词: {case['search_keywords']}")
        print(f"  - 预期目标: {case['golden_entities']}")
        print(f"  - 实际命中: {hits}")
        print(f"  - 当前召回率: {recall:.2%}")

    avg_recall = total_recall / len(TEST_CASES)
    print(f"\n{'='*60}")
    print(f"最终平均召回率 (Average Recall): {avg_recall:.2%}")
    print(f"{'='*60}")

if __name__ == "__main__":
    evaluate()
