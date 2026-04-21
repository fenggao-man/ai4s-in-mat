from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .llm_client import DEFAULT_ENV_FILE, load_env_file

DOCUMENT_FIELDS = {"doc_id", "title", "source", "filename"}
NAME_FIELDS = {"display_name", "original_name", "doc_id"}
VALUE_FIELDS = {"value", "unit", "display_name", "original_name", "doc_id"}

VALUE_NODE_TYPES = {
    "粒径",
    "比表面积",
    "助剂含量",
    "温度",
    "压力",
    "空速",
    "反应时间",
    "焙烧温度",
    "还原活化",
    "氨合成活性",
    "转化率",
}


def store_entity_graph_from_run(
    run_dir: str | Path,
    env_file: str | Path = DEFAULT_ENV_FILE,
    verbose: bool = False,
    driver_factory: Callable[..., Any] | None = None,
) -> Path:
    run_path = Path(run_dir)
    graph_path = run_path / "knowledge_graph" / "entity_graph_fused.json"
    if not graph_path.exists():
        raise FileNotFoundError(graph_path)
    return store_entity_graph(
        graph_path=graph_path,
        env_file=env_file,
        verbose=verbose,
        driver_factory=driver_factory,
    )


def clear_entity_graph_database(
    env_file: str | Path = DEFAULT_ENV_FILE,
    verbose: bool = False,
    driver_factory: Callable[..., Any] | None = None,
) -> dict[str, str]:
    config = _load_neo4j_config(env_file=env_file)

    if verbose:
        print(
            f"[entity_storage] clearing neo4j database: uri={config['uri']}, database={config['database']}",
            flush=True,
        )

    driver = _build_driver(config=config, driver_factory=driver_factory)
    try:
        with driver.session(database=config["database"]) as session:
            session.run("MATCH (n) DETACH DELETE n")
    finally:
        driver.close()

    result = {
        "database": config["database"],
        "uri": config["uri"],
        "status": "cleared",
    }
    if verbose:
        print("[entity_storage] database cleared", flush=True)
    return result


def store_entity_graph(
    graph_path: str | Path,
    env_file: str | Path = DEFAULT_ENV_FILE,
    verbose: bool = False,
    driver_factory: Callable[..., Any] | None = None,
) -> Path:
    source_path = Path(graph_path)
    graph = json.loads(source_path.read_text(encoding="utf-8"))
    storage_graph = build_storage_graph(graph)
    storage_ready_path = source_path.with_name("entity_graph_storage_ready.json")
    storage_ready_path.write_text(json.dumps(storage_graph, ensure_ascii=False, indent=2), encoding="utf-8")
    config = _load_neo4j_config(env_file=env_file)

    if verbose:
        print(
            f"[entity_storage] connecting neo4j: uri={config['uri']}, database={config['database']}",
            flush=True,
        )
        print(f"[entity_storage] storage-ready graph: {storage_ready_path}", flush=True)

    driver = _build_driver(config=config, driver_factory=driver_factory)
    try:
        with driver.session(database=config["database"]) as session:
            _create_constraints(session=session, graph=storage_graph)
            node_count = _store_nodes(session=session, graph=storage_graph)
            edge_count = _store_edges(session=session, graph=storage_graph)
    finally:
        driver.close()

    report = {
        "graph_path": str(source_path),
        "storage_ready_path": str(storage_ready_path),
        "database": config["database"],
        "uri": config["uri"],
        "node_count": node_count,
        "edge_count": edge_count,
        "status": "stored",
    }
    report_path = source_path.with_name("entity_graph_storage_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if verbose:
        print(
            f"[entity_storage] stored graph: nodes={node_count}, edges={edge_count}",
            flush=True,
        )
        print(f"[entity_storage] report saved: {report_path}", flush=True)
    return report_path


def build_storage_graph(graph: dict[str, Any]) -> dict[str, Any]:
    projected_nodes = [_project_node(node) for node in graph.get("nodes", [])]
    return {
        "document": graph.get("document", {}),
        "nodes": projected_nodes,
        "edges": graph.get("edges", []),
    }


def _load_neo4j_config(env_file: str | Path) -> dict[str, str]:
    import os

    load_env_file(env_file)
    uri = os.environ.get("NEO4J_URI", "").strip()
    username = os.environ.get("NEO4J_USERNAME", os.environ.get("NEO4J_USER", "")).strip()
    password = os.environ.get("NEO4J_PASSWORD", "").strip()
    database = os.environ.get("NEO4J_DATABASE", "neo4j").strip() or "neo4j"

    if not uri:
        raise ValueError("NEO4J_URI is required")
    if not username:
        raise ValueError("NEO4J_USERNAME or NEO4J_USER is required")
    if not password:
        raise ValueError("NEO4J_PASSWORD is required")

    return {
        "uri": uri,
        "username": username,
        "password": password,
        "database": database,
    }


def _build_driver(config: dict[str, str], driver_factory: Callable[..., Any] | None = None) -> Any:
    if driver_factory is not None:
        return driver_factory(config["uri"], auth=(config["username"], config["password"]))

    try:
        from neo4j import GraphDatabase
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "neo4j package is not installed in the active Python environment. "
            "Install it before running entity storage."
        ) from exc

    return GraphDatabase.driver(config["uri"], auth=(config["username"], config["password"]))


def _create_constraints(session: Any, graph: dict[str, Any]) -> None:
    labels = sorted({node["type"] for node in graph.get("nodes", [])})
    for label in labels:
        session.run(
            f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{_quote_identifier(label)}) REQUIRE n.id IS UNIQUE"
        )


def _store_nodes(session: Any, graph: dict[str, Any]) -> int:
    nodes = graph.get("nodes", [])
    for node in nodes:
        props = _sanitize_properties(node.get("properties") or {})
        props["id"] = node["id"]
        props["type"] = node["type"]
        props["level"] = node.get("level")
        session.run(
            f"""
            MERGE (n:{_quote_identifier(node['type'])} {{id: $id}})
            SET n = $props
            """,
            id=node["id"],
            props=props,
        )
    return len(nodes)


def _store_edges(session: Any, graph: dict[str, Any]) -> int:
    edges = graph.get("edges", [])
    for edge in edges:
        session.run(
            f"""
            MATCH (a {{id: $source_id}})
            MATCH (b {{id: $target_id}})
            MERGE (a)-[r:{_quote_identifier(edge['relation'])}]->(b)
            """,
            source_id=edge["source"],
            target_id=edge["target"],
        )
    return len(edges)


def _project_node(node: dict[str, Any]) -> dict[str, Any]:
    projected_node = dict(node)
    props = dict(node.get("properties") or {})
    node_type = node.get("type", "")
    keep_fields = _resolve_keep_fields(node_type=node_type)

    projected_props = {key: props[key] for key in keep_fields if key in props}

    if "display_name" not in projected_props:
        fallback = props.get("display_name") or props.get("name")
        if fallback:
            projected_props["display_name"] = fallback
    if "original_name" not in projected_props:
        fallback = props.get("original_name") or props.get("name")
        if fallback:
            projected_props["original_name"] = fallback

    projected_node["properties"] = projected_props
    return projected_node


def _resolve_keep_fields(node_type: str) -> set[str]:
    if node_type == "文档":
        return set(DOCUMENT_FIELDS)
    if node_type in VALUE_NODE_TYPES:
        return set(VALUE_FIELDS)
    return set(NAME_FIELDS)


def _sanitize_properties(properties: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in properties.items():
        sanitized[key] = _sanitize_property_value(value)
    return sanitized


def _sanitize_property_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, list):
        if all(item is None or isinstance(item, (str, int, float, bool)) for item in value):
            return value
        return json.dumps(value, ensure_ascii=False)

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def _quote_identifier(value: str) -> str:
    escaped = value.replace("`", "``")
    return f"`{escaped}`"
