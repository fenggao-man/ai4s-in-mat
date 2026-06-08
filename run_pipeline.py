#!/usr/bin/env python3
"""
KG2 全流程知识入库管线

用法:
    python run_pipeline.py                           # 处理 Data/ 下所有 PDF
    python run_pipeline.py --download "iron catalyst ammonia"  # 先下载论文再处理
    python run_pipeline.py --target 50               # 目标处理 50 篇
    python run_pipeline.py --file "path/to/paper.pdf" # 处理单篇
    python run_pipeline.py --steps ocr,extract       # 只跑到抽取
    python run_pipeline.py --clear-neo4j             # 先清空 Neo4j 再入库
    python run_pipeline.py --skip-existing           # 跳过已有 OCR 产物的论文

管线阶段:
    download → ocr → extract → align → fuse → store
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

# ── 项目路径 ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from scr.knowledge_graph.llm_client import load_env_file

ENV_FILE = PROJECT_ROOT / ".env"
DATA_ROOT = PROJECT_ROOT / "Data"
OCR_ROOT = PROJECT_ROOT / "artifacts" / "ocr"

load_env_file(ENV_FILE)


# ═══════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════

def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', str(name))[:100]

def count_pdfs(data_dir: Path = DATA_ROOT) -> int:
    return len(list(data_dir.glob("*.pdf")))

def count_ocr_docs(ocr_root: Path = OCR_ROOT) -> int:
    if not ocr_root.exists():
        return 0
    return len([d for d in ocr_root.iterdir() if d.is_dir()])

def step_header(title: str):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ═══════════════════════════════════════════════════════
# Step 0: 环境检查
# ═══════════════════════════════════════════════════════

def preflight() -> bool:
    issues = []
    checks = {
        "PADDLEOCR_VL_API_URL": "OCR API",
        "KG_LLM_API_URL": "KG LLM API",
        "KG_LLM_MODEL": "LLM Model",
        "NEO4J_URI": "Neo4j URI",
    }
    for key, label in checks.items():
        val = os.environ.get(key, "").strip()
        if not val:
            issues.append(f"  ✗ {label} ({key}) 未配置")
        else:
            # 脱敏显示
            display = val[:30] + "..." if len(val) > 30 else val
            print(f"  ✓ {label}: {display}")

    if not DATA_ROOT.exists():
        issues.append(f"  ✗ Data 目录不存在: {DATA_ROOT}")

    if issues:
        print("\n⚠ 配置问题:")
        for i in issues:
            print(i)
        return False
    return True


# ═══════════════════════════════════════════════════════
# Step 1: 论文下载（可选）
# ═══════════════════════════════════════════════════════

def download_papers(
    queries: list[str],
    target: int = 50,
    per_query: int = 30,
) -> int:
    """从 Europe PMC 下载催化剂相关论文。"""
    import requests

    EPMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    # 铁基/催化剂关键词过滤器
    KW_RE = re.compile(
        r'(catalyst|catalysis|catalytic|iron|ferrite|wustite|magnetite|'
        r'ammonia|synthesis|promoter|Fe|oxide|nitride|support)', re.I
    )

    existing = {f.stem for f in DATA_ROOT.glob("*.pdf")}
    start = len(existing)

    step_header(f"Step 1: 论文下载  (目标 ≥{target} 篇)")
    print(f"  已有: {start} 篇\n")

    for qi, query in enumerate(queries, 1):
        count = count_pdfs()
        if count >= target:
            break

        print(f"  [{qi}/{len(queries)}] {query[:65]}...", end=" ", flush=True)
        results = []
        for attempt in range(3):
            try:
                r = requests.get(EPMC_API, params={
                    'query': query, 'format': 'json',
                    'pageSize': per_query, 'resultType': 'core',
                }, timeout=30)
                if r.status_code == 200:
                    results = r.json().get('resultList', {}).get('result', [])
                    break
                time.sleep(5)
            except Exception:
                time.sleep(5)

        new = 0
        for paper in results:
            if count + new >= target:
                break

            title = re.sub(r'</?[^>]+>', '', paper.get('title', '').strip())
            if not KW_RE.search(title):
                continue

            fname = sanitize_filename(title)
            if fname in existing:
                continue

            ft = paper.get('fullTextUrlList', {}).get('fullTextUrl', [])
            pdf_url = next((u['url'] for u in ft if 'pdf' in u.get('url', '').lower()), None)
            if not pdf_url:
                continue

            filepath = DATA_ROOT / (fname + '.pdf')
            try:
                resp = requests.get(pdf_url, stream=True, timeout=45)
                if resp.status_code == 200 and len(resp.content) > 2000:
                    filepath.write_bytes(resp.content)
                    existing.add(fname)
                    new += 1
            except Exception:
                pass

        count = count_pdfs()
        print(f"+{new}, 累计 {count}")
        if count < target:
            time.sleep(5)

    total = count_pdfs()
    print(f"\n  ✅ 下载完成: {total} 篇 (新增 {total - start})\n")
    return total


# ═══════════════════════════════════════════════════════
# Step 2-6: KG2 管线 (OCR → Extract → Align → Fuse → Store)
# ═══════════════════════════════════════════════════════

def run_kg2_pipeline(
    pdf_files: list[Path],
    skip_existing: bool = True,
    clear_neo4j: bool = False,
    verbose: bool = True,
) -> dict:
    """运行 KG2 标准管线。"""
    from scr.ocr.paddle_api import _slugify_filename
    from scr.ocr.paddle_structured import recognize_to_structured_markdown
    from scr.knowledge_graph import (
        align_entity_graph_from_run,
        clear_entity_graph_database,
        extract_graph_from_ocr_run,
        fuse_entity_graph_from_run,
        store_entity_graph_from_run,
    )

    stats = {"total": len(pdf_files), "ocr_skipped": 0, "ocr_ran": 0,
             "extracted": 0, "aligned": 0, "fused": 0, "stored": 0, "errors": 0}

    if clear_neo4j:
        step_header("清空 Neo4j 数据库")
        clear_entity_graph_database(verbose=verbose)

    step_header(f"Step 2-6: KG2 管线  ({stats['total']} 篇论文)")
    t_total = time.time()

    for i, pdf_path in enumerate(pdf_files, 1):
        doc_slug = _slugify_filename(pdf_path)
        doc_dir = OCR_ROOT / doc_slug
        run_dirs = sorted(
            [d for d in doc_dir.iterdir() if d.is_dir() and d.name.startswith("run_")]
        ) if doc_dir.exists() else []

        print(f"\n  [{i}/{stats['total']}] {pdf_path.name[:60]}")

        # ── OCR ──
        t0 = time.time()
        if skip_existing and run_dirs:
            run_dir = run_dirs[-1]
            stats["ocr_skipped"] += 1
            print(f"    OCR: ⏭ 已有 (run={run_dir.name})")
        else:
            try:
                structured_md = recognize_to_structured_markdown(
                    file_path=pdf_path, env_file=ENV_FILE,
                    output_root=OCR_ROOT, verbose=False,
                )
                run_dir = structured_md.parent
                stats["ocr_ran"] += 1
                print(f"    OCR: ✓ {time.time()-t0:.0f}s")
            except Exception as e:
                print(f"    OCR: ✗ {e}")
                stats["errors"] += 1
                continue

        # ── Extract ──
        t0 = time.time()
        try:
            extract_graph_from_ocr_run(run_dir=run_dir, verbose=False)
            stats["extracted"] += 1
            print(f"    Extract: ✓ {time.time()-t0:.0f}s")
        except Exception as e:
            print(f"    Extract: ✗ {e}")
            stats["errors"] += 1
            continue

        # ── Align ──
        t0 = time.time()
        try:
            align_entity_graph_from_run(run_dir=run_dir, verbose=False)
            stats["aligned"] += 1
            print(f"    Align: ✓ {time.time()-t0:.0f}s")
        except Exception as e:
            print(f"    Align: ✗ {e}")
            stats["errors"] += 1
            continue

        # ── Fuse ──
        t0 = time.time()
        try:
            fuse_entity_graph_from_run(run_dir=run_dir, verbose=False)
            stats["fused"] += 1
            print(f"    Fuse: ✓ {time.time()-t0:.0f}s")
        except Exception as e:
            print(f"    Fuse: ✗ {e}")
            stats["errors"] += 1
            continue

        # ── Store ──
        t0 = time.time()
        try:
            store_entity_graph_from_run(run_dir=run_dir, verbose=False)
            stats["stored"] += 1
            print(f"    Store → Neo4j: ✓ {time.time()-t0:.0f}s")
        except Exception as e:
            print(f"    Store: ✗ {e}")
            stats["errors"] += 1
            continue

    total_elapsed = time.time() - t_total
    print(f"\n  ✅ 管线完成 ({total_elapsed:.0f}s, {total_elapsed/stats['total']:.0f}s/篇)")

    return stats


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="KG2 全流程知识入库管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_pipeline.py                              # 处理 Data/ 下所有 PDF
  python run_pipeline.py --download "iron catalyst"   # 下载 + 处理
  python run_pipeline.py --target 50                  # 目标 50 篇
  python run_pipeline.py --file paper.pdf             # 单篇处理
  python run_pipeline.py --steps ocr,extract          # 只到抽取
  python run_pipeline.py --clear-neo4j                # 清空 Neo4j 后入库
  python run_pipeline.py --skip-existing --clear-neo4j # 全量重入库
        """,
    )
    # 论文来源
    parser.add_argument("--download", type=str, nargs="?",
                        const="iron catalyst ammonia synthesis",
                        help="先下载论文 (可选关键词)")
    parser.add_argument("--target", type=int, default=50,
                        help="目标论文数 (默认 50)")
    parser.add_argument("--file", type=str,
                        help="处理单篇 PDF (路径)")
    parser.add_argument("--data-dir", type=str, default=str(DATA_ROOT),
                        help=f"论文目录 (默认 {DATA_ROOT})")

    # 流程控制
    parser.add_argument("--skip-existing", action="store_true",
                        help="跳过已有 OCR 产物的论文")
    parser.add_argument("--clear-neo4j", action="store_true",
                        help="入库前清空 Neo4j 数据库")
    parser.add_argument("--steps", type=str, default="all",
                        help="执行步骤: download,ocr,extract,align,fuse,store (逗号分隔)")

    args = parser.parse_args()
    steps = set(s.strip().lower() for s in args.steps.split(","))
    run_all = "all" in steps

    # ── 环境检查 ──
    print("=" * 55)
    print("  KG2 Pipeline — 知识入库")
    print("=" * 55)
    print(f"  LLM:     {os.environ.get('KG_LLM_MODEL', '?')}")
    print(f"  Neo4j:   {os.environ.get('NEO4J_URI', '?')}")
    print(f"  Steps:   {args.steps}")
    print()

    if not preflight():
        sys.exit(1)

    # ── 论文准备 ──
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    if args.download is not None and (run_all or "download" in steps):
        queries = [
            args.download,
            '("iron catalyst" OR "Fe catalyst") AND (ammonia synthesis) AND OPEN_ACCESS:y',
            '(catalyst) AND (ammonia synthesis OR NH3) AND (iron OR Fe OR promoter) AND OPEN_ACCESS:y',
        ]
        download_papers(queries, target=args.target)

    # ── 获取 PDF 列表 ──
    if args.file:
        pdf_files = [Path(args.file)]
    else:
        pdf_files = sorted(data_dir.glob("*.pdf"))

    if not pdf_files:
        print("❌ 没有论文可处理。")
        sys.exit(1)

    # ── 运行管线 ──
    if run_all or any(s in steps for s in ["ocr", "extract", "align", "fuse", "store"]):
        stats = run_kg2_pipeline(
            pdf_files=pdf_files,
            skip_existing=args.skip_existing,
            clear_neo4j=args.clear_neo4j,
        )

        # ── 总结 ──
        print(f"\n{'='*55}")
        print(f"  ✅ Pipeline 完成")
        print(f"{'='*55}")
        print(f"  论文总数:  {stats['total']}")
        print(f"  OCR 跳过: {stats['ocr_skipped']} | 新跑: {stats['ocr_ran']}")
        print(f"  抽取成功: {stats['extracted']}")
        print(f"  对齐成功: {stats['aligned']}")
        print(f"  融合成功: {stats['fused']}")
        print(f"  入库成功: {stats['stored']}")
        print(f"  失败:     {stats['errors']}")
        print(f"  Neo4j:    {os.environ.get('NEO4J_URI', '?')}")


if __name__ == "__main__":
    main()
