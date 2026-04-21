from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SUBSCRIPT_MAP = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
SUPERSCRIPT_MINUS = "⁻"
SUPPORTED_METHOD_TYPES = {
    "表征方法",
    "XRD",
    "BET",
    "TEM",
    "SEM",
    "XPS",
    "H₂-TPR",
    "N₂-TPD",
    "NH₃-TPD",
    "Mössbauer",
    "Raman",
    "FT-IR",
}
TARGET_NAME_TYPES = {
    "催化剂",
    "助剂",
    "助剂种类",
    "活性组分",
    "前驱体",
    "晶相结构",
    "孔结构",
    "制备方式",
    "表征方法",
    "XRD",
    "BET",
    "TEM",
    "SEM",
    "XPS",
    "H2-TPR",
    "N2-TPD",
    "NH3-TPD",
    "Mössbauer",
    "Raman",
    "FT-IR",
}
VALUE_UNIT_TYPES = {"温度", "压力", "粒径", "比表面积", "空速", "助剂含量"}
UNIT_MAP = {
    "C": "°C",
    "°C": "°C",
    "MPa": "MPa",
    "nm": "nm",
    "wt%": "wt%",
    "m2/g": "m²/g",
    "m^2/g": "m²/g",
    "m²/g": "m²/g",
    "h-1": "h⁻¹",
    "h^-1": "h⁻¹",
    "h⁻¹": "h⁻¹",
}
METHOD_NAME_MAP = {
    "H2-TPR": "H₂-TPR",
    "N2-TPD": "N₂-TPD",
    "NH3-TPD": "NH₃-TPD",
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
        print(f"[entity_alignment] source graph: {source_path}", flush=True)
        print(
            f"[entity_alignment] aligned graph saved: {output_path} "
            f"(nodes={len(aligned['nodes'])}, edges={len(aligned['edges'])})",
            flush=True,
        )
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
        edge_key = (
            aligned_edge["source"],
            aligned_edge["relation"],
            aligned_edge["target"],
        )
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

    display_name, original_name, method = _derive_display_name(node_type=node_type, properties=properties)
    if original_name:
        properties.setdefault("original_name", original_name)
    if display_name:
        properties["display_name"] = display_name
    if method:
        properties["normalization_method"] = method

    aligned_node["properties"] = properties
    return aligned_node


def _derive_display_name(node_type: str, properties: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    original_name = _extract_original_name(node_type=node_type, properties=properties)
    if not original_name:
        return None, None, None

    if node_type in VALUE_UNIT_TYPES:
        return _normalize_value_unit(original_name, properties)

    if node_type in TARGET_NAME_TYPES:
        display_name = _normalize_name(node_type=node_type, raw_name=original_name)
        return display_name, original_name, "format_standard"

    return original_name, original_name, "pass_through"


def _extract_original_name(node_type: str, properties: dict[str, Any]) -> str | None:
    if properties.get("original_name"):
        return str(properties["original_name"]).strip()

    if node_type in VALUE_UNIT_TYPES and properties.get("value") is not None:
        value = str(properties.get("value")).strip()
        unit = str(properties.get("unit", "")).strip()
        return f"{value}{unit}" if unit else value

    for key in ("name", "value"):
        if properties.get(key) is not None:
            value = str(properties[key]).strip()
            if value:
                return value
    return None


def _normalize_value_unit(raw_name: str, properties: dict[str, Any]) -> tuple[str, str, str]:
    value = str(properties.get("value", "")).strip()
    unit = str(properties.get("unit", "")).strip()

    if not value:
        parsed_value, parsed_unit = _split_value_unit(raw_name)
        value = parsed_value or raw_name.strip()
        unit = parsed_unit or unit

    normalized_unit = _normalize_unit(unit)
    properties["value"] = value
    if normalized_unit:
        properties["unit"] = normalized_unit
        return f"{value} {normalized_unit}", raw_name, "format_standard"
    return value, raw_name, "format_standard"


def _split_value_unit(raw_name: str) -> tuple[str | None, str | None]:
    compact = raw_name.replace(" ", "")
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)(.*)$", compact)
    if not match:
        return None, None
    value, unit = match.groups()
    return value, unit or None


def _normalize_unit(unit: str) -> str:
    cleaned = unit.strip()
    if not cleaned:
        return ""
    return UNIT_MAP.get(cleaned, _normalize_formula(cleaned))


def _normalize_name(node_type: str, raw_name: str) -> str:
    text = raw_name.strip()
    if node_type == "催化剂":
        text = _normalize_catalyst_name(text)
    elif node_type in SUPPORTED_METHOD_TYPES:
        text = METHOD_NAME_MAP.get(text, text)
    else:
        text = _normalize_formula(text)

    return text


def _normalize_catalyst_name(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", "", text)
    text = text.replace(":", "/")
    text = re.sub(r"(?<=[A-Za-z0-9₀₁₂₃₄₅₆₇₈₉])-(?=[A-Z])", "-", text)
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
    normalized = re.sub(r"([A-Za-z\)])(\d+)", lambda m: m.group(1) + m.group(2).translate(SUBSCRIPT_MAP), normalized)
    normalized = normalized.replace("^−1", SUPERSCRIPT_MINUS + "¹")
    normalized = normalized.replace("^-1", SUPERSCRIPT_MINUS + "¹")
    normalized = normalized.replace("-1", SUPERSCRIPT_MINUS + "¹") if normalized.endswith("-1") else normalized
    normalized = normalized.replace("m2/g", "m²/g")
    return normalized


def _build_dedup_key(node: dict[str, Any]) -> tuple[str, str] | None:
    node_type = node.get("type", "")
    if node_type == "文档":
        return None

    properties = node.get("properties") or {}
    display_name = str(properties.get("display_name", "")).strip()
    if not display_name:
        return None
    return node_type, display_name
