from __future__ import annotations

import json
import re
import time
import inspect
from pathlib import Path
from typing import Any, Callable

from .llm_client import call_kg_llm, call_kg_llm_messages
try:
    import json5 as _json5_lib
except ImportError:
    _json5_lib = None
from .prompts import (
    ENTITY_EXTRACT_PROMPT,
    SYNTHESIS_EXTRACT_PROMPT,
    SYNTHESIS_CHECK_PROMPT,
    TESTING_EXTRACT_PROMPT,
    TESTING_CHECK_PROMPT,
    CHARACTERIZATION_EXTRACT_PROMPT,
    CHARACTERIZATION_CHECK_PROMPT,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_RUNTIME_DIR = PROJECT_ROOT / "Data" / "ontology_runtime"

# ── Stage splits for multi-stage extraction ──────────────────────────────────
STAGE_SPLITS: dict[str, dict[str, Any]] = {
    "synthesis": {
        "label": "合成信息",
        "entity_types": ["催化剂", "化学物质", "助剂", "制备步骤", "机理"],
    },
    "testing": {
        "label": "测试信息",
        "entity_types": ["测试"],
    },
    "characterization": {
        "label": "表征信息",
        "entity_types": ["表征"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def extract_graph_from_ocr_run(
    run_dir: str | Path,
    llm_client: Callable[..., str] | None = None,
    llm_model: str | None = None,
    verbose: bool = False,
    single_stage: bool = False,
) -> Path:
    if single_stage:
        return _extract_single_stage(run_dir, llm_client, llm_model, verbose)
    return _extract_multi_stage(run_dir, llm_client, llm_model, verbose)


def extract_entities_from_ocr_run(
    run_dir: str | Path,
    llm_client: Callable[[str, str | None], str] | None = None,
    llm_model: str | None = None,
    verbose: bool = False,
) -> Path:
    return extract_graph_from_ocr_run(run_dir=run_dir, llm_client=llm_client, llm_model=llm_model, verbose=verbose)


# ═══════════════════════════════════════════════════════════════════════════════
# Ontology loading
# ═══════════════════════════════════════════════════════════════════════════════

def load_runtime_ontology(ontology_dir: str | Path = ONTOLOGY_RUNTIME_DIR) -> dict[str, Any]:
    ontology_path = Path(ontology_dir)
    node_types = _load_node_types(ontology_path / "node_types.yaml")
    relation_types = _load_relation_types(ontology_path / "relation_types.yaml")
    entity_type_names = [nt["name"] for nt in node_types]
    return {
        "node_types": node_types,
        "relation_types": relation_types,
        "entity_type_names": entity_type_names,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Single-stage extraction (legacy, updated)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_single_stage(
    run_dir: str | Path,
    llm_client: Callable[..., str] | None = None,
    llm_model: str | None = None,
    verbose: bool = False,
) -> Path:
    started_at = time.perf_counter()
    run_path = Path(run_dir)
    markdown_path = run_path / "document.md"
    if not markdown_path.exists():
        raise FileNotFoundError(markdown_path)

    ontology_bundle = load_runtime_ontology()
    document_text = markdown_path.read_text(encoding="utf-8")
    prompt = build_extraction_prompt(document_text=document_text, ontology_bundle=ontology_bundle)

    client = llm_client or call_kg_llm
    if verbose:
        print("[entity_extraction] calling KG LLM (single-stage)...", flush=True)
    client_signature = inspect.signature(client)
    if "verbose" in client_signature.parameters:
        raw_output = client(prompt, llm_model, verbose=verbose)
    else:
        raw_output = client(prompt, llm_model)

    grouped_output = parse_grouped_output(raw_output)
    doc_context = {
        "doc_id": run_path.name,
        "filename": markdown_path.name,
        **(grouped_output.get("document") or {}),
    }
    graph = build_graph_draft(
        grouped_output=grouped_output,
        ontology_bundle=ontology_bundle,
        doc_context=doc_context,
    )

    output_dir = run_path / "knowledge_graph"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "entity_graph_raw.txt"
    raw_path.write_text(raw_output, encoding="utf-8")
    graph_path = output_dir / "entity_graph.json"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    if verbose:
        elapsed = time.perf_counter() - started_at
        print(
            f"[entity_extraction] single-stage: nodes={len(graph['nodes'])}, edges={len(graph['edges'])}, "
            f"elapsed={elapsed:.2f}s", flush=True
        )
    return graph_path


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-stage extraction
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_multi_stage(
    run_dir: str | Path,
    llm_client: Callable[..., str] | None = None,
    llm_model: str | None = None,
    verbose: bool = False,
) -> Path:
    started_at = time.perf_counter()
    run_path = Path(run_dir)
    markdown_path = run_path / "document.md"
    if not markdown_path.exists():
        raise FileNotFoundError(markdown_path)

    ontology_bundle = load_runtime_ontology()
    document_text = markdown_path.read_text(encoding="utf-8")
    client = llm_client or call_kg_llm

    if verbose:
        print(f"[entity_extraction] multi-stage pipeline: chars={len(document_text)}", flush=True)

    doc_context: dict[str, Any] = {
        "doc_id": run_path.name,
        "filename": markdown_path.name,
        "source": "OCR",
        "title": "Unknown",
    }

    stage_outputs: dict[str, dict[str, Any]] = {}

    # Stage 1: Synthesis
    if verbose:
        print("[entity_extraction] === Stage 1/3: Synthesis ===", flush=True)
    stage_outputs["synthesis"] = _run_stage(
        stage="synthesis", document_text=document_text,
        ontology_bundle=ontology_bundle, client=client,
        llm_model=llm_model, verbose=verbose, catalyst_names=None,
    )
    catalyst_names = _collect_catalyst_names(stage_outputs["synthesis"])
    if verbose:
        print(f"[entity_extraction] synthesis: {len(catalyst_names)} catalysts: {catalyst_names}", flush=True)

    # Stage 2: Testing
    if verbose:
        print("[entity_extraction] === Stage 2/3: Testing ===", flush=True)
    stage_outputs["testing"] = _run_stage(
        stage="testing", document_text=document_text,
        ontology_bundle=ontology_bundle, client=client,
        llm_model=llm_model, verbose=verbose, catalyst_names=catalyst_names,
    )

    # Stage 3: Characterization
    if verbose:
        print("[entity_extraction] === Stage 3/3: Characterization ===", flush=True)
    stage_outputs["characterization"] = _run_stage(
        stage="characterization", document_text=document_text,
        ontology_bundle=ontology_bundle, client=client,
        llm_model=llm_model, verbose=verbose, catalyst_names=catalyst_names,
    )

    # Merge stages
    merged_output = _merge_stage_outputs(stage_outputs, doc_context)
    graph = build_graph_draft(
        grouped_output=merged_output,
        ontology_bundle=ontology_bundle,
        doc_context=doc_context,
    )

    # Save outputs
    output_dir = run_path / "knowledge_graph"
    output_dir.mkdir(parents=True, exist_ok=True)

    for stage_name, output in stage_outputs.items():
        raw_path = output_dir / f"entity_graph_{stage_name}_raw.json"
        raw_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    graph_path = output_dir / "entity_graph.json"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    if verbose:
        elapsed = time.perf_counter() - started_at
        print(
            f"[entity_extraction] multi-stage: nodes={len(graph['nodes'])}, edges={len(graph['edges'])}, "
            f"elapsed={elapsed:.2f}s", flush=True
        )
    return graph_path


def _run_stage(
    stage: str,
    document_text: str,
    ontology_bundle: dict[str, Any],
    client: Callable[..., str],
    llm_model: str | None,
    verbose: bool,
    catalyst_names: list[str] | None,
) -> dict[str, Any]:
    stage_prompt = _build_stage_prompt(
        stage=stage, document_text=document_text,
        ontology_bundle=ontology_bundle, catalyst_names=catalyst_names,
    )
    if verbose:
        print(f"  [{stage}] prompt chars={len(stage_prompt)}", flush=True)

    client_signature = inspect.signature(client)
    if "verbose" in client_signature.parameters:
        raw = client(stage_prompt, llm_model, verbose=verbose)
    else:
        raw = client(stage_prompt, llm_model)
    if verbose:
        print(f"  [{stage}] response chars={len(raw)}", flush=True)

    stage_output = parse_grouped_output(raw)

    # Validation pass
    check_prompt_map = {
        "synthesis": SYNTHESIS_CHECK_PROMPT,
        "testing": TESTING_CHECK_PROMPT,
        "characterization": CHARACTERIZATION_CHECK_PROMPT,
    }

    # ★ CATDA-style multi-turn validation:
    # Send [extraction prompt, AI response, check prompt] as a conversation
    # so the model sees its own output when self-correcting.
    check_messages = [
        {"role": "user", "content": stage_prompt},
        {"role": "assistant", "content": raw},
        {"role": "user", "content": check_prompt_map[stage]},
    ]

    if verbose:
        print(f"  [{stage}] multi-turn validation check (3 messages)...", flush=True)
    try:
        check_raw = call_kg_llm_messages(
            messages=check_messages,
            model=llm_model,
            verbose=verbose,
        )
    except Exception:
        # Fallback: if multi-turn fails (e.g. provider doesn't support it),
        # fall back to single-prompt concatenation
        if verbose:
            print(f"  [{stage}] multi-turn failed, falling back to single-prompt", flush=True)
        check_full_prompt = (
            f"【原始抽取任务】\n{stage_prompt}\n\n"
            f"【你的抽取结果】\n{raw}\n\n"
            f"【审查任务】\n{check_prompt_map[stage]}"
        )
        if "verbose" in client_signature.parameters:
            check_raw = client(check_full_prompt, llm_model, verbose=verbose)
        else:
            check_raw = client(check_full_prompt, llm_model)

    try:
        corrections = parse_grouped_output(check_raw)
    except (ValueError, json.JSONDecodeError):
        if verbose:
            print(f"  [{stage}] could not parse validation output, skipping", flush=True)
        corrections = {}

    if corrections and any(
        corrections.get(k) for k in ("nodes_to_add", "nodes_to_update", "node_names_to_delete")
    ):
        add_count = sum(len(v) for v in corrections.get("nodes_to_add", {}).values())
        upd_count = sum(len(v) for v in corrections.get("nodes_to_update", {}).values())
        del_count = sum(len(v) for v in corrections.get("node_names_to_delete", {}).values())
        if verbose:
            print(f"  [{stage}] corrections: +{add_count} ~{upd_count} -{del_count}", flush=True)
        stage_output = _apply_corrections(stage_output, corrections)

    return stage_output


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt building
# ═══════════════════════════════════════════════════════════════════════════════

def build_extraction_prompt(document_text: str, ontology_bundle: dict[str, Any]) -> str:
    ontology_text = _build_ontology_text(ontology_bundle)
    output_example = _build_output_example(ontology_bundle)
    return ENTITY_EXTRACT_PROMPT.format(
        ontology_text=ontology_text,
        output_example=output_example,
        text=document_text,
    )


def _build_ontology_text(ontology_bundle: dict[str, Any]) -> str:
    node_types = ontology_bundle["node_types"]
    relation_types = ontology_bundle["relation_types"]
    parts = []
    parts.append("【实体类型及属性】")
    for nt in node_types:
        props = [p["name"] for p in nt.get("properties", [])]
        parts.append(f"  {nt['name']}: {', '.join(props)}")
    parts.append("\n【关系类型】")
    for rt in relation_types:
        src = ', '.join(rt.get("source_types", []))
        tgt = ', '.join(rt.get("target_types", []))
        desc = rt.get("description", "")
        parts.append(f"  {rt['name']}: {src} → {tgt}" + (f"  ({desc})" if desc else ""))
    return "\n".join(parts)


def _build_stage_prompt(
    stage: str,
    document_text: str,
    ontology_bundle: dict[str, Any],
    catalyst_names: list[str] | None,
) -> str:
    split = STAGE_SPLITS[stage]
    stage_entity_names = split["entity_types"]

    # Filter ontology for this stage
    stage_node_types = [nt for nt in ontology_bundle["node_types"] if nt["name"] in stage_entity_names]
    stage_relation_types = [
        rt for rt in ontology_bundle["relation_types"]
        if any(s in stage_entity_names for s in rt.get("source_types", []))
        or any(t in stage_entity_names for t in rt.get("target_types", []))
    ]
    stage_ontology = {
        "node_types": stage_node_types,
        "relation_types": stage_relation_types,
        "entity_type_names": stage_entity_names,
    }
    ontology_text = _build_ontology_text(stage_ontology)

    output_example = _build_stage_output_example(stage, stage_node_types)
    catalyst_names_str = json.dumps(catalyst_names, ensure_ascii=False) if catalyst_names else "[]"

    template_map = {
        "synthesis": SYNTHESIS_EXTRACT_PROMPT,
        "testing": TESTING_EXTRACT_PROMPT,
        "characterization": CHARACTERIZATION_EXTRACT_PROMPT,
    }
    template = template_map[stage]

    return template.format(
        ontology_text=ontology_text,
        output_example_synthesis=output_example,
        output_example_testing=output_example,
        output_example_characterization=output_example,
        catalyst_names_from_synthesis=catalyst_names_str,
        text=document_text,
    )


def _build_output_example(ontology_bundle: dict[str, Any]) -> str:
    node_types = ontology_bundle["node_types"]
    example: dict[str, Any] = {"document": {"title": "示例文献标题"}}

    for nt in node_types:
        if nt["name"] == "文档":
            continue
        props = nt.get("properties", [])
        sample: dict[str, Any] = {}
        for p in props:
            pname = p["name"]
            if pname in ("doc_id", "filename", "source"):
                continue
            if pname == "name":
                sample["name"] = f"示例{nt['name']}"
            elif pname == "method":
                sample["method"] = "XRD"
            elif pname == "aspect":
                sample["aspect"] = "解离吸附"
            elif pname == "role":
                sample["role"] = "active_component"
            elif pname == "step_order":
                sample["step_order"] = 1
            elif pname == "step_name":
                sample["step_name"] = "共沉淀"
            elif pname == "catalyst_name":
                sample["catalyst_name"] = "示例催化剂"
            elif "value" in pname:
                sample[pname] = "示例值"
            elif "unit" in pname:
                sample[pname] = "单位"
            elif pname == "source_text":
                sample["source_text"] = "原文引用..."
            elif pname in ("description", "note", "result_summary"):
                sample[pname] = f"示例{nt['name']}描述"
            else:
                sample[pname] = f"示例{pname}"
        if nt["name"] in ("催化剂",):
            example[nt["name"]] = [sample]
        elif nt["name"] in ("助剂", "测试", "制备步骤", "表征", "机理", "化学物质"):
            example[nt["name"]] = [sample]

    return json.dumps(example, ensure_ascii=False, indent=2)


def _build_stage_output_example(stage: str, stage_node_types: list[dict[str, Any]]) -> str:
    stage_bundle = {"node_types": stage_node_types, "relation_types": []}
    return _build_output_example(stage_bundle)


# ═══════════════════════════════════════════════════════════════════════════════
# Output parsing & stage merging
# ═══════════════════════════════════════════════════════════════════════════════
# ── Control symbol removal ────────────────────────────────────────────────
CONTROL_SYMBOLS_TO_REMOVE = [
    "<!-- PageBreak -->",
    "☐", "☒",
    "\u200b",  # zero-width space
    "\ufeff",   # BOM
]

def remove_control_symbols(text: str) -> str:
    """Strip OCR artifacts and invisible chars that confuse LLMs."""
    for sym in CONTROL_SYMBOLS_TO_REMOVE:
        text = text.replace(sym, "")
    return text


# ── Robust JSON parsing (CATDA-style) ────────────────────────────────────

def _iter_balanced_json_candidates(text: str):
    """Yield balanced object/array substrings while respecting JSON strings."""
    start = None
    stack = []
    in_string = False
    escape = False
    for idx, ch in enumerate(text):
        if start is None:
            if ch in "{[":
                start = idx
                stack = [ch]
                in_string = False
                escape = False
            continue
        if in_string:
            if escape: escape = False
            elif ch == "\\": escape = True
            elif ch == '"': in_string = False
            continue
        if ch == '"': in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack: start = None; continue
            opener = stack[-1]
            if (opener, ch) not in (("{", "}"), ("[", "]")): start = None; stack = []; continue
            stack.pop()
            if not stack and start is not None:
                yield text[start:idx + 1]
                start = None


def _loads_llm_json(output: str, label: str = "LLM output") -> Any:
    """Parse JSON/JSON5 from fenced, direct, or balanced LLM output.

    Tries in order:
      1. Fenced blocks (```json ... ```)
      2. Raw output as-is
      3. Balanced bracket extraction (handles extra text around JSON)
    Falls back to json5 if available for relaxed parsing.
    """
    import json as _json
    errors = []
    fenced_blocks = re.findall(r"```(?:json|JSON)?\s*(.*?)\s*```", output, re.DOTALL)
    candidates = fenced_blocks + [output.strip()] + list(_iter_balanced_json_candidates(output))
    seen = set()

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        # Try json5 first (more forgiving), then json
        if _json5_lib:
            try:
                return _json5_lib.loads(candidate)
            except Exception as exc:
                errors.append(f"json5: {type(exc).__name__}")
        try:
            return _json.loads(candidate)
        except Exception as exc:
            errors.append(f"json: {type(exc).__name__}: {exc}")

    raise ValueError(
        f"Failed to parse {label} as JSON. Tried {len(seen)} candidate(s). "
        f"Last errors: {'; '.join(errors[-3:])}"
    )



def parse_grouped_output(raw_output: str) -> dict[str, Any]:
    """Parse LLM output using CATDA-style robust JSON parser."""
    parsed = _loads_llm_json(raw_output, "extraction output")
    if not isinstance(parsed, dict):
        raise ValueError("Extraction output must be a JSON object.")
    return parsed


def _collect_catalyst_names(stage_output: dict[str, Any]) -> list[str]:
    catalysts = _ensure_list(stage_output.get("催化剂"))
    names: list[str] = []
    for cat in catalysts:
        name = cat.get("name")
        if name and isinstance(name, str):
            names.append(name)
    return names


def _merge_stage_outputs(
    stage_outputs: dict[str, dict[str, Any]],
    doc_context: dict[str, Any],
) -> dict[str, Any]:
    """Merge synthesis, testing, characterization outputs.

    Synthesis data provides the base (催化剂, 化学物质, 助剂, 制备步骤, 机理).
    Testing and characterization data are appended as additional arrays.
    """
    syn = stage_outputs.get("synthesis", {})
    merged: dict[str, Any] = {"document": doc_context}
    if "document" in syn:
        merged["document"].update(syn["document"])

    # Copy synthesis entities as-is
    for entity_type in ["催化剂", "化学物质", "助剂", "制备步骤", "机理"]:
        merged[entity_type] = _ensure_list(syn.get(entity_type))

    # Append testing data
    test_output = stage_outputs.get("testing", {})
    merged["测试"] = _ensure_list(test_output.get("测试"))

    # Append characterization data
    char_output = stage_outputs.get("characterization", {})
    merged["表征"] = _ensure_list(char_output.get("表征"))

    return merged


def _apply_corrections(
    stage_output: dict[str, Any],
    corrections: dict[str, Any],
) -> dict[str, Any]:
    """Apply add/update/delete corrections grouped by entity type."""

    # Process deletions by entity type
    names_to_delete_by_type: dict[str, set] = {}
    for entity_type, names in corrections.get("node_names_to_delete", {}).items():
        names_to_delete_by_type[entity_type] = set(_ensure_list(names))
    for entity_type, names_set in names_to_delete_by_type.items():
        items = _ensure_list(stage_output.get(entity_type))
        stage_output[entity_type] = [
            item for item in items if item.get("name") not in names_set
        ]

    # Process updates by entity type
    nodes_to_update = corrections.get("nodes_to_update", {})
    for entity_type, updates in nodes_to_update.items():
        update_map: dict[str, dict] = {}
        for u in _ensure_list(updates):
            name = u.get("name")
            if name:
                update_map[name] = u
        if update_map:
            items = _ensure_list(stage_output.get(entity_type))
            stage_output[entity_type] = [
                update_map.get(item.get("name"), item) for item in items
            ]

    # Process additions by entity type
    nodes_to_add = corrections.get("nodes_to_add", {})
    for entity_type, additions in nodes_to_add.items():
        existing = _ensure_list(stage_output.get(entity_type))
        existing.extend(_ensure_list(additions))
        stage_output[entity_type] = existing

    return stage_output


# ═══════════════════════════════════════════════════════════════════════════════
# Graph building (entity-centric)
# ═══════════════════════════════════════════════════════════════════════════════
def _validate_dag(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Validate that the graph is a DAG (no cycles). Returns list of cycle descriptions if any."""
    # Build adjacency list
    adj: dict[str, list[str]] = {}
    node_ids = {n["id"] for n in nodes}
    for e in edges:
        src, tgt = e.get("source", ""), e.get("target", "")
        if src in node_ids and tgt in node_ids:
            adj.setdefault(src, []).append(tgt)

    # DFS-based cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}
    parent: dict[str, str | None] = {}
    cycles: list[str] = []

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in adj.get(u, []):
            if color.get(v) == GRAY:
                # Found cycle — trace back
                path = [v, u]
                cur = u
                while parent.get(cur) and parent[cur] != v:
                    cur = parent[cur]
                    path.append(cur)
                path.append(v)
                cycles.append(" → ".join(reversed(path)))
                return True
            if color.get(v) == WHITE:
                parent[v] = u
                if dfs(v):
                    return True
        color[u] = BLACK
        return False

    for nid in node_ids:
        if color[nid] == WHITE:
            dfs(nid)

    return cycles


def _link_step_chemicals(
    step: dict[str, Any],
    step_node_id: str,
    grouped_output: dict[str, Any],
    doc_context: dict[str, Any],
    catalyst_name: str,
    add_node_fn: Callable[[str, dict[str, Any]], str],
    add_edge_fn: Callable[[str, str, str], None],
) -> None:
    """Link preparation step to chemicals via 消耗/产出 edges."""
    for direction, field, rel in [("inputs", "outputs", "消耗"), ("inputs", "outputs", "产出")]:
        pass  # placeholder, handled below

    # Inputs → 消耗 edges
    inputs_str = step.get("inputs", "").strip()
    if inputs_str:
        for chem_name in [s.strip() for s in inputs_str.split(",") if s.strip()]:
            chem_node_id = _find_or_create_chemical(
                chem_name, grouped_output, doc_context, catalyst_name, add_node_fn
            )
            # Determine role from chemical data
            chem_data = next((c for c in _ensure_list(grouped_output.get("化学物质")) if c.get("name") == chem_name), {})
            role = chem_data.get("role", "reactant")
            ep = {"role": role} if role else None
            add_edge_fn(step_node_id, "消耗", chem_node_id, ep)

    # Outputs → 产出 edges
    outputs_str = step.get("outputs", "").strip()
    if outputs_str:
        for out_name in [s.strip() for s in outputs_str.split(",") if s.strip()]:
            chem_node_id = _find_or_create_chemical(
                out_name, grouped_output, doc_context, catalyst_name, add_node_fn
            )
            add_edge_fn(step_node_id, "产出", chem_node_id)



def build_graph_draft(
    grouped_output: dict[str, Any],
    ontology_bundle: dict[str, Any],
    doc_context: dict[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_counter = 0
    relation_index = _build_relation_index(ontology_bundle["relation_types"])

    def next_id(entity_type: str) -> str:
        nonlocal node_counter
        node_counter += 1
        return f"{entity_type}:{node_counter}"

    def add_node(entity_type: str, properties: dict[str, Any]) -> str:
        node_id = next_id(entity_type)
        nodes.append({"id": node_id, "type": entity_type, "properties": properties})
        return node_id

    def add_edge(source_id: str, relation: str, target_id: str, edge_props: dict | None = None) -> None:
        edge = {"source": source_id, "relation": relation, "target": target_id}
        if edge_props:
            edge["properties"] = edge_props
        edges.append(edge)

    # Document node
    doc_node_id = add_node("文档", {
        "doc_id": doc_context.get("doc_id", "unknown-doc"),
        "title": doc_context.get("title", "Unknown"),
        "source": doc_context.get("source", "OCR"),
        "filename": doc_context.get("filename", "document.md"),
    })

    # ── Process each catalyst ──
    for catalyst in _ensure_list(grouped_output.get("催化剂")):
        catalyst_name = catalyst.get("name", "未命名催化剂")
        cat_props = _build_catalyst_properties(catalyst, doc_context)
        cat_node_id = add_node("催化剂", cat_props)
        add_edge(doc_node_id, "提及", cat_node_id)

        # ── 化学物质 (active_component, precursor, support) ──
        for chem in _ensure_list(grouped_output.get("化学物质")):
            chem_cat_name = chem.get("catalyst_name", "")
            if chem_cat_name and chem_cat_name != catalyst_name:
                continue
            role = chem.get("role", "unknown")
            chem_props = _normalize_props(chem, doc_context, catalyst_name)
            chem_node_id = add_node("化学物质", chem_props)

            relation_map = {
                "active_component": "含有活性组分",
                "precursor": "使用前驱体",
                "support": "负载于",
            }
            rel = relation_map.get(role)
            if rel:
                add_edge(cat_node_id, rel, chem_node_id)

        # ── 助剂 ──
        for promoter in _ensure_list(grouped_output.get("助剂")):
            prom_cat_name = promoter.get("catalyst_name", "")
            if prom_cat_name and prom_cat_name != catalyst_name:
                continue
            prom_props = _normalize_props(promoter, doc_context, catalyst_name)
            prom_node_id = add_node("助剂", prom_props)
            add_edge(cat_node_id, "添加助剂", prom_node_id)

        # ── 制备步骤 (linked list) ──
        prep_steps = _ensure_list(grouped_output.get("制备步骤"))
        cat_steps = [s for s in prep_steps if s.get("catalyst_name", "") == catalyst_name or not s.get("catalyst_name")]
        cat_steps.sort(key=lambda s: int(s.get("step_order", 0)))
        step_ids: list[str] = []
        for step in cat_steps:
            step_props = _normalize_props(step, doc_context, catalyst_name)
            sid = add_node("制备步骤", step_props)
            step_ids.append(sid)
            # Link step inputs/outputs to chemical nodes
            _link_step_chemicals(
                step, sid, grouped_output, doc_context, catalyst_name, add_node, add_edge
            )

        if step_ids:
            add_edge(cat_node_id, "制备于", step_ids[0])
            for i in range(len(step_ids) - 1):
                add_edge(step_ids[i], "下一步", step_ids[i + 1])

        # ── 测试 ──
        for test in _ensure_list(grouped_output.get("测试")):
            test_cat_name = test.get("catalyst_name", "")
            if test_cat_name and test_cat_name != catalyst_name:
                continue
            test_props = _normalize_props(test, doc_context, catalyst_name)
            test_node_id = add_node("测试", test_props)
            add_edge(cat_node_id, "测试于", test_node_id)

        # ── 表征 ──
        for char in _ensure_list(grouped_output.get("表征")):
            char_cat_name = char.get("catalyst_name", "")
            if char_cat_name and char_cat_name != catalyst_name:
                continue
            char_props = _normalize_props(char, doc_context, catalyst_name)
            char_node_id = add_node("表征", char_props)
            add_edge(cat_node_id, "表征于", char_node_id)

            # Cross-domain: 表征 → 证实 化学物质
            confirmed_phase = char.get("confirmed_phase", "").strip()
            if confirmed_phase:
                # Find or create chemical node for confirmed phase
                phase_node_id = _find_or_create_chemical(
                    confirmed_phase, grouped_output, doc_context, catalyst_name, add_node
                )
                add_edge(char_node_id, "证实", phase_node_id)

        # ── 机理 ──
        for mech in _ensure_list(grouped_output.get("机理")):
            mech_cat_name = mech.get("catalyst_name", "")
            if mech_cat_name and mech_cat_name != catalyst_name:
                continue
            mech_props = _normalize_props(mech, doc_context, catalyst_name)
            mech_node_id = add_node("机理", mech_props)
            add_edge(cat_node_id, "有机理", mech_node_id)

        # ── Cross-domain: 助剂 → 促进 机理, 助剂 → 影响性能 测试 ──
        # These are inferred when a promoter shares catalyst_name with a mechanism/test node
        prom_nodes = [n for n in nodes if n["type"] == "助剂" and n["properties"].get("catalyst_name") == catalyst_name]
        mech_nodes = [n for n in nodes if n["type"] == "机理" and n["properties"].get("catalyst_name") == catalyst_name]
        test_nodes = [n for n in nodes if n["type"] == "测试" and n["properties"].get("catalyst_name") == catalyst_name]
        for pn in prom_nodes:
            for mn in mech_nodes:
                add_edge(pn["id"], "促进", mn["id"])
            for tn in test_nodes:
                add_edge(pn["id"], "影响性能", tn["id"])

    # ── DAG validation ──
    cycles = _validate_dag(nodes, edges)
    if cycles:
        import logging
        _logger = logging.getLogger(__name__)
        _logger.warning(f"[DAG] {len(cycles)} cycle(s) detected in synthesis graph!")
        for c in cycles:
            _logger.warning(f"[DAG] cycle: {c}")

    return {
        "document": {
            "doc_id": doc_context.get("doc_id", "unknown-doc"),
            "title": doc_context.get("title", "Unknown"),
            "source": doc_context.get("source", "OCR"),
            "filename": doc_context.get("filename", "document.md"),
        },
        "nodes": nodes,
        "edges": edges,
    }


def _build_catalyst_properties(catalyst: dict[str, Any], doc_context: dict[str, Any]) -> dict[str, Any]:
    prop_names = [
        "name", "active_component", "precursor", "crystal_phase",
        "iron_ratio_value", "iron_ratio_unit",
        "surface_area_value", "surface_area_unit",
        "pore_structure",
        "particle_size_value", "particle_size_unit",
        "preparation_method",
        "mechanical_strength_value", "mechanical_strength_unit",
        "support", "source_text", "note",
    ]
    props = {"doc_id": doc_context.get("doc_id")}
    for pn in prop_names:
        if pn in catalyst and catalyst[pn] is not None and catalyst[pn] != "":
            props[pn] = catalyst[pn]
    props.setdefault("name", catalyst.get("name", "未命名催化剂"))
    return props


def _find_or_create_chemical(
    name: str,
    grouped_output: dict[str, Any],
    doc_context: dict[str, Any],
    catalyst_name: str,
    add_node_fn: Callable[[str, dict[str, Any]], str],
) -> str:
    """Find an existing chemical node by name or create a new one."""
    for chem in _ensure_list(grouped_output.get("化学物质")):
        if chem.get("name") == name:
            return add_node_fn("化学物质", _normalize_props(chem, doc_context, catalyst_name))
    return add_node_fn("化学物质", {
        "doc_id": doc_context.get("doc_id"),
        "name": name,
        "role": "confirmed_phase",
        "catalyst_name": catalyst_name,
    })


def _build_relation_index(relation_types: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    index: dict[tuple[str, str], str] = {}
    for rt in relation_types:
        for src in rt.get("source_types", []):
            for tgt in rt.get("target_types", []):
                index[(src, tgt)] = rt["name"]
    return index


def _normalize_props(payload: Any, doc_context: dict[str, Any], catalyst_name: str) -> dict[str, Any]:
    if isinstance(payload, dict):
        result = dict(payload)
    else:
        result = {"name": str(payload)}
    result.setdefault("doc_id", doc_context.get("doc_id"))
    result.setdefault("catalyst_name", catalyst_name)
    return result


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ═══════════════════════════════════════════════════════════════════════════════
# YAML parsers (adapted for v0.3.0 entity-centric format)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_node_types(path: Path) -> list[dict[str, Any]]:
    import yaml as _yaml_lib
    try:
        data = _yaml_lib.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        data = _parse_simple_yaml_list(path)
    if isinstance(data, dict):
        return data.get("node_types", [])
    return data or []


def _load_relation_types(path: Path) -> list[dict[str, Any]]:
    import yaml as _yaml_lib
    try:
        data = _yaml_lib.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        data = _parse_simple_yaml_list(path)
    if isinstance(data, dict):
        return data.get("relation_types", [])
    return data or []


def _parse_simple_yaml_list(path: Path) -> Any:
    """Fallback parser when PyYAML is not available."""
    content = path.read_text(encoding="utf-8")
    return _parse_yaml_value(content)


def _parse_yaml_value(text: str) -> Any:
    """Minimal YAML parser for the simple structure we use."""
    import ast
    lines = text.splitlines()
    result: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_key: str | None = None
    in_sequence: list[Any] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- name:"):
            if current is not None:
                result.append(current)
            current = {"name": stripped.split(":", 1)[1].strip()}
            in_sequence = None
            continue
        if current is None:
            continue
        # Key-value
        if ":" in stripped and not stripped.startswith("-"):
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                try:
                    current[key] = ast.literal_eval(val)
                except Exception:
                    current[key] = [v.strip() for v in val[1:-1].split(",")]
            else:
                current[key] = val
    if current is not None:
        result.append(current)
    return result
