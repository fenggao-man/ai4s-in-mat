from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from scr.knowledge_graph.sqlite_retrieval import (
    DEFAULT_DB_PATH,
    index_graph_for_retrieval,
    search_knowledge_graph,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_LIMIT = 5
DEFAULT_HOPS = 1


def index_knowledge_graph(
    graph_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    document_markdown_path: str | Path | None = None,
) -> dict:
    return index_graph_for_retrieval(
        graph_path=graph_path,
        db_path=db_path,
        document_markdown_path=document_markdown_path,
    )


def retrieve_knowledge(
    query: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = DEFAULT_OUTPUT_LIMIT,
    hops: int = DEFAULT_HOPS,
) -> dict:
    return search_knowledge_graph(
        query=query,
        db_path=db_path,
        limit=limit,
        hops=hops,
    )


def run_retrieval_command(args: argparse.Namespace) -> dict:
    if args.command == "index":
        return index_knowledge_graph(
            graph_path=args.graph_path,
            db_path=args.db_path,
            document_markdown_path=args.markdown_path,
        )
    if args.command == "search":
        return retrieve_knowledge(
            query=args.query,
            db_path=args.db_path,
            limit=args.limit,
            hops=args.hops,
        )
    raise ValueError(f"Unsupported command: {args.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SQLite knowledge retrieval MVP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Index a fused entity graph into SQLite")
    index_parser.add_argument("--graph-path", required=True, help="Path to entity_graph_fused.json")
    index_parser.add_argument("--markdown-path", default=None, help="Optional OCR document.md path")
    index_parser.add_argument("--db-path", default=str(PROJECT_ROOT / DEFAULT_DB_PATH), help="SQLite database path")

    search_parser = subparsers.add_parser("search", help="Search indexed knowledge")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--db-path", default=str(PROJECT_ROOT / DEFAULT_DB_PATH), help="SQLite database path")
    search_parser.add_argument("--limit", type=int, default=DEFAULT_OUTPUT_LIMIT, help="Maximum node/chunk hits")
    search_parser.add_argument("--hops", type=int, default=DEFAULT_HOPS, help="Neighbor expansion hops")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_retrieval_command(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
