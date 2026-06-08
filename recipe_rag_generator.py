#!/usr/bin/env python3
"""
Graph RAG 配方生成器 — Neo4j 知识图谱 + 联网检索 + LLM 合成

三阶段管线:
  Phase 1 — Graph RAG: 从 Neo4j 图谱检索相关催化剂知识
  Phase 2 — Web Search: 联网检索补充文献（可插拔接口）
  Phase 3 — LLM Synthesis: 多轮对话，综合知识生成新配方

配置: 所有连接信息和路径从 .env 读取（通过 scr.knowledge_graph.recipe_config）

用法:
    python recipe_rag_generator.py "设计一个Ru基Ba助剂低温氨合成催化剂"
    python recipe_rag_generator.py --interactive       # 交互对话模式
    python recipe_rag_generator.py --export             # 导出中间文件
"""

import json, sys, os, urllib.request, base64, re, time
from pathlib import Path
from typing import Any

# ── 从 .env 加载全部配置 ──────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
from scr.knowledge_graph.recipe_config import load_recipe_config, load_env_file
from scr.knowledge_graph.llm_client import call_kg_llm_messages

_cfg = load_recipe_config()


# ═══════════════════════════════════════════════════════════
# Neo4j HTTP Client
# ═══════════════════════════════════════════════════════════

def neo4j_cypher(query: str, **params) -> list[dict]:
    """Execute Cypher via Neo4j HTTP API."""
    auth_b64 = base64.b64encode(_cfg.neo4j_auth.encode()).decode()
    payload = json.dumps({"statements": [{"statement": query, "parameters": params}]}).encode()
    req = urllib.request.Request(_cfg.neo4j_http_url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_b64}"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        cols = data["results"][0]["columns"]
        return [dict(zip(cols, row["row"])) for row in data["results"][0]["data"]]
    except Exception as e:
        print(f"  [neo4j] {e}", file=sys.stderr)
        return []


# ═══════════════════════════════════════════════════════════
# Paper Index
# ═══════════════════════════════════════════════════════════

_paper_index: dict | None = None

def load_paper_index() -> dict:
    global _paper_index
    if _paper_index is not None:
        return _paper_index
    try:
        _paper_index = json.loads(_cfg.paper_index_path.read_text(encoding="utf-8"))
    except Exception:
        _paper_index = {}
    return _paper_index

def cite(paper_id: str) -> str:
    pi = load_paper_index()
    if paper_id in pi:
        return f"{pi[paper_id]['title']} [doc_id: {paper_id}]"
    return f"[doc_id: {paper_id}]"


# ═══════════════════════════════════════════════════════════
# Phase 1: Graph RAG — 知识图谱检索
# ═══════════════════════════════════════════════════════════

def rag_retrieve_catalysts(keywords: list[str], limit: int | None = None) -> list[dict]:
    """基于关键词从图谱检索相关催化剂。"""
    limit = limit or _cfg.rag_top_n
    if not keywords:
        return rag_retrieve_top(limit)
    
    results = []
    for kw in keywords:
        rows = neo4j_cypher("""
            MATCH (c:催化剂)-[:有催化性能]->(:催化性能)-[:有氨合成活性]->(a:氨合成活性)
            WHERE a.value IS NOT NULL
              AND (c.display_name CONTAINS $kw
                   OR EXISTS { MATCH (c)-[:有助剂]->(p:助剂) WHERE p.display_name CONTAINS $kw }
                   OR EXISTS { MATCH (c)-[:有活性组分]->(ac:活性组分) WHERE ac.display_name CONTAINS $kw })
            WITH c, a, toFloat(split(a.value, '-')[0]) AS act_num
            ORDER BY act_num DESC
            RETURN DISTINCT c.id AS node_id, c.display_name AS catalyst,
                   c.doc_id AS doc_id, a.value AS activity, a.unit AS unit,
                   act_num AS activity_numeric
            LIMIT $limit
        """, kw=kw, limit=limit)
        results.extend(rows)
    
    seen = set()
    unique = []
    for r in results:
        if r["node_id"] not in seen:
            seen.add(r["node_id"])
            unique.append(r)
    
    if len(unique) < 5:
        top = rag_retrieve_top(limit)
        for t in top:
            if t["node_id"] not in seen:
                seen.add(t["node_id"])
                unique.append(t)
    
    return unique[:limit]


def rag_retrieve_top(limit: int | None = None) -> list[dict]:
    """检索活性最高的催化剂。"""
    limit = limit or _cfg.rag_top_n
    return neo4j_cypher("""
        MATCH (c:催化剂)-[:有催化性能]->(:催化性能)-[:有氨合成活性]->(a:氨合成活性)
        WHERE a.value IS NOT NULL
        WITH c, a, toFloat(split(a.value, '-')[0]) AS act_num
        ORDER BY act_num DESC
        RETURN DISTINCT c.id AS node_id, c.display_name AS catalyst,
               c.doc_id AS doc_id, a.value AS activity, a.unit AS unit,
               act_num AS activity_numeric
        LIMIT $limit
    """, limit=limit)


def rag_retrieve_detail(node_id: str) -> dict:
    """检索单个催化剂节点的全部相关知识。"""
    detail = {}

    rows = neo4j_cypher("""
        MATCH (c:催化剂 {id: $nid})
        RETURN c.display_name AS name, c.doc_id AS doc_id
    """, nid=node_id)
    if not rows:
        return {}
    detail.update(rows[0])
    detail["citation"] = cite(detail.get("doc_id", ""))

    detail["promoters"] = neo4j_cypher("""
        MATCH (c:催化剂 {id: $nid})-[:有助剂]->(p:助剂)
        OPTIONAL MATCH (p)-[:有助剂含量]->(pc:助剂含量)
        OPTIONAL MATCH (p)-[:有添加方式]->(am:添加方式)
        OPTIONAL MATCH (p)-[:有助剂种类]->(pk:助剂种类)
        RETURN p.display_name AS promoter, pc.display_name AS content,
               am.display_name AS method, pk.display_name AS type
    """, nid=node_id)

    detail["conditions"] = neo4j_cypher("""
        MATCH (c:催化剂 {id: $nid})-[:有反应条件]->(r:反应条件)
        OPTIONAL MATCH (r)-[:有温度]->(t:温度)
        OPTIONAL MATCH (r)-[:有压力]->(pr:压力)
        OPTIONAL MATCH (r)-[:有空速]->(g:空速)
        OPTIONAL MATCH (r)-[:有氢氮比]->(h:氢氮比)
        RETURN t.display_name AS temperature, pr.display_name AS pressure,
               g.display_name AS ghsv, h.display_name AS h2_n2_ratio
        LIMIT 5
    """, nid=node_id)

    prep_rows = neo4j_cypher("""
        MATCH (c:催化剂 {id: $nid})-[:有制备工艺]->(prep:制备工艺)
        OPTIONAL MATCH (prep)-[:有混合方式]->(m:混合方式)
        OPTIONAL MATCH (prep)-[:有成型工艺]->(f:成型工艺)
        OPTIONAL MATCH (prep)-[:有焙烧温度]->(ct:焙烧温度)
        OPTIONAL MATCH (prep)-[:有原料选择]->(rm:原料选择)
        OPTIONAL MATCH (prep)-[:有前驱体]->(pr:前驱体)
        OPTIONAL MATCH (prep)-[:有制备方式]->(pm:制备方式)
        OPTIONAL MATCH (prep)-[:有还原活化]->(ra:还原活化)
        RETURN m.display_name AS mixing, f.display_name AS forming,
               ct.display_name AS calcination, pr.display_name AS precursor,
               pm.display_name AS prep_method, ra.display_name AS activation,
               collect(DISTINCT rm.display_name) AS raw_materials
        LIMIT 1
    """, nid=node_id)
    detail["preparation"] = prep_rows[0] if prep_rows else {}

    char_rows = neo4j_cypher("""
        MATCH (c:催化剂 {id: $nid})-[:有表征方法]->(ch:表征方法)-[r]->()
        WHERE type(r) STARTS WITH '有' AND type(r) <> '有表征方法'
        RETURN collect(DISTINCT replace(type(r), '有', '')) AS methods
    """, nid=node_id)
    detail["characterization"] = sorted(char_rows[0]["methods"]) if char_rows and char_rows[0].get("methods") else []

    surf_rows = neo4j_cypher("""
        MATCH (c:催化剂 {id: $nid})
        OPTIONAL MATCH (c)-[:有比表面积]->(sa:比表面积)
        OPTIONAL MATCH (c)-[:有孔结构]->(ps:孔结构)
        OPTIONAL MATCH (c)-[:有粒径]->(gs:粒径)
        OPTIONAL MATCH (c)-[:有晶相结构]->(cs:晶相结构)
        OPTIONAL MATCH (c)-[:有活性组分]->(ac:活性组分)
        RETURN sa.display_name AS surface_area, ps.display_name AS pore_structure,
               gs.display_name AS grain_size, cs.display_name AS crystal_phase,
               collect(DISTINCT ac.display_name) AS active_components
        LIMIT 1
    """, nid=node_id)
    detail["surface"] = surf_rows[0] if surf_rows else {}

    return detail


def rag_promoter_stats() -> list[dict]:
    """全局助剂统计。"""
    return neo4j_cypher("""
        MATCH (c:催化剂)-[:有助剂]->(p:助剂)
        MATCH (c)-[:有催化性能]->(:催化性能)-[:有氨合成活性]->(a:氨合成活性)
        WHERE a.value IS NOT NULL
        WITH p.display_name AS promoter,
             count(DISTINCT c) AS usage_count,
             collect(toFloat(split(a.value, '-')[0])) AS activities
        WHERE size(activities) > 0
        RETURN promoter, usage_count,
               round(reduce(s=0.0, x IN activities | s + x) / size(activities) * 100) / 100 AS avg_activity
        ORDER BY usage_count DESC
        LIMIT 20
    """)


# ═══════════════════════════════════════════════════════════
# Phase 2: Web Search — 联网文献检索（可插拔）
# ═══════════════════════════════════════════════════════════

def web_search_literature(query: str, max_results: int = 5) -> list[dict]:
    """
    联网检索补充文献。根据 WEB_SEARCH_BACKEND 选择后端。

    支持的后端:
      - "none": 不检索（默认）
      - "semanticscholar": Semantic Scholar 免费 API
      - "custom": 使用 WEB_SEARCH_API_URL

    Returns: [{"title": ..., "snippet": ..., "url": ..., "source": ...}, ...]
    """
    backend = _cfg.web_search_backend

    if backend == "none":
        return []

    if backend == "semanticscholar":
        return _search_semantic_scholar(query, max_results)

    if backend == "custom" and _cfg.web_search_api_url:
        return _search_custom(query, max_results)

    return []


def _search_semantic_scholar(query: str, max_results: int) -> list[dict]:
    """Semantic Scholar API（免费，无需 Key）。"""
    import urllib.parse
    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={urllib.parse.quote(query)}"
        f"&limit={max_results}"
        f"&fields=title,abstract,url,year"
    )
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for paper in data.get("data", []):
            results.append({
                "title": paper.get("title", "未知"),
                "snippet": (paper.get("abstract") or "")[:300],
                "url": paper.get("url", ""),
                "year": paper.get("year", ""),
                "source": "Semantic Scholar",
            })
        return results
    except Exception as e:
        print(f"  [web_search] Semantic Scholar: {e}", file=sys.stderr)
        return []


def _search_custom(query: str, max_results: int) -> list[dict]:
    """自定义搜索 API。"""
    import urllib.parse
    url = _cfg.web_search_api_url
    headers = {"Content-Type": "application/json"}
    if _cfg.web_search_api_key:
        headers["Authorization"] = f"Bearer {_cfg.web_search_api_key}"
    try:
        payload = json.dumps({"query": query, "limit": max_results}).encode()
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if isinstance(data, list):
            return data[:max_results]
        if isinstance(data, dict):
            return data.get("results", data.get("data", []))[:max_results]
        return []
    except Exception as e:
        print(f"  [web_search] custom: {e}", file=sys.stderr)
        return []


# ═══════════════════════════════════════════════════════════
# Phase 3: LLM Synthesis — 多轮对话生成配方
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一位合成氨催化剂配方设计专家，拥有丰富的催化剂开发经验。

## 你的能力
你可以基于知识图谱中检索到的真实实验数据和文献，为合成氨催化剂设计新的配方。

## 工作方式
1. 仔细分析用户需求和检索到的知识（催化剂组成、助剂、制备工艺、反应条件、表征数据）
2. 从现有数据中提取可复用的设计规律（哪些助剂组合有效、哪种制备方法产生活性最高的催化剂等）
3. 基于这些规律，设计一个改进的催化剂配方
4. 为每个设计选择提供数据支撑和文献引用

## 输出格式
请按以下结构输出配方：

### 配方概述
简要说明设计思路和目标性能。

### 催化剂组成
- 活性组分：...（选择理由 + 数据支撑 + 文献引用）
- 载体：...（选择理由 + 数据支撑 + 文献引用）
- 助剂体系：...（选择理由 + 数据支撑 + 文献引用）

### 制备工艺
- 前驱体：...
- 制备方法：...
- 关键工艺参数（温度、时间、气氛等）：...

### 预期反应条件
- 温度 / 压力 / 空速 / 氢氮比：...

### 预期表征
- 建议表征方法：...

### 设计依据总结
- 列出本配方参考的关键文献和数据来源

## 重要原则
- 只基于检索到的真实数据做推断，不要编造数值
- 明确标注每个设计选择对应的文献来源
- 如果某方面数据不足，诚实说明
- 配方应具有可操作性（实验室可实现）"""


def build_rag_context(keywords: list[str], top_n: int | None = None) -> str:
    """从图谱检索知识并构建结构化上下文文本。"""
    top_n = top_n or _cfg.rag_top_n
    catalysts = rag_retrieve_catalysts(keywords, limit=top_n)
    prom_stats = rag_promoter_stats()

    lines = []
    lines.append("=" * 60)
    lines.append("【知识图谱检索结果】")
    lines.append(f"Neo4j: {_cfg.neo4j_http_url}")
    lines.append(f"检索到 {len(catalysts)} 个相关催化剂")
    lines.append("=" * 60)

    for i, cat in enumerate(catalysts, 1):
        detail = rag_retrieve_detail(cat["node_id"])
        if not detail:
            continue

        lines.append(f"\n── 催化剂 [{i}]: {detail.get('name', '?')} ──")
        lines.append(f"  活性: {cat.get('activity', '?')} {cat.get('unit', '')}")
        lines.append(f"  文献: {detail.get('citation', '?')}")

        surf = detail.get("surface", {})
        if surf.get("surface_area"):
            lines.append(f"  比表面积: {surf['surface_area']}")
        comps = [c for c in (surf.get("active_components") or []) if c]
        if comps:
            lines.append(f"  活性组分: {', '.join(comps[:8])}")
        if surf.get("crystal_phase"):
            lines.append(f"  晶相: {surf['crystal_phase']}")

        promoters = detail.get("promoters", [])
        if promoters:
            prom_strs = []
            for p in promoters[:5]:
                s = p.get("promoter", "?")
                if p.get("content"):
                    s += f" ({p['content']})"
                if p.get("method"):
                    s += f" [{p['method']}]"
                prom_strs.append(s)
            lines.append(f"  助剂: {'; '.join(prom_strs)}")

        conds = detail.get("conditions", [])
        if conds:
            parts = []
            for cd in conds:
                for k in ["temperature", "pressure", "ghsv", "h2_n2_ratio"]:
                    if cd.get(k):
                        parts.append(cd[k])
            if parts:
                lines.append(f"  反应条件: {', '.join(parts[:4])}")

        prep = detail.get("preparation", {})
        prep_items = []
        for label, key in [("前驱体", "precursor"), ("方法", "prep_method"),
                            ("混合", "mixing"), ("焙烧", "calcination"),
                            ("成型", "forming"), ("活化", "activation")]:
            if prep.get(key):
                prep_items.append(f"{label}={prep[key]}")
        if prep_items:
            lines.append(f"  制备: {' | '.join(prep_items)}")

        chars = detail.get("characterization", [])
        if chars:
            lines.append(f"  表征: {', '.join(chars)}")

    lines.append(f"\n── 助剂效能统计 ──")
    for ps in prom_stats[:12]:
        lines.append(f"  {ps['promoter'] or '?':24s} 使用{ps['usage_count']:3d}次  平均活性{ps['avg_activity']:8.2f}")

    return "\n".join(lines)


def build_web_context(query: str) -> str:
    """从联网检索构建补充上下文。"""
    results = web_search_literature(query)
    if not results:
        return ""

    lines = ["\n" + "=" * 60]
    lines.append("【联网检索补充文献】")
    lines.append("=" * 60)
    for i, r in enumerate(results[:5], 1):
        lines.append(f"\n  [{i}] {r.get('title', '未知标题')}")
        lines.append(f"      来源: {r.get('source', r.get('url', '未知'))}")
        if r.get("snippet"):
            lines.append(f"      摘要: {r['snippet'][:200]}")
    return "\n".join(lines)


def generate_recipe_llm(user_query: str, keywords: list[str] | None = None,
                        top_n: int | None = None, verbose: bool = True) -> dict:
    """完整的 Graph RAG + LLM 配方生成管线。"""
    top_n = top_n or _cfg.rag_top_n

    if keywords is None:
        keywords = extract_keywords(user_query)

    if verbose:
        print(f"🔍 关键词: {keywords}")
        print(f"📡 Phase 1: Graph RAG — 检索知识图谱...")

    rag_text = build_rag_context(keywords, top_n=top_n)

    if verbose:
        print(f"🌐 Phase 2: Web Search — 联网检索补充文献 (backend={_cfg.web_search_backend})...")

    web_text = build_web_context(user_query)

    if verbose:
        print(f"🧠 Phase 3: LLM Synthesis ({_cfg.llm_model}) — 综合分析生成配方...")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""请根据以下检索到的知识和用户需求，设计一个新的合成氨催化剂配方。

## 用户需求
{user_query}

## 检索到的知识

{rag_text}
{web_text}

## 任务
请基于以上知识，按照系统提示中的格式，输出一个完整的催化剂配方设计。
确保每个设计选择都有数据支撑和文献引用。"""}
    ]

    try:
        response = call_kg_llm_messages(messages, verbose=verbose, max_tokens=4096)
    except Exception as e:
        response = f"[LLM调用失败: {e}]\n\n以下是检索到的原始知识:\n\n{rag_text}"

    return {
        "recipe": response,
        "rag_context": rag_text,
        "web_context": web_text,
        "keywords": keywords,
    }


# ═══════════════════════════════════════════════════════════
# Keyword extraction
# ═══════════════════════════════════════════════════════════

CATALYST_KEYWORDS = [
    "Ru", "Fe", "Co", "Ni", "Rh", "Os", "Ir", "Pt", "Mo", "W", "Mn",
    "Ba", "K", "Cs", "Ca", "Li", "Sr", "La", "Ce", "Al", "Si", "Mg",
    "CeO2", "CeO₂", "Al2O3", "Al₂O₃", "SiO2", "SiO₂", "MgO", "ZrO2",
    "TiO2", "TiO₂", "ZnO", "Nb2O5", "Nb₂O₅", "activated carbon", "CNT",
    "Fe2O3", "Fe₃O₄", "Fe₃O4", "ZSM-5", "MOF", "MCM-41", "SBA-15",
    "wustite", "magnetite", "hematite", "钙钛矿", "perovskite",
    "低温", "low temperature", "高压", "high pressure",
    "氨合成", "ammonia synthesis", "NRR", "氮还原",
]

def extract_keywords(query: str) -> list[str]:
    """从用户查询中提取催化剂相关关键词。"""
    found = []
    q_lower = query.lower()
    for kw in CATALYST_KEYWORDS:
        if kw.lower() in q_lower:
            found.append(kw)
    if not found:
        found = ["ammonia", "catalyst"]
    return found


# ═══════════════════════════════════════════════════════════
# Interactive mode
# ═══════════════════════════════════════════════════════════

def interactive_mode():
    """交互式配方设计对话。"""
    print("═" * 60)
    print("  Graph RAG 配方生成器 — 交互模式")
    print(f"  图谱: {_cfg.neo4j_http_url}")
    print(f"  LLM:  {_cfg.llm_model}")
    print(f"  搜索: {_cfg.web_search_backend}")
    print("  输入 'quit' 退出, 'reset' 重置对话, 'config' 查看配置")
    print("═" * 60)

    conversation = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("\n📡 正在加载知识图谱摘要...")
    summary_ctx = build_rag_context([], top_n=8)
    print(f"   已加载图谱知识（{summary_ctx.count('催化剂 [')} 个催化剂）\n")

    while True:
        try:
            user_input = input("🧪 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("👋 再见!")
            break

        if user_input.lower() == "reset":
            conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
            print("🔄 对话已重置\n")
            continue

        if user_input.lower() == "config":
            print(json.dumps(_cfg.as_dict(), ensure_ascii=False, indent=2) + "\n")
            continue

        if not user_input:
            continue

        keywords = extract_keywords(user_input)
        print(f"🔍 关键词: {keywords}")

        rag_text = build_rag_context(keywords, top_n=8)

        print("🧠 正在分析...")
        user_msg = f"""## 用户需求
{user_input}

## 知识图谱检索结果
{rag_text}

请基于以上知识回答用户需求。如果是配方设计请求，请按系统提示格式输出完整配方。"""

        conversation.append({"role": "user", "content": user_msg})

        try:
            response = call_kg_llm_messages(conversation, max_tokens=4096, verbose=False)
        except Exception as e:
            response = f"❌ LLM 调用失败: {e}"

        conversation.append({"role": "assistant", "content": response})
        print(f"\n🤖 配方助手:\n{response}\n")


# ═══════════════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════════════

def export_result(result: dict, prefix: str = "rag_recipe", output_dir: Path | None = None):
    """导出结果文件。"""
    desk = output_dir or _cfg.output_dir
    files = {}
    for key in ["recipe", "rag_context", "web_context"]:
        if key not in result:
            continue
        if key == "recipe":
            path = desk / f"{prefix}_{key}.txt"
            path.write_text(result[key], encoding="utf-8")
        else:
            path = desk / f"{prefix}_{key}.json"
            path.write_text(json.dumps({"content": result[key]}, ensure_ascii=False, indent=2), encoding="utf-8")
        files[key] = str(path)
    return files


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Graph RAG 配方生成器 — KG + Web + LLM 三阶段管线")
    parser.add_argument("query", nargs="?", help="配方设计需求（自然语言）")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互对话模式")
    parser.add_argument("--keywords", "-k", nargs="+", help="手动指定检索关键词")
    parser.add_argument("--top", type=int, default=None, help=f"图谱检索催化剂数 (default: {_cfg.rag_top_n})")
    parser.add_argument("--export", action="store_true", help="导出结果文件")
    parser.add_argument("--outdir", type=str, default=None, help="导出目录（默认: ~/Desktop）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--show-config", action="store_true", help="显示当前配置")
    args = parser.parse_args()

    if args.show_config:
        print(json.dumps(_cfg.as_dict(), ensure_ascii=False, indent=2))
        return

    if args.interactive:
        interactive_mode()
        return

    if not args.query:
        parser.print_help()
        return

    result = generate_recipe_llm(
        user_query=args.query,
        keywords=args.keywords,
        top_n=args.top,
        verbose=args.verbose,
    )

    print("\n" + "=" * 60)
    print(result["recipe"])

    if args.export:
        output_dir = Path(args.outdir) if args.outdir else None
        files = export_result(result, output_dir=output_dir)
        print(f"\n📁 结果已导出到 {output_dir or _cfg.output_dir}:")
        for k, v in files.items():
            print(f"  {k}: {Path(v).name}")


if __name__ == "__main__":
    main()
