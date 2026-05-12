from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("artifacts") / "kg_retrieval.sqlite3"


def initialize_retrieval_database(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        _initialize_schema(conn)
    return path


def index_graph_for_retrieval(
    graph_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    document_markdown_path: str | Path | None = None,
) -> dict[str, Any]:
    graph_file = Path(graph_path)
    graph = json.loads(graph_file.read_text(encoding="utf-8"))
    db_file = initialize_retrieval_database(db_path)

    document = dict(graph.get("document") or {})
    doc_id = str(document.get("doc_id") or graph_file.parent.parent.name or graph_file.stem)
    title = str(document.get("title") or document.get("filename") or doc_id)
    source = str(document.get("source") or "")
    filename = str(document.get("filename") or "")

    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO documents(doc_id, title, source, filename, graph_path, markdown_path, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                title = excluded.title,
                source = excluded.source,
                filename = excluded.filename,
                graph_path = excluded.graph_path,
                markdown_path = excluded.markdown_path,
                metadata_json = excluded.metadata_json
            """,
            (
                doc_id,
                title,
                source,
                filename,
                str(graph_file),
                str(document_markdown_path or ""),
                json.dumps(document, ensure_ascii=False),
            ),
        )

        conn.execute("DELETE FROM nodes WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))

        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        for node in nodes:
            properties = dict(node.get("properties") or {})
            display_name = _node_display_name(node)
            conn.execute(
                """
                INSERT INTO nodes(node_id, doc_id, type, level, display_name, properties_json, search_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    doc_id = excluded.doc_id,
                    type = excluded.type,
                    level = excluded.level,
                    display_name = excluded.display_name,
                    properties_json = excluded.properties_json,
                    search_text = excluded.search_text
                """,
                (
                    node["id"],
                    doc_id,
                    node.get("type", ""),
                    node.get("level", ""),
                    display_name,
                    json.dumps(properties, ensure_ascii=False),
                    _build_node_search_text(node),
                ),
            )

        conn.execute("DELETE FROM edges WHERE doc_id = ?", (doc_id,))
        for index, edge in enumerate(edges):
            edge_id = f"{doc_id}:{index}:{edge['source']}:{edge['relation']}:{edge['target']}"
            conn.execute(
                """
                INSERT OR REPLACE INTO edges(edge_id, doc_id, source_id, relation, target_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (edge_id, doc_id, edge["source"], edge["relation"], edge["target"]),
            )

        chunk_count = 0
        if document_markdown_path:
            markdown_file = Path(document_markdown_path)
            if markdown_file.exists():
                for chunk_index, chunk_text in enumerate(_chunk_markdown(markdown_file.read_text(encoding="utf-8"))):
                    conn.execute(
                        """
                        INSERT INTO chunks(doc_id, chunk_index, text, source_path)
                        VALUES (?, ?, ?, ?)
                        """,
                        (doc_id, chunk_index, chunk_text, str(markdown_file)),
                    )
                    chunk_count += 1

    return {
        "db_path": str(db_file),
        "doc_id": doc_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "chunk_count": chunk_count,
        "status": "indexed",
    }


def search_knowledge_graph(
    query: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 5,
    hops: int = 1,
) -> dict[str, Any]:
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(db_file)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        node_hits = _search_nodes(conn, query=query, limit=limit)
        chunk_hits = _search_chunks(conn, query=query, limit=limit)
        seed_node_ids = [row["node_id"] for row in node_hits]
        subgraph = _expand_subgraph(conn, seed_node_ids=seed_node_ids, hops=hops)

    return {
        "query": query,
        "nodes": [dict(row) for row in node_hits],
        "chunks": [dict(row) for row in chunk_hits],
        "subgraph": subgraph,
    }


def _initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source TEXT,
            filename TEXT,
            graph_path TEXT,
            markdown_path TEXT,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            type TEXT NOT NULL,
            level TEXT,
            display_name TEXT,
            properties_json TEXT NOT NULL,
            search_text TEXT NOT NULL,
            FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS edges (
            edge_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            target_id TEXT NOT NULL,
            FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            source_path TEXT,
            FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_nodes_doc_id ON nodes(doc_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
        """
    )


def _search_nodes(conn: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    pattern = f"%{query}%"
    return conn.execute(
        """
        SELECT node_id, doc_id, type, level, display_name, properties_json
        FROM nodes
        WHERE search_text LIKE ? OR display_name LIKE ? OR type LIKE ?
        ORDER BY
            CASE
                WHEN display_name = ? THEN 0
                WHEN display_name LIKE ? THEN 1
                ELSE 2
            END,
            type,
            display_name
        LIMIT ?
        """,
        (pattern, pattern, pattern, query, pattern, limit),
    ).fetchall()


def _search_chunks(conn: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    pattern = f"%{query}%"
    return conn.execute(
        """
        SELECT chunk_id, doc_id, chunk_index, text, source_path
        FROM chunks
        WHERE text LIKE ?
        ORDER BY chunk_index
        LIMIT ?
        """,
        (pattern, limit),
    ).fetchall()


def _expand_subgraph(conn: sqlite3.Connection, seed_node_ids: list[str], hops: int) -> dict[str, Any]:
    if not seed_node_ids:
        return {"nodes": [], "edges": []}

    visited = set(seed_node_ids)
    frontier = set(seed_node_ids)
    collected_edges: dict[str, sqlite3.Row] = {}

    for _ in range(max(hops, 0)):
        if not frontier:
            break
        placeholders = ",".join("?" for _ in frontier)
        rows = conn.execute(
            f"""
            SELECT edge_id, doc_id, source_id, relation, target_id
            FROM edges
            WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})
            """,
            tuple(frontier) + tuple(frontier),
        ).fetchall()
        next_frontier: set[str] = set()
        for row in rows:
            collected_edges[row["edge_id"]] = row
            for node_id in (row["source_id"], row["target_id"]):
                if node_id not in visited:
                    visited.add(node_id)
                    next_frontier.add(node_id)
        frontier = next_frontier

    placeholders = ",".join("?" for _ in visited)
    node_rows = conn.execute(
        f"""
        SELECT node_id, doc_id, type, level, display_name, properties_json
        FROM nodes
        WHERE node_id IN ({placeholders})
        ORDER BY type, display_name
        """,
        tuple(visited),
    ).fetchall()

    return {
        "nodes": [dict(row) for row in node_rows],
        "edges": [dict(row) for row in collected_edges.values()],
    }


def _node_display_name(node: dict[str, Any]) -> str:
    properties = node.get("properties") or {}
    return str(
        properties.get("display_name")
        or properties.get("original_name")
        or properties.get("name")
        or properties.get("value")
        or node.get("id", "")
    )


def _build_node_search_text(node: dict[str, Any]) -> str:
    properties = node.get("properties") or {}
    values = [node.get("id", ""), node.get("type", ""), node.get("level", ""), _node_display_name(node)]
    values.extend(str(value) for value in properties.values() if isinstance(value, (str, int, float)))
    return " ".join(value for value in values if value)


def _chunk_markdown(text: str, max_chars: int = 1200) -> list[str]:
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    chunks: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = block
    if current:
        chunks.append(current)
    return chunks
