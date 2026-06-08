from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .llm_client import DEFAULT_ENV_FILE, load_env_file

# Properties to exclude from Neo4j (pipeline noise)
_PIPELINE_NOISE_KEYS = {
    "aliases", "source_node_ids", "merged_from_count",
    "fusion_status", "normalization_method",
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
        graph_path=graph_path, env_file=env_file,
        verbose=verbose, driver_factory=driver_factory,
    )


def clear_entity_graph_database(
    env_file: str | Path = DEFAULT_ENV_FILE,
    verbose: bool = False,
    driver_factory: Callable[..., Any] | None = None,
) -> dict[str, str]:
    config = _load_neo4j_config(env_file=env_file)
    if verbose:
        print(f"[entity_storage] clearing neo4j: {config['uri']}", flush=True)
    driver = _build_driver(config=config, driver_factory=driver_factory)
    try:
        with driver.session(database=config["database"]) as session:
            session.run("MATCH (n) DETACH DELETE n")
    finally:
        driver.close()
    return {"database": config["database"], "uri": config["uri"], "status": "cleared"}


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
        print(f"[entity_storage] connecting neo4j: {config['uri']}", flush=True)

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
        print(f"[entity_storage] stored: nodes={node_count}, edges={edge_count}", flush=True)
    return report_path


def build_storage_graph(graph: dict[str, Any]) -> dict[str, Any]:
    projected_nodes = [_project_node(node) for node in graph.get("nodes", [])]
    return {
        "document": graph.get("document", {}),
        "nodes": projected_nodes,
        "edges": graph.get("edges", []),
    }


def _project_node(node: dict[str, Any]) -> dict[str, Any]:
    """Project node properties: drop pipeline noise, keep domain data."""
    projected = dict(node)
    props = dict(node.get("properties") or {})

    projected_props: dict[str, Any] = {}
    for key, value in props.items():
        if key in _PIPELINE_NOISE_KEYS:
            continue
        if value is None or value == "" or value == []:
            continue
        projected_props[key] = value

    # Ensure display_name exists for graph readability
    if "display_name" not in projected_props:
        fallback = props.get("display_name") or props.get("name")
        if fallback:
            projected_props["display_name"] = str(fallback)

    projected["properties"] = projected_props
    return projected


# ═══════════════════════════════════════════════════════════════════════════════
# Neo4j helpers (unchanged from v0.2.0)
# ═══════════════════════════════════════════════════════════════════════════════

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
    return {"uri": uri, "username": username, "password": password, "database": database}


def _build_driver(config: dict[str, str], driver_factory: Callable[..., Any] | None = None) -> Any:
    if driver_factory is not None:
        return driver_factory(config["uri"], auth=(config["username"], config["password"]))
    try:
        from neo4j import GraphDatabase
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "neo4j package is not installed. Install it before running entity storage."
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
        edge_props = _sanitize_properties(edge.get("properties") or {})
        if edge_props:
            # Build SET clause for edge properties
            set_parts = []
            params = {"source_id": edge["source"], "target_id": edge["target"]}
            for key, value in edge_props.items():
                param_key = f"ep_{key}"
                set_parts.append(f"r.{_quote_identifier(key)} = ${param_key}")
                params[param_key] = value
            set_clause = ", ".join(set_parts)
            session.run(
                f"""
                MATCH (a {{id: $source_id}})
                MATCH (b {{id: $target_id}})
                MERGE (a)-[r:{_quote_identifier(edge['relation'])}]->(b)
                SET {set_clause}
                """,
                **params,
            )
        else:
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
