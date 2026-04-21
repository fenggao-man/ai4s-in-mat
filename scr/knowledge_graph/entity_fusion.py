from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def fuse_entity_graph_from_run(run_dir: str | Path, verbose: bool = False) -> Path:
    run_path = Path(run_dir)
    graph_path = run_path / "knowledge_graph" / "entity_graph_aligned.json"
    if not graph_path.exists():
        raise FileNotFoundError(graph_path)
    return fuse_entity_graph(graph_path=graph_path, verbose=verbose)


def fuse_entity_graph(graph_path: str | Path, verbose: bool = False) -> Path:
    source_path = Path(graph_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))

    fused = build_fused_graph(data)
    output_path = source_path.with_name("entity_graph_fused.json")
    output_path.write_text(json.dumps(fused, ensure_ascii=False, indent=2), encoding="utf-8")

    if verbose:
        print(f"[entity_fusion] source graph: {source_path}", flush=True)
        print(
            f"[entity_fusion] fused graph saved: {output_path} "
            f"(nodes={len(fused['nodes'])}, edges={len(fused['edges'])})",
            flush=True,
        )
    return output_path


def build_fused_graph(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    group_to_fused_id: dict[tuple[str, str], str] = {}
    original_to_fused_id: dict[str, str] = {}
    fused_nodes: list[dict[str, Any]] = []

    for node in nodes:
        fused_key = _build_fused_key(node)
        fused_id = group_to_fused_id.get(fused_key)
        if fused_id is None:
            fused_id = f"fused:{node['type']}:{len(fused_nodes) + 1}"
            group_to_fused_id[fused_key] = fused_id
            fused_nodes.append(_create_fused_node(node=node, fused_id=fused_id))
        else:
            fused_node = next(item for item in fused_nodes if item["id"] == fused_id)
            _merge_node_into_fused(fused_node=fused_node, node=node)
        original_to_fused_id[node["id"]] = fused_id

    fused_edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        mapped_edge = {
            "source": original_to_fused_id.get(edge["source"], edge["source"]),
            "relation": edge["relation"],
            "target": original_to_fused_id.get(edge["target"], edge["target"]),
        }
        edge_key = (mapped_edge["source"], mapped_edge["relation"], mapped_edge["target"])
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        fused_edges.append(mapped_edge)

    for fused_node in fused_nodes:
        properties = fused_node["properties"]
        aliases = sorted(set(properties.get("aliases", [])))
        source_node_ids = sorted(set(properties.get("source_node_ids", [])))
        properties["aliases"] = aliases
        properties["source_node_ids"] = source_node_ids
        properties["merged_from_count"] = len(source_node_ids)
        properties["fusion_status"] = "merged" if len(source_node_ids) > 1 else "single"

    return {
        "document": graph.get("document", {}),
        "nodes": fused_nodes,
        "edges": fused_edges,
    }


def _build_fused_key(node: dict[str, Any]) -> tuple[str, str]:
    properties = node.get("properties") or {}
    label = str(
        properties.get("display_name")
        or properties.get("original_name")
        or properties.get("name")
        or properties.get("value")
        or node["id"]
    ).strip()
    return node["type"], label


def _create_fused_node(node: dict[str, Any], fused_id: str) -> dict[str, Any]:
    properties = dict(node.get("properties") or {})
    alias_seed = [
        value
        for value in [
            properties.get("display_name"),
            properties.get("original_name"),
            properties.get("name"),
        ]
        if value
    ]
    properties["aliases"] = list(dict.fromkeys(str(item).strip() for item in alias_seed if str(item).strip()))
    properties["source_node_ids"] = [node["id"]]
    return {
        "id": fused_id,
        "type": node["type"],
        "level": node.get("level"),
        "properties": properties,
    }


def _merge_node_into_fused(fused_node: dict[str, Any], node: dict[str, Any]) -> None:
    fused_properties = fused_node["properties"]
    node_properties = dict(node.get("properties") or {})

    for key, value in node_properties.items():
        if key in {"aliases", "source_node_ids", "merged_from_count", "fusion_status"}:
            continue
        if key not in fused_properties or _is_empty(fused_properties[key]):
            fused_properties[key] = value

    for value in [
        node_properties.get("display_name"),
        node_properties.get("original_name"),
        node_properties.get("name"),
    ]:
        if value and str(value).strip():
            fused_properties.setdefault("aliases", []).append(str(value).strip())

    fused_properties.setdefault("source_node_ids", []).append(node["id"])


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []
