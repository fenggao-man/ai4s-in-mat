from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests
from requests import exceptions as requests_exceptions


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_KG_LLM_TIMEOUT = 900
THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)


def load_env_file(env_file: str | Path = DEFAULT_ENV_FILE) -> None:
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
        
        # Remove quotes if present
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
            
        os.environ[key] = value


def strip_reasoning_blocks(text: str) -> str:
    """
    Remove model reasoning blocks such as <think>...</think>.

    Some models, including DeepSeek-style reasoning models, may prepend hidden
    reasoning in the visible response. Downstream parsers expect only the final
    answer, so strip those blocks when present and leave normal responses alone.
    """
    if "<think" not in text.lower():
        return text.strip()
    return THINK_BLOCK_RE.sub("", text).strip()


def call_kg_llm_messages(
    messages: list[dict[str, str]],
    model: str | None = None,
    env_file: str | Path = DEFAULT_ENV_FILE,
    timeout: int | None = None,
    max_tokens: int = 8192,
    verbose: bool = False,
) -> str:
    """Send a multi-turn conversation to the LLM.

    Unlike call_kg_llm which wraps a single prompt in a user message,
    this sends the full message list as-is, preserving assistant turns.
    This enables CATDA-style validation loops where the model sees its
    own previous output when self-correcting.
    """
    load_env_file(env_file)

    api_url = os.environ.get("KG_LLM_API_URL", "").strip()
    api_key = os.environ.get("KG_LLM_API_KEY", "").strip()
    model_name = model or os.environ.get("KG_LLM_MODEL", "").strip()
    timeout_value = timeout or int(os.environ.get("KG_LLM_TIMEOUT", DEFAULT_KG_LLM_TIMEOUT))

    if not api_url:
        raise ValueError("KG_LLM_API_URL is required")
    if not model_name:
        raise ValueError("KG_LLM_MODEL is required")

    url = api_url
    if not url.endswith("/chat/completions"):
        if "/v1" not in url:
            url = url.rstrip("/") + "/v1/chat/completions"
        else:
            url = url.rstrip("/") + "/chat/completions"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Prepend system message if not already present
    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": "你是一位材料化学知识抽取专家。"}] + messages

    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }

    if verbose:
        msg_roles = " → ".join(m["role"] for m in messages)
        print(
            f"[llm] multi-turn request: model={model_name}, turns={len(messages)}, "
            f"flow={msg_roles}, timeout={timeout_value}s",
            flush=True,
        )

    started_at = time.perf_counter()
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout_value)
    except requests_exceptions.RequestException as exc:
        raise RuntimeError(
            "KG LLM multi-turn request failed. Check KG_LLM_API_URL and network. "
            f"api_url={url}"
        ) from exc
    response.raise_for_status()
    data = response.json()

    if verbose:
        elapsed = time.perf_counter() - started_at
        print(
            f"[llm] multi-turn response: status={response.status_code}, elapsed={elapsed:.2f}s",
            flush=True,
        )
    try:
        return strip_reasoning_blocks(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected KG LLM response: {json.dumps(data, ensure_ascii=False)[:500]}") from exc



def call_kg_llm(
    prompt: str,
    model: str | None = None,
    env_file: str | Path = DEFAULT_ENV_FILE,
    timeout: int | None = None,
    max_tokens: int = 8192,
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

    # Prepare URL and headers
    url = api_url
    if not url.endswith("/chat/completions"):
        if "/v1" not in url:
            url = url.rstrip("/") + "/v1/chat/completions"
        else:
            url = url.rstrip("/") + "/chat/completions"
    
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "你是一位材料化学知识抽取专家。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }

    if verbose:
        print(
            f"[llm] request started: model={model_name}, timeout={timeout_value}s, api={url}",
            flush=True,
        )

    started_at = time.perf_counter()
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout_value)
    except requests_exceptions.RequestException as exc:
        raise RuntimeError(
            "KG LLM request failed. Check KG_LLM_API_URL, network connectivity, DNS, and proxy settings. "
            f"api_url={url}"
        ) from exc
    response.raise_for_status()
    data = response.json()

    if verbose:
        elapsed = time.perf_counter() - started_at
        print(
            f"[llm] response received: status={response.status_code}, elapsed={elapsed:.2f}s",
            flush=True,
        )
    try:
        return strip_reasoning_blocks(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected KG LLM response: {json.dumps(data, ensure_ascii=False)[:500]}") from exc
