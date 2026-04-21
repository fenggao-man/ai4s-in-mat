from __future__ import annotations

import json
import re
import time
import inspect
from pathlib import Path
from typing import Any, Callable

from .llm_client import call_kg_llm
from .prompts import ENTITY_EXTRACT_PROMPT


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_RUNTIME_DIR = PROJECT_ROOT / "Data" / "ontology_runtime"


def extract_graph_from_ocr_run(
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

    if verbose:
        print(f"[entity_extraction] run dir: {run_path}", flush=True)
        print(f"[entity_extraction] loading ontology...", flush=True)
    ontology_bundle = load_runtime_ontology()
    if verbose:
        print(
            f"[entity_extraction] ontology loaded: roots={len(ontology_bundle['root_types'])}, "
            f"relations={len(ontology_bundle['relation_types'])}",
            flush=True,
        )
        print(f"[entity_extraction] reading OCR markdown: {markdown_path}", flush=True)
    document_text = markdown_path.read_text(encoding="utf-8")
    if verbose:
        print(
            f"[entity_extraction] markdown loaded: chars={len(document_text)}",
            flush=True,
        )
        print("[entity_extraction] building extraction prompt...", flush=True)
    prompt = build_extraction_prompt(document_text=document_text, ontology_bundle=ontology_bundle)
    if verbose:
        print(
            f"[entity_extraction] prompt ready: chars={len(prompt)}",
            flush=True,
        )

    client = llm_client or call_kg_llm
    if verbose:
        print("[entity_extraction] calling KG LLM...", flush=True)
    client_signature = inspect.signature(client)
    if "verbose" in client_signature.parameters:
        raw_output = client(prompt, llm_model, verbose=verbose)
    else:
        raw_output = client(prompt, llm_model)

    if verbose:
        print(
            f"[entity_extraction] raw extraction received: chars={len(raw_output)}",
            flush=True,
        )
        print("[entity_extraction] parsing grouped output...", flush=True)
    grouped_output = parse_grouped_output(raw_output)
    doc_context = {
        "doc_id": run_path.name,
        "filename": markdown_path.name,
        **(grouped_output.get("document") or {}),
    }
    if verbose:
        print("[entity_extraction] building graph draft...", flush=True)
    graph = build_graph_draft(
        grouped_output=grouped_output,
        ontology_bundle=ontology_bundle,
        doc_context=doc_context,
    )

    output_dir = run_path / "knowledge_graph"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output_path = output_dir / "entity_graph_raw.txt"
    if verbose:
        print(f"[entity_extraction] writing raw extraction: {raw_output_path}", flush=True)
    raw_output_path.write_text(raw_output, encoding="utf-8")
    graph_path = output_dir / "entity_graph.json"
    if verbose:
        print(f"[entity_extraction] writing graph json: {graph_path}", flush=True)
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    if verbose:
        elapsed = time.perf_counter() - started_at
        print(
            f"[entity_extraction] completed: nodes={len(graph['nodes'])}, "
            f"edges={len(graph['edges'])}, elapsed={elapsed:.2f}s",
            flush=True,
        )
    return graph_path


def extract_entities_from_ocr_run(
    run_dir: str | Path,
    llm_client: Callable[[str, str | None], str] | None = None,
    llm_model: str | None = None,
    verbose: bool = False,
) -> Path:
    return extract_graph_from_ocr_run(run_dir=run_dir, llm_client=llm_client, llm_model=llm_model, verbose=verbose)


def load_runtime_ontology(ontology_dir: str | Path = ONTOLOGY_RUNTIME_DIR) -> dict[str, Any]:
    ontology_path = Path(ontology_dir)
    node_types = _load_node_types(ontology_path / "node_types.yaml")
    relation_types = _load_relation_types(ontology_path / "relation_types.yaml")
    concept_tree = _load_concept_tree(ontology_path / "concept_tree.yaml")
    return {
        "node_types": node_types,
        "relation_types": relation_types,
        "concept_tree": concept_tree,
        "root_types": [item["name"] for item in node_types if item.get("level") == "root"],
    }


def build_extraction_prompt(document_text: str, ontology_bundle: dict[str, Any]) -> str:
    ontology_text = json.dumps(
        {
            "root_types": ontology_bundle["root_types"],
            "concept_tree": ontology_bundle["concept_tree"],
            "relation_types": ontology_bundle["relation_types"],
        },
        ensure_ascii=False,
        indent=2,
    )
    return ENTITY_EXTRACT_PROMPT.format(ontology_text=ontology_text, text=document_text)


def parse_grouped_output(raw_output: str) -> dict[str, Any]:
    cleaned = raw_output.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Grouped extraction output must be a JSON object.")
    return parsed


def build_graph_draft(
    grouped_output: dict[str, Any],
    ontology_bundle: dict[str, Any],
    doc_context: dict[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_counter = 0
    relation_whitelist = {
        (item["source"], item["target"]): item["relation"]
        for item in ontology_bundle["relation_types"]
    }

    def next_id(node_type: str) -> str:
        nonlocal node_counter
        node_counter += 1
        return f"{node_type}:{node_counter}"

    def add_node(node_type: str, properties: dict[str, Any], level: str) -> str:
        node_id = next_id(node_type)
        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "level": level,
                "properties": properties,
            }
        )
        return node_id

    document_node_id = add_node(
        "文档",
        {
            "doc_id": doc_context.get("doc_id", "unknown-doc"),
            "title": doc_context.get("title", "Unknown"),
            "source": doc_context.get("source", "OCR"),
            "filename": doc_context.get("filename", "document.md"),
        },
        "root",
    )

    for catalyst in _ensure_list(grouped_output.get("催化剂")):
        catalyst_name = catalyst.get("name", "未命名催化剂")
        catalyst_properties = {"doc_id": doc_context.get("doc_id"), "name": catalyst_name}
        if "note" in catalyst:
            catalyst_properties["note"] = catalyst["note"]
        catalyst_node_id = add_node("催化剂", catalyst_properties, "root")
        edges.append({"source": document_node_id, "relation": "提及", "target": catalyst_node_id})

        _build_children(
            parent_type="催化剂",
            parent_id=catalyst_node_id,
            parent_data=catalyst,
            ontology_bundle=ontology_bundle,
            relation_whitelist=relation_whitelist,
            add_node=add_node,
            edges=edges,
            doc_context=doc_context,
            catalyst_name=catalyst_name,
        )

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


def _build_children(
    parent_type: str,
    parent_id: str,
    parent_data: dict[str, Any],
    ontology_bundle: dict[str, Any],
    relation_whitelist: dict[tuple[str, str], str],
    add_node: Callable[[str, dict[str, Any], str], str],
    edges: list[dict[str, Any]],
    doc_context: dict[str, Any],
    catalyst_name: str,
) -> None:
    root_types = set(ontology_bundle["root_types"])
    concept_map = ontology_bundle["concept_tree"]

    for child_type in concept_map.get(parent_type, []):
        for child in _ensure_list(parent_data.get(child_type)):
            child_node_id = add_node(
                child_type,
                _normalize_properties(child, doc_context, catalyst_name),
                "child",
            )
            relation = relation_whitelist.get((parent_type, child_type))
            if relation:
                edges.append({"source": parent_id, "relation": relation, "target": child_node_id})

    for root_type in root_types:
        if root_type == "文档" or root_type == parent_type:
            continue
        for root_item in _ensure_list(parent_data.get(root_type)):
            root_node_id = add_node(
                root_type,
                _normalize_properties(root_item, doc_context, catalyst_name),
                "root",
            )
            relation = relation_whitelist.get((parent_type, root_type))
            if relation:
                edges.append({"source": parent_id, "relation": relation, "target": root_node_id})
            _build_children(
                parent_type=root_type,
                parent_id=root_node_id,
                parent_data=root_item,
                ontology_bundle=ontology_bundle,
                relation_whitelist=relation_whitelist,
                add_node=add_node,
                edges=edges,
                doc_context=doc_context,
                catalyst_name=catalyst_name,
            )


def _normalize_properties(payload: Any, doc_context: dict[str, Any], catalyst_name: str) -> dict[str, Any]:
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


def _load_node_types(path: Path) -> list[dict[str, Any]]:
    node_types: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- name: "):
            if current is not None:
                node_types.append(current)
            current = {"name": stripped.split(": ", 1)[1]}
            continue
        if current is None:
            continue
        if stripped.startswith("level: "):
            current["level"] = stripped.split(": ", 1)[1]
            continue
        if stripped.startswith("parent_type: "):
            current["parent_type"] = stripped.split(": ", 1)[1]
            continue
    if current is not None:
        node_types.append(current)
    return node_types


def _load_relation_types(path: Path) -> list[dict[str, str]]:
    relation_types: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- name: "):
            if current is not None:
                relation_types.append(current)
            current = {"relation": stripped.split(": ", 1)[1]}
            continue
        if current is None:
            continue
        if stripped.startswith("source_types: "):
            current["source"] = _parse_inline_list(stripped.split(": ", 1)[1])[0]
            continue
        if stripped.startswith("target_types: "):
            current["target"] = _parse_inline_list(stripped.split(": ", 1)[1])[0]
            continue
    if current is not None:
        relation_types.append(current)
    return relation_types


def _load_concept_tree(path: Path) -> dict[str, list[str]]:
    concept_tree: dict[str, list[str]] = {}
    current_root: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- root: "):
            current_root = stripped.split(": ", 1)[1]
            concept_tree[current_root] = []
            continue
        if current_root is None:
            continue
        if re.match(r"^- ", stripped):
            concept_tree[current_root].append(stripped[2:].strip())
    return concept_tree


def _parse_inline_list(value: str) -> list[str]:
    cleaned = value.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    if not cleaned:
        return []
    return [item.strip() for item in cleaned.split(",") if item.strip()]
