from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from scr.knowledge_graph import (
    align_entity_graph_from_run,
    clear_entity_graph_database,
    extract_graph_from_ocr_run,
    fuse_entity_graph_from_run,
    store_entity_graph_from_run,
)
from scr.knowledge_graph.llm_client import load_env_file
from scr.ocr.paddle_api import _slugify_filename
from scr.ocr.paddle_structured import recognize_to_structured_markdown

PROJECT_ROOT = Path(__file__).resolve().parent
OCR_ARTIFACTS_ROOT = PROJECT_ROOT / "artifacts" / "ocr"
ENV_FILE = PROJECT_ROOT / ".env"


def resolve_data_root(project_root: Path) -> Path:
    candidates = [project_root / "data", project_root / "Data"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DATA_ROOT = resolve_data_root(PROJECT_ROOT)


def find_latest_ocr_run(artifacts_root: Path, doc_slug: str) -> Path | None:
    doc_dir = artifacts_root / doc_slug
    if not doc_dir.exists():
        return None

    run_dirs = sorted(
        [path for path in doc_dir.iterdir() if path.is_dir() and path.name.startswith("run_")],
        key=lambda path: path.name,
    )
    if not run_dirs:
        return None
    return run_dirs[-1]


def _extract_host(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or ""


def _check_dns(host: str) -> str | None:
    if not host:
        return "missing host"
    try:
        socket.getaddrinfo(host, None)
        return None
    except socket.gaierror as exc:
        return str(exc)


def run_preflight_checks(verbose: bool = True) -> bool:
    issues: list[str] = []

    if not ENV_FILE.exists():
        issues.append(f".env file not found: {ENV_FILE}")

    ocr_url = os.environ.get("PADDLEOCR_VL_API_URL", "").strip()
    kg_url = os.environ.get("KG_LLM_API_URL", "").strip()

    for label, url, env_name in [
        ("OCR API", ocr_url, "PADDLEOCR_VL_API_URL"),
        ("KG LLM API", kg_url, "KG_LLM_API_URL"),
    ]:
        if not url:
            issues.append(f"{env_name} is not configured")
            continue
        host = _extract_host(url)
        dns_error = _check_dns(host)
        if dns_error:
            issues.append(f"{label} host cannot be resolved: {host} ({dns_error})")

    if not DATA_ROOT.exists():
        issues.append(f"data directory not found: {DATA_ROOT}")

    if issues:
        print("[preflight] configuration/network checks failed:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    if verbose:
        print(f"[preflight] data root: {DATA_ROOT}")
        print("[preflight] configuration/network checks passed")
    return True


def ensure_ocr_run(pdf_path: Path, verbose: bool = True) -> Path:
    doc_slug = _slugify_filename(pdf_path)
    latest_run = find_latest_ocr_run(OCR_ARTIFACTS_ROOT, doc_slug)

    if latest_run:
        if verbose:
            print(f"[ocr] found existing run for {pdf_path.name}: {latest_run.name}")
        return latest_run

    if verbose:
        print(f"[ocr] no existing run for {pdf_path.name}, running OCR...")

    # recognize_to_structured_markdown returns structured_md_path
    # which is run_dir / "document_structured.md"
    structured_md_path = recognize_to_structured_markdown(
        file_path=pdf_path,
        env_file=ENV_FILE,
        output_root=OCR_ARTIFACTS_ROOT,
        verbose=verbose,
    )
    return structured_md_path.parent


def process_document(pdf_path: Path, verbose: bool = True) -> None:
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_path.name}")
    print(f"{'='*60}")

    try:
        run_dir = ensure_ocr_run(pdf_path, verbose=verbose)

        print(f"[pipeline] starting extraction for {run_dir.name}...", flush=True)
        extract_graph_from_ocr_run(run_dir=run_dir, verbose=verbose)

        print(f"[pipeline] starting alignment...", flush=True)
        align_entity_graph_from_run(run_dir=run_dir, verbose=verbose)

        print(f"[pipeline] starting fusion...", flush=True)
        fuse_entity_graph_from_run(run_dir=run_dir, verbose=verbose)

        print(f"[pipeline] starting storage...", flush=True)
        store_entity_graph_from_run(run_dir=run_dir, verbose=verbose)

        print(f"[pipeline] successfully processed {pdf_path.name}")
    except Exception as e:
        print(f"[pipeline] failed to process {pdf_path.name}: {e}")


def main() -> None:
    # Load environment variables
    load_env_file(ENV_FILE)

    # Get all PDF files in data root
    pdf_files = sorted(list(DATA_ROOT.glob("*.pdf")))

    if not pdf_files:
        print(f"[main] no PDF files found in {DATA_ROOT}")
        return

    print(f"[main] found {len(pdf_files)} PDF files to process")

    # Optional: clear database before starting if needed
    # clear_entity_graph_database(verbose=True)

    for pdf_file in pdf_files:
        process_document(pdf_file)


if __name__ == "__main__":
    main()
