#!/usr/bin/env python3
"""
配方生成器 — Neo4j 知识图谱驱动的催化剂配方推荐，带文献引用。

基于知识检索（Knowledge Retrieval）→ 配方合成（Recipe Generation）两阶段流程：
  Phase 1: 从 Neo4j 图谱检索高性能催化剂及相关数据（助剂、条件、制备、表征）
  Phase 2: 综合检索结果，生成可溯源配方推荐，每条数据标注来源文献

配置: 所有连接信息和路径从 .env 读取（通过 scr.knowledge_graph.recipe_config）

用法:
    python recipe_generator.py                          # 交互模式
    python recipe_generator.py --top 10                 # Top-10 催化剂
    python recipe_generator.py --json                   # JSON 完整输出
    python recipe_generator.py --export                 # 导出中间文件到桌面
    python recipe_generator.py --catalyst "Ru/CeO₂"     # 单催化剂详细配方
"""

import json, sys, os, urllib.request, base64
from pathlib import Path
from collections import defaultdict

# ── 从 .env 加载全部配置 ──────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
from scr.knowledge_graph.recipe_config import load_recipe_config

_cfg = load_recipe_config()


# ═══════════════════════════════════════════════════════════
# Neo4j HTTP client
# ═══════════════════════════════════════════════════════════

def cypher(query: str, **params) -> list[dict]:
    """Execute a Cypher query via Neo4j HTTP API, return list of dicts."""
    auth_b64 = base64.b64encode(_cfg.neo4j_auth.encode()).decode()
    payload = json.dumps({
        "statements": [{"statement": query, "parameters": params}]
    }).encode()
    req = urllib.request.Request(_cfg.neo4j_http_url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_b64}"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        results = data["results"][0]
        return [dict(zip(results["columns"], row["row"])) for row in results["data"]]
    except Exception as e:
        print(f"[cypher error] {e}", file=sys.stderr)
        return []


# ═══════════════════════════════════════════════════════════
# Paper index loader
# ═══════════════════════════════════════════════════════════

_paper_index: dict | None = None

def load_paper_index() -> dict:
    """Load doc_id → paper metadata mapping. Cached after first load."""
    global _paper_index
    if _paper_index is not None:
        return _paper_index
    try:
        with open(_cfg.paper_index_path, encoding="utf-8") as f:
            _paper_index = json.load(f)
    except FileNotFoundError:
        _paper_index = {}
    return _paper_index


def cite_paper(doc_id: str) -> str:
    """Return a human-readable citation for a doc_id."""
    if not doc_id:
        return "未知来源"
    pi = load_paper_index()
    if doc_id in pi:
        return f"📄 {pi[doc_id]['title']} [{doc_id}]"
    return f"📄 {doc_id}"


# ═══════════════════════════════════════════════════════════
# Phase 1: Knowledge Retrieval
#
# 重要: 使用 node_id (c.id) 进行精确限定，避免同名催化剂跨论文数据混杂
# ═══════════════════════════════════════════════════════════

def retrieve_top_catalysts(limit: int = 30) -> list[dict]:
    """检索活性最高的氨合成催化剂（唯一 node_id + doc_id）。"""
    return cypher("""
        MATCH (c:催化剂)-[:有催化性能]->(:催化性能)-[:有氨合成活性]->(a:氨合成活性)
        WHERE a.value IS NOT NULL
        WITH c, a, toFloat(split(a.value, '-')[0]) AS act_num
        ORDER BY act_num DESC
        RETURN c.display_name AS catalyst,
               c.id AS node_id,
               c.doc_id AS doc_id,
               a.value AS activity_raw,
               a.unit AS act_unit,
               act_num AS activity_numeric
        LIMIT $limit
    """, limit=limit)


def retrieve_promoters(node_id: str) -> list[dict]:
    """检索指定催化剂节点的助剂信息。"""
    return cypher("""
        MATCH (c:催化剂 {id: $nid})-[:有助剂]->(p:助剂)
        OPTIONAL MATCH (p)-[:有助剂含量]->(pc:助剂含量)
        OPTIONAL MATCH (p)-[:有添加方式]->(am:添加方式)
        OPTIONAL MATCH (p)-[:有助剂种类]->(pk:助剂种类)
        RETURN p.display_name AS promoter,
               pc.display_name AS content,
               am.display_name AS addition_method,
               pk.display_name AS promoter_type
    """, nid=node_id)


def retrieve_conditions(node_id: str) -> list[dict]:
    """检索反应条件。"""
    return cypher("""
        MATCH (c:催化剂 {id: $nid})-[:有反应条件]->(r:反应条件)
        OPTIONAL MATCH (r)-[:有温度]->(t:温度)
        OPTIONAL MATCH (r)-[:有压力]->(pr:压力)
        OPTIONAL MATCH (r)-[:有空速]->(g:空速)
        OPTIONAL MATCH (r)-[:有氢氮比]->(h:氢氮比)
        RETURN t.display_name AS temperature,
               pr.display_name AS pressure,
               g.display_name AS ghsv,
               h.display_name AS h2_n2_ratio
        LIMIT 5
    """, nid=node_id)


def retrieve_preparation(node_id: str) -> dict:
    """检索制备工艺。"""
    rows = cypher("""
        MATCH (c:催化剂 {id: $nid})-[:有制备工艺]->(prep:制备工艺)
        OPTIONAL MATCH (prep)-[:有混合方式]->(m:混合方式)
        OPTIONAL MATCH (prep)-[:有成型工艺]->(f:成型工艺)
        OPTIONAL MATCH (prep)-[:有焙烧温度]->(ct:焙烧温度)
        OPTIONAL MATCH (prep)-[:有原料选择]->(rm:原料选择)
        OPTIONAL MATCH (prep)-[:有前驱体]->(pr:前驱体)
        OPTIONAL MATCH (prep)-[:有制备方式]->(pm:制备方式)
        OPTIONAL MATCH (prep)-[:有还原活化]->(ra:还原活化)
        RETURN m.display_name AS mixing,
               f.display_name AS forming,
               ct.display_name AS calcination,
               pr.display_name AS precursor,
               pm.display_name AS prep_method,
               ra.display_name AS activation,
               collect(DISTINCT rm.display_name) AS raw_materials
        LIMIT 1
    """, nid=node_id)
    return rows[0] if rows else {}


def retrieve_characterization(node_id: str) -> list[str]:
    """检索表征方法 — 动态发现表征方法关系类型。"""
    try:
        rows = cypher("""
            MATCH (c:催化剂 {id: $nid})-[:有表征方法]->(ch:表征方法)-[r]->()
            WHERE type(r) STARTS WITH '有' AND type(r) <> '有表征方法'
            RETURN collect(DISTINCT replace(type(r), '有', '')) AS methods
        """, nid=node_id)
        if rows and rows[0].get("methods"):
            return sorted(rows[0]["methods"])
    except Exception:
        pass
    return []


def retrieve_surface_properties(node_id: str) -> dict:
    """检索表面性质。"""
    rows = cypher("""
        MATCH (c:催化剂 {id: $nid})
        OPTIONAL MATCH (c)-[:有比表面积]->(sa:比表面积)
        OPTIONAL MATCH (c)-[:有孔结构]->(ps:孔结构)
        OPTIONAL MATCH (c)-[:有粒径]->(gs:粒径)
        OPTIONAL MATCH (c)-[:有活性组分]->(ac:活性组分)
        OPTIONAL MATCH (c)-[:有晶相结构]->(cs:晶相结构)
        RETURN sa.display_name AS surface_area,
               ps.display_name AS pore_structure,
               gs.display_name AS grain_size,
               cs.display_name AS crystal_phase,
               collect(DISTINCT ac.display_name) AS active_components
        LIMIT 1
    """, nid=node_id)
    return rows[0] if rows else {}


def retrieve_promoter_stats() -> list[dict]:
    """检索助剂使用统计：频率 + 平均活性。"""
    return cypher("""
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


def retrieve_by_node_id(node_id: str) -> dict | None:
    """通过 node_id 检索单个催化剂的完整知识。"""
    rows = cypher("""
        MATCH (c:催化剂 {id: $nid})
        RETURN c.display_name AS catalyst,
               c.doc_id AS doc_id,
               c.id AS node_id
        LIMIT 1
    """, nid=node_id)
    if not rows:
        return None
    info = rows[0]
    info["promoters"] = retrieve_promoters(node_id)
    info["conditions"] = retrieve_conditions(node_id)
    info["preparation"] = retrieve_preparation(node_id)
    info["characterization"] = retrieve_characterization(node_id)
    info["surface"] = retrieve_surface_properties(node_id)
    info["citation"] = cite_paper(info.get("doc_id", ""))
    return info


# ═══════════════════════════════════════════════════════════
# Phase 2: Recipe Synthesis
# ═══════════════════════════════════════════════════════════

def synthesize_recipe(top_n: int = 5) -> dict:
    """从图谱知识合成配方推荐。返回结构化 dict。"""
    ranked = retrieve_top_catalysts(limit=max(top_n * 3, 15))
    if not ranked:
        return {"error": "图谱中无氨合成活性数据"}

    prom_stats = retrieve_promoter_stats()

    # 去重: 同一 node_id 只取一次
    seen = set()
    unique = []
    for c in ranked:
        nid = c["node_id"]
        if nid not in seen:
            seen.add(nid)
            unique.append(c)
        if len(unique) >= top_n:
            break

    # 为每个 top catalyst 补充完整信息
    recipes = []
    for c in unique:
        full = retrieve_by_node_id(c["node_id"])
        if full:
            full["activity_raw"] = c.get("activity_raw", "")
            full["activity_numeric"] = c.get("activity_numeric", 0)
            full["act_unit"] = c.get("act_unit", "")
            recipes.append(full)

    return {
        "neo4j_url": _cfg.neo4j_http_url,
        "total_catalysts_with_activity": len(ranked),
        "unique_top_catalysts": len(unique),
        "top_recipes": recipes,
        "promoter_analysis": prom_stats,
    }


# ═══════════════════════════════════════════════════════════
# Output formatters
# ═══════════════════════════════════════════════════════════

def format_recipe_text(result: dict) -> str:
    """将配方 dict 格式化为可读的文本输出。"""
    if "error" in result:
        return f"❌ {result['error']}"

    recipes = result["top_recipes"]
    prom_stats = result["promoter_analysis"]
    lines = []
    w = 72

    lines.append("═" * w)
    lines.append("  氨合成催化剂配方推荐（知识图谱驱动 · 带文献溯源）")
    lines.append(f"  图谱规模: {result['total_catalysts_with_activity']} 个催化剂有活性数据")
    lines.append("═" * w)

    # ── Top catalysts ──
    lines.append(f"\n{'─' * w}")
    lines.append(f"  ★ Top-{len(recipes)} 高性能催化剂配方")
    lines.append(f"{'─' * w}")

    for i, rc in enumerate(recipes, 1):
        name = rc["catalyst"]
        act = rc.get("activity_raw", "?")
        unit = rc.get("act_unit", "")
        lines.append(f"\n  ┌─ [{i}] {name}")
        lines.append(f"  ├─ 活性: {act} {unit}")
        lines.append(f"  ├─ 来源: {rc.get('citation', '未知')}")

        # Surface
        surf = rc.get("surface", {})
        if surf.get("surface_area"):
            lines.append(f"  ├─ 比表面积: {surf['surface_area']}")
        if surf.get("crystal_phase"):
            lines.append(f"  ├─ 晶相: {surf['crystal_phase']}")
        comps = (surf.get("active_components") or [])
        comps = [c for c in comps if c]
        if comps:
            lines.append(f"  ├─ 活性组分: {', '.join(comps[:6])}")

        # Promoters
        promoters = rc.get("promoters", [])
        if promoters:
            prom_strs = []
            for p in promoters[:6]:
                parts = [p.get("promoter", "?")]
                if p.get("content"):
                    parts.append(p["content"])
                if p.get("addition_method"):
                    parts.append(f"({p['addition_method']})")
                prom_strs.append(" ".join(parts))
            lines.append(f"  ├─ 助剂: {', '.join(prom_strs)}")

        # Conditions
        conds = rc.get("conditions", [])
        if conds:
            parts = []
            for cd in conds:
                for k in ["temperature", "pressure", "ghsv", "h2_n2_ratio"]:
                    v = cd.get(k)
                    if v:
                        parts.append(v)
            if parts:
                lines.append(f"  ├─ 反应条件: {', '.join(parts[:4])}")

        # Preparation
        prep = rc.get("preparation", {})
        prep_parts = []
        for label, key in [("前驱体", "precursor"), ("方法", "prep_method"),
                            ("混合", "mixing"), ("焙烧", "calcination"),
                            ("成型", "forming"), ("活化", "activation")]:
            if prep.get(key):
                prep_parts.append(f"{label}={prep[key]}")
        if prep_parts:
            lines.append(f"  ├─ 制备: {' | '.join(prep_parts)}")
        raw = prep.get("raw_materials", [])
        raw = [r for r in (raw or []) if r]
        if raw:
            lines.append(f"  ├─ 原料: {', '.join(raw[:5])}")

        # Characterization
        chars = rc.get("characterization", [])
        lines.append(f"  └─ 表征: {', '.join(chars) if chars else '(未记录)'}")

    # ── Promoter analysis ──
    lines.append(f"\n{'─' * w}")
    lines.append(f"  助剂效能统计（频率 + 平均活性）")
    lines.append(f"{'─' * w}")
    for ps in prom_stats[:15]:
        lines.append(
            f"  {(ps['promoter'] or '?')[:24]:24s} "
            f"使用 {ps['usage_count']:>3d} 次  "
            f"平均活性 {ps['avg_activity']:>8.2f}"
        )

    # ── Summary recommendation ──
    best = recipes[0]
    lines.append(f"\n{'─' * w}")
    lines.append(f"  ★ 推荐配方摘要")
    lines.append(f"{'─' * w}")
    lines.append(f"  催化剂: {best['catalyst']}")
    lines.append(f"  文献: {best.get('citation', '未知')}")
    promoters = best.get("promoters", [])
    if promoters:
        lines.append(f"  助剂体系: {', '.join(p.get('promoter','?') for p in promoters[:4])}")
    prep = best.get("preparation", {})
    method_parts = []
    if prep.get("prep_method"):
        method_parts.append(prep["prep_method"])
    if prep.get("mixing"):
        method_parts.append(prep["mixing"])
    if prep.get("calcination"):
        method_parts.append(f"焙烧{prep['calcination']}")
    if prep.get("activation"):
        method_parts.append(f"活化{prep['activation']}")
    if method_parts:
        lines.append(f"  关键工艺: {' → '.join(method_parts)}")

    lines.append(f"\n{'═' * w}")
    lines.append(f"  注: 所有配方数据均来自图谱中已入库文献，可溯源至原始论文。")
    lines.append(f"  未匹配到论文标题的 doc_id 仅显示运行编号。")
    lines.append(f"{'═' * w}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════════════

def export_intermediate_files(result: dict, output_dir: Path | None = None):
    """导出中间 JSON 文件。"""
    desk = output_dir or _cfg.output_dir
    files = {}

    # 1. 催化剂排名
    ranked = retrieve_top_catalysts(100)
    seen = set()
    unique_ranked = []
    for c in ranked:
        nid = c["node_id"]
        if nid not in seen:
            seen.add(nid)
            c["citation"] = cite_paper(c.get("doc_id", ""))
            unique_ranked.append(c)
    ranked_out = desk / "recipe_1_catalyst_ranking.json"
    with open(ranked_out, "w", encoding="utf-8") as f:
        json.dump(unique_ranked, f, ensure_ascii=False, indent=2)
    files["catalyst_ranking"] = str(ranked_out)

    # 2. 助剂分析
    prom_out = desk / "recipe_2_promoter_analysis.json"
    with open(prom_out, "w", encoding="utf-8") as f:
        json.dump(result.get("promoter_analysis", []), f, ensure_ascii=False, indent=2)
    files["promoter_analysis"] = str(prom_out)

    # 3. 配方推荐
    recipe_out = desk / "recipe_3_full_recipes.json"
    with open(recipe_out, "w", encoding="utf-8") as f:
        json.dump(result["top_recipes"], f, ensure_ascii=False, indent=2)
    files["full_recipes"] = str(recipe_out)

    # 4. 综合报告
    full_out = desk / "recipe_4_complete_report.json"
    with open(full_out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    files["complete_report"] = str(full_out)

    return files


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="配方生成器 — Neo4j KG 驱动 · 带文献溯源")
    parser.add_argument("--top", type=int, default=5, help="Top-N 催化剂 (default: 5)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出完整配方")
    parser.add_argument("--export", action="store_true", help="导出中间 JSON 文件")
    parser.add_argument("--outdir", type=str, default=None, help="导出目录（默认: ~/Desktop）")
    parser.add_argument("--catalyst", type=str, help="查询单个催化剂名称")
    parser.add_argument("--node-id", type=str, help="通过 node_id 精确查询")
    parser.add_argument("--list", action="store_true", help="列出所有催化剂及活性排名")
    parser.add_argument("--show-config", action="store_true", help="显示当前配置")
    args = parser.parse_args()

    if args.show_config:
        print(json.dumps(_cfg.as_dict(), ensure_ascii=False, indent=2))
        return

    output_dir = Path(args.outdir) if args.outdir else None

    # 精确 node_id 查询
    if args.node_id:
        info = retrieve_by_node_id(args.node_id)
        if info:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 未找到 node_id: {args.node_id}")
        return

    # 按名称查询（可能匹配多个）
    if args.catalyst:
        ranked = retrieve_top_catalysts(200)
        matches = [c for c in ranked if args.catalyst in c["catalyst"]]
        if not matches:
            print(f"❌ 未找到匹配催化剂: {args.catalyst}")
            return
        for m in matches:
            info = retrieve_by_node_id(m["node_id"])
            if info:
                info["activity_raw"] = m.get("activity_raw", "")
                info["activity_numeric"] = m.get("activity_numeric", 0)
                print(f"\n{'─'*60}")
                print(json.dumps(info, ensure_ascii=False, indent=2))
        return

    # 列表模式
    if args.list:
        ranked = retrieve_top_catalysts(100)
        seen = set()
        for c in ranked:
            nid = c["node_id"]
            if nid in seen:
                continue
            seen.add(nid)
            cit = cite_paper(c.get("doc_id", ""))
            print(f"{c['catalyst'][:40]:40s} | {c['activity_raw']:>12s} {c.get('act_unit',''):<10s} | {cit}")
        return

    # 配方生成
    result = synthesize_recipe(args.top)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_recipe_text(result))

    # 导出
    if args.export:
        files = export_intermediate_files(result, output_dir)
        print(f"\n📁 中间文件已导出到 {output_dir or _cfg.output_dir}:")
        for label, path in files.items():
            print(f"  {label}: {Path(path).name}")


if __name__ == "__main__":
    main()
