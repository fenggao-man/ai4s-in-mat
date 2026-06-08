"""
配方生成器共享配置 — 所有配置项从 .env / 环境变量读取，无硬编码。

用法:
    from scr.knowledge_graph.recipe_config import load_recipe_config
    cfg = load_recipe_config()
    neo4j_cypher("MATCH (n) RETURN n", cfg=cfg)
"""

from __future__ import annotations
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


def load_env_file(env_file: str | Path = DEFAULT_ENV_FILE) -> None:
    """Load .env into os.environ (idempotent)."""
    path = Path(env_file)
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8")
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ.setdefault(key, value)


class RecipeConfig:
    """配方生成器运行配置，全部从环境变量读取。"""

    def __init__(self) -> None:
        load_env_file()

        # ── Neo4j ──
        self.neo4j_http_url: str = os.environ.get(
            "NEO4J_HTTP_URL",
            "http://192.168.66.148:7474/db/neo4j/tx/commit"
        )
        self.neo4j_user: str = os.environ.get("NEO4J_USER", "neo4j")
        self.neo4j_password: str = os.environ.get("NEO4J_PASSWORD", "")
        self.neo4j_auth: str = f"{self.neo4j_user}:{self.neo4j_password}"

        # ── LLM ──
        self.llm_api_url: str = os.environ.get("KG_LLM_API_URL", "")
        self.llm_api_key: str = os.environ.get("KG_LLM_API_KEY", "")
        self.llm_model: str = os.environ.get("KG_LLM_MODEL", "deepseek-chat")
        self.llm_timeout: int = int(os.environ.get("KG_LLM_TIMEOUT", "900"))

        # ── Web Search ──
        self.web_search_backend: str = os.environ.get("WEB_SEARCH_BACKEND", "none")
        self.web_search_api_url: str = os.environ.get("WEB_SEARCH_API_URL", "")
        self.web_search_api_key: str = os.environ.get("WEB_SEARCH_API_KEY", "")

        # ── Paths ──
        _desktop = Path.home() / "Desktop"
        self.output_dir: Path = Path(
            os.environ.get("RECIPE_OUTPUT_DIR") or str(_desktop)
        )
        self.paper_index_path: Path = Path(
            os.environ.get("RECIPE_PAPER_INDEX_PATH") or str(_desktop / "paper_index.json")
        )

        # ── Retrieval ──
        self.rag_top_n: int = int(os.environ.get("RECIPE_RAG_TOP_N", "10"))

    def as_dict(self) -> dict:
        return {
            "neo4j_http_url": self.neo4j_http_url,
            "neo4j_user": self.neo4j_user,
            "llm_model": self.llm_model,
            "web_search_backend": self.web_search_backend,
            "output_dir": str(self.output_dir),
            "paper_index_path": str(self.paper_index_path),
            "rag_top_n": self.rag_top_n,
        }


# Singleton
_config: RecipeConfig | None = None


def load_recipe_config() -> RecipeConfig:
    """获取配置单例（首次调用从 .env 加载）。"""
    global _config
    if _config is None:
        _config = RecipeConfig()
    return _config
