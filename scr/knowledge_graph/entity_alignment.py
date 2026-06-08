from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SUBSCRIPT_MAP = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
SUPERSCRIPT_MINUS = "⁻"

# Characterization method name normalization
METHOD_NAME_MAP: dict[str, str] = {
    "H2-TPR": "H₂-TPR",
    "N2-TPD": "N₂-TPD",
    "NH3-TPD": "NH₃-TPD",
}

UNIT_MAP: dict[str, str] = {
    "C": "°C", "°C": "°C",
    "MPa": "MPa",
    "nm": "nm",
    "wt%": "wt%", "wt.%": "wt%",
    "m2/g": "m²/g", "m^2/g": "m²/g", "m²/g": "m²/g",
    "h-1": "h⁻¹", "h^-1": "h⁻¹", "h⁻¹": "h⁻¹",
    "mL/g": "mL/g", "cm3/g": "cm³/g",
}


def align_entity_graph_from_run(run_dir: str | Path, verbose: bool = False) -> Path:
    run_path = Path(run_dir)
    graph_path = run_path / "knowledge_graph" / "entity_graph.json"
    if not graph_path.exists():
        raise FileNotFoundError(graph_path)
    return align_entity_graph(graph_path=graph_path, verbose=verbose)


def align_entity_graph(graph_path: str | Path, verbose: bool = False) -> Path:
    source_path = Path(graph_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))

    aligned = build_aligned_graph(data)
    output_path = source_path.with_name("entity_graph_aligned.json")
    output_path.write_text(json.dumps(aligned, ensure_ascii=False, indent=2), encoding="utf-8")

    if verbose:
        print(f"[entity_alignment] aligned: nodes={len(aligned['nodes'])}, edges={len(aligned['edges'])}", flush=True)
    return output_path


def build_aligned_graph(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    deduped_nodes: list[dict[str, Any]] = []
    node_id_map: dict[str, str] = {}
    dedup_key_to_id: dict[tuple[str, str], str] = {}

    for node in nodes:
        aligned_node = _align_node(node)
        dedup_key = _build_dedup_key(aligned_node)
        if dedup_key is None:
            deduped_nodes.append(aligned_node)
            node_id_map[node["id"]] = aligned_node["id"]
            continue

        existing_id = dedup_key_to_id.get(dedup_key)
        if existing_id is None:
            deduped_nodes.append(aligned_node)
            dedup_key_to_id[dedup_key] = aligned_node["id"]
            node_id_map[node["id"]] = aligned_node["id"]
            continue

        node_id_map[node["id"]] = existing_id

    deduped_edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        aligned_edge = {
            "source": node_id_map.get(edge["source"], edge["source"]),
            "relation": edge["relation"],
            "target": node_id_map.get(edge["target"], edge["target"]),
        }
        edge_key = (aligned_edge["source"], aligned_edge["relation"], aligned_edge["target"])
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        deduped_edges.append(aligned_edge)

    return {
        "document": graph.get("document", {}),
        "nodes": deduped_nodes,
        "edges": deduped_edges,
    }


def _align_node(node: dict[str, Any]) -> dict[str, Any]:
    aligned_node = dict(node)
    properties = dict(node.get("properties") or {})
    node_type = node.get("type", "")

    # Normalize display name based on entity type
    display_name, original_name, method = _derive_display_name(node_type, properties)
    if original_name:
        properties.setdefault("original_name", original_name)
    if display_name:
        properties["display_name"] = display_name
    if method:
        properties["normalization_method"] = method

    # Normalize unit fields in properties
    for key in list(properties.keys()):
        if key.endswith("_unit") and properties[key]:
            properties[key] = _normalize_unit(str(properties[key]))

    aligned_node["properties"] = properties
    return aligned_node


def _derive_display_name(
    node_type: str, properties: dict[str, Any]
) -> tuple[str | None, str | None, str | None]:
    """Derive display_name based on entity type."""
    original_name = _extract_primary_name(node_type, properties)
    if not original_name:
        return None, None, None

    if node_type == "催化剂":
        display = _normalize_catalyst_name(original_name)
        return display, original_name, "format_standard"

    if node_type == "化学物质":
        display = _normalize_formula(original_name)
        return display, original_name, "format_standard"

    if node_type == "助剂":
        display = _normalize_formula(original_name)
        return display, original_name, "format_standard"

    if node_type == "表征":
        # Normalize method name
        method_name = properties.get("method", original_name)
        normalized_method = METHOD_NAME_MAP.get(method_name, method_name)
        normalized_method = _normalize_formula(normalized_method)
        return normalized_method, method_name, "method_normalization"

    return original_name, original_name, "pass_through"


def _extract_primary_name(node_type: str, properties: dict[str, Any]) -> str | None:
    """Extract the primary identifier for an entity."""
    if node_type == "表征":
        return properties.get("method") or properties.get("name")

    if properties.get("original_name"):
        return str(properties["original_name"]).strip()

    return properties.get("name") or properties.get("display_name")


def _normalize_catalyst_name(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", "", text)
    text = text.replace(":", "/")
    parts = text.split("/")
    if len(parts) >= 2:
        left = _normalize_formula(parts[0])
        right = "/".join(parts[1:])
        right_components = [_normalize_formula(part) for part in right.split("-") if part]
        return left + "/" + "-".join(right_components)
    return _normalize_formula(text)


def _normalize_formula(text: str) -> str:
    normalized = text.strip()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(
        r"([A-Za-z\)])(\d+)",
        lambda m: m.group(1) + m.group(2).translate(SUBSCRIPT_MAP),
        normalized,
    )
    normalized = normalized.replace("^−1", SUPERSCRIPT_MINUS + "¹")
    normalized = normalized.replace("^-1", SUPERSCRIPT_MINUS + "¹")
    if normalized.endswith("-1"):
        normalized = normalized[:-2] + SUPERSCRIPT_MINUS + "¹"
    normalized = normalized.replace("m2/g", "m²/g")
    return normalized


def _normalize_unit(unit: str) -> str:
    cleaned = unit.strip()
    if not cleaned:
        return ""
    return UNIT_MAP.get(cleaned, cleaned)


def _build_dedup_key(node: dict[str, Any]) -> tuple[str, str] | None:
    node_type = node.get("type", "")
    if node_type == "文档":
        return None

    properties = node.get("properties") or {}
    display_name = str(properties.get("display_name", "")).strip()
    if not display_name:
        display_name = str(properties.get("name", "")).strip()
    if not display_name:
        return None
    return node_type, display_name
