#!/usr/bin/env python3
"""
批量语义审核管线：对所有 OCR 产物逐篇 → LLM 抽取 → 转 Excel

用法:
    python batch_semantic_review.py                  # 处理全部 OCR 目录
    python batch_semantic_review.py --limit 5        # 只处理 5 篇（测试）
    python batch_semantic_review.py --skip-existing  # 跳过已有 JSON 的论文
    python batch_semantic_review.py --paper "助剂对Ru" # 只处理名字匹配的论文
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from scr.knowledge_graph.llm_client import load_env_file, call_kg_llm
from scr.knowledge_graph.semantic_review_export import export_semantic_review_excel

ENV_FILE = PROJECT_ROOT / ".env"
OCR_ROOT = PROJECT_ROOT / "artifacts" / "ocr"
ANNOTATION_DIR = PROJECT_ROOT / "artifacts" / "annotation"
PROMPT_PATH = ANNOTATION_DIR / "Prompt.md"

load_env_file(ENV_FILE)


def find_ocr_runs(ocr_root: Path) -> list[tuple[Path, str]]:
    """Return list of (run_dir, paper_name) for all OCR run directories."""
    runs = []
    if not ocr_root.exists():
        return runs
    for doc_dir in sorted(ocr_root.iterdir()):
        if not doc_dir.is_dir():
            continue
        run_dirs = sorted(
            [d for d in doc_dir.iterdir() if d.is_dir() and d.name.startswith("run_")],
            reverse=True,  # newest first
        )
        if run_dirs:
            runs.append((run_dirs[0], doc_dir.name))
    return runs



def _repair_truncated_json(raw: str) -> dict:
    """Try to salvage a truncated or malformed JSON from LLM output."""
    import re as _re

    # Clean markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 1: Try to close unclosed braces/brackets
    for attempt in range(5):
        try:
            # Count unclosed structures
            fixed = cleaned
            # Close unclosed strings
            in_string = False
            escape_next = False
            chars = list(fixed)
            for j, ch in enumerate(chars):
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\':
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
            if in_string:
                fixed += '"'
            # Close braces
            open_braces = fixed.count('{') - fixed.count('}')
            open_brackets = fixed.count('[') - fixed.count(']')
            fixed += '}' * max(0, open_braces) + ']' * max(0, open_brackets)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        # Strategy 2: Try removing last incomplete line
        lines = cleaned.rsplit('\n', 1)
        if len(lines) > 1:
            cleaned = lines[0]
        else:
            break

    raise ValueError("Unable to repair truncated JSON after multiple attempts")


def process_single_paper(
    run_dir: Path,
    paper_name: str,
    prompt_template: str,
    annotation_dir: Path,
    skip_existing: bool = True,
    verbose: bool = True,
) -> dict:
    """Process one paper: read document.md → LLM → save JSON → export Excel."""
    
    # Check document.md
    doc_md_path = run_dir / "document.md"
    if not doc_md_path.exists():
        return {"status": "skip", "reason": "no document.md"}

    # Check if already processed
    json_path = annotation_dir / f"{paper_name}.json"
    xlsx_path = annotation_dir / f"{paper_name}_semantic_review.xlsx"
    
    if skip_existing and json_path.exists() and xlsx_path.exists():
        return {"status": "skip", "reason": "already exists"}

    # Read OCR text
    ocr_text = doc_md_path.read_text(encoding="utf-8")
    if len(ocr_text.strip()) < 100:
        return {"status": "skip", "reason": f"document.md too short ({len(ocr_text)} chars)"}

    # Build prompt
    prompt = prompt_template.replace("{{PAPER_TEXT}}", ocr_text)
    
    if verbose:
        print(f"    OCR text: {len(ocr_text)} chars, prompt: {len(prompt)} chars")
        print(f"    Calling LLM...", end=" ", flush=True)

    # Call LLM
    t0 = time.time()
    try:
        raw_output = call_kg_llm(prompt=prompt, max_tokens=16384, verbose=False)
    except Exception as e:
        return {"status": "error", "reason": f"LLM call failed: {e}"}
    elapsed = time.time() - t0

    # Parse JSON from LLM output (with truncation repair)
    try:
        cleaned = raw_output.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        data = json.loads(cleaned.strip())
    except json.JSONDecodeError:
        # Try repair
        try:
            data = _repair_truncated_json(raw_output)
            if verbose:
                print(f"    ⚠ JSON repaired (truncated output)", end=" ")
        except Exception as e2:
            # Save raw output for debugging
            raw_path = annotation_dir / f"{paper_name}_raw_llm_output.txt"
            raw_path.write_text(raw_output, encoding="utf-8")
            return {"status": "error", "reason": f"JSON parse+repair failed: {e2}", "raw_saved": str(raw_path)}

    # Count items
    n_catalysts = len(data.get("catalyst_inventory", data.get("sample_inventory", [])))
    n_assertions = len(data.get("catalyst_assertions", data.get("sample_assertions", [])))
    n_flags = len(data.get("review_flags", []))

    # Save JSON
    annotation_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Export Excel
    try:
        export_semantic_review_excel(json_path=json_path, output_path=xlsx_path)
    except Exception as e:
        return {
            "status": "partial",
            "reason": f"JSON saved but Excel failed: {e}",
            "json_path": str(json_path),
            "catalysts": n_catalysts,
            "assertions": n_assertions,
            "flags": n_flags,
            "llm_time": elapsed,
        }

    return {
        "status": "ok",
        "json_path": str(json_path),
        "xlsx_path": str(xlsx_path),
        "catalysts": n_catalysts,
        "assertions": n_assertions,
        "flags": n_flags,
        "llm_time": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="批量语义审核：OCR → LLM → Excel")
    parser.add_argument("--limit", type=int, default=0, help="限制处理篇数 (0=全部)")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="跳过已有 JSON+Excel 的论文")
    parser.add_argument("--force", action="store_true", help="强制重新处理所有论文")
    parser.add_argument("--paper", type=str, help="只处理名字包含此关键词的论文")
    parser.add_argument("--ocr-root", type=str, default=str(OCR_ROOT))
    parser.add_argument("--annotation-dir", type=str, default=str(ANNOTATION_DIR))
    parser.add_argument("--prompt", type=str, default=str(PROMPT_PATH))

    args = parser.parse_args()

    # ── 环境检查 ──
    print("=" * 60)
    print("  Batch Semantic Review Pipeline")
    print("=" * 60)
    print(f"  LLM:   {os.environ.get('KG_LLM_MODEL', '?')}")
    print(f"  API:   {os.environ.get('KG_LLM_API_URL', '?')}")
    print(f"  OCR:   {args.ocr_root}")
    print(f"  Out:   {args.annotation_dir}")
    print()

    if not Path(args.prompt).exists():
        print(f"❌ Prompt file not found: {args.prompt}")
        sys.exit(1)

    # Load prompt template
    prompt_template = Path(args.prompt).read_text(encoding="utf-8")
    if "{{PAPER_TEXT}}" not in prompt_template:
        print("⚠ Prompt template missing {{PAPER_TEXT}} placeholder!")

    # Find OCR runs
    all_runs = find_ocr_runs(Path(args.ocr_root))
    if args.paper:
        all_runs = [(d, n) for d, n in all_runs if args.paper in n]

    if args.limit > 0:
        all_runs = all_runs[:args.limit]

    print(f"  待处理: {len(all_runs)} 篇\n")

    # ── Process ──
    annotation_dir = Path(args.annotation_dir)
    skip_existing = not args.force
    stats = {"ok": 0, "skip": 0, "error": 0, "partial": 0}
    t_start = time.time()

    for i, (run_dir, paper_name) in enumerate(all_runs, 1):
        print(f"[{i}/{len(all_runs)}] {paper_name[:60]}")

        result = process_single_paper(
            run_dir=run_dir,
            paper_name=paper_name,
            prompt_template=prompt_template,
            annotation_dir=annotation_dir,
            skip_existing=skip_existing,
            verbose=True,
        )

        status = result["status"]
        stats[status] = stats.get(status, 0) + 1

        if status == "ok":
            print(f"    ✅ {result['catalysts']} catalysts, {result['assertions']} assertions, "
                  f"{result['flags']} flags ({result['llm_time']:.0f}s)")
        elif status == "skip":
            print(f"    ⏭ {result['reason']}")
        elif status == "partial":
            print(f"    ⚠ {result['reason']}")
            print(f"       JSON saved, {result.get('catalysts', 0)} catalysts")
        else:
            print(f"    ❌ {result['reason']}")

        # Brief pause to avoid API rate limiting
        if status in ("ok", "partial"):
            time.sleep(1)

    # ── Summary ──
    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  ✅ Batch Complete ({elapsed:.0f}s)")
    print(f"{'='*60}")
    print(f"  OK:      {stats.get('ok', 0)}")
    print(f"  Skipped: {stats.get('skip', 0)}")
    print(f"  Partial: {stats.get('partial', 0)}")
    print(f"  Errors:  {stats.get('error', 0)}")
    print(f"  Output:  {annotation_dir}/")


if __name__ == "__main__":
    main()
