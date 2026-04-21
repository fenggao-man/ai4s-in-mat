from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_KG_LLM_TIMEOUT = 900


def load_env_file(env_file: str | Path = DEFAULT_ENV_FILE) -> None:
    path = Path(env_file)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def call_kg_llm(
    prompt: str,
    model: str | None = None,
    env_file: str | Path = DEFAULT_ENV_FILE,
    timeout: int | None = None,
    verbose: bool = False,
) -> str:
    load_env_file(env_file)

    api_url = os.environ.get("KG_LLM_API_URL", "").strip()
    api_key = os.environ.get("KG_LLM_API_KEY", "").strip()
    model_name = model or os.environ.get("KG_LLM_MODEL", "").strip()
    timeout_value = timeout or int(os.environ.get("KG_LLM_TIMEOUT", DEFAULT_KG_LLM_TIMEOUT))

    if not api_url:
        raise ValueError("KG_LLM_API_URL is required")
    if not model_name:
        raise ValueError("KG_LLM_MODEL is required")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "你是一位材料化学知识抽取专家。"},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    if verbose:
        print(
            f"[llm] request started: model={model_name}, timeout={timeout_value}s, api={api_url}",
            flush=True,
        )

    started_at = time.perf_counter()
    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout_value)
    response.raise_for_status()
    data = response.json()

    if verbose:
        elapsed = time.perf_counter() - started_at
        print(
            f"[llm] response received: status={response.status_code}, elapsed={elapsed:.2f}s",
            flush=True,
        )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected KG LLM response: {json.dumps(data, ensure_ascii=False)[:500]}") from exc
