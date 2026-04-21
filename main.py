from __future__ import annotations

from pathlib import Path

from scr.knowledge_graph import (
    align_entity_graph_from_run,
    clear_entity_graph_database,
    extract_graph_from_ocr_run,
    fuse_entity_graph_from_run,
    store_entity_graph_from_run,
)


PROJECT_ROOT = Path(__file__).resolve().parent
OCR_ARTIFACTS_ROOT = PROJECT_ROOT / "artifacts" / "ocr"

# Manual test target
CURRENT_DOC_NAME = "助剂对Ru:CeO2催化剂的表面性质及氨合成性能的影响"
CURRENT_DOC_SLUG = "助剂对Ru_CeO2催化剂的表面性质及氨合成性能的影响"

# Shared module context
CURRENT_OCR_RUN_DIR: Path | None = None
CURRENT_ENTITY_GRAPH_PATH: Path | None = None
CURRENT_ALIGNED_GRAPH_PATH: Path | None = None
CURRENT_FUSED_GRAPH_PATH: Path | None = None
CURRENT_STORAGE_REPORT_PATH: Path | None = None


def test_clear_database() -> None:
    print("[main] clearing graph database...", flush=True)
    result = clear_entity_graph_database(verbose=True)
    print(f"[entity_storage] clear result: {result}", flush=True)


def find_latest_ocr_run(artifacts_root: Path, doc_slug: str) -> Path:
    doc_dir = artifacts_root / doc_slug
    if not doc_dir.exists():
        raise FileNotFoundError(f"OCR artifact directory not found: {doc_dir}")

    run_dirs = sorted(
        [path for path in doc_dir.iterdir() if path.is_dir() and path.name.startswith("run_")],
        key=lambda path: path.name,
    )
    if not run_dirs:
        raise FileNotFoundError(f"No OCR run directories found under: {doc_dir}")
    return run_dirs[-1]


def bootstrap_context() -> None:
    global CURRENT_OCR_RUN_DIR
    CURRENT_OCR_RUN_DIR = find_latest_ocr_run(
        artifacts_root=OCR_ARTIFACTS_ROOT,
        doc_slug=CURRENT_DOC_SLUG,
    )
    print(f"[context] current document: {CURRENT_DOC_NAME}")
    print(f"[context] current ocr run: {CURRENT_OCR_RUN_DIR}")


def test_entity_extraction() -> None:
    global CURRENT_ENTITY_GRAPH_PATH
    if CURRENT_OCR_RUN_DIR is None:
        bootstrap_context()

    print("[main] starting entity extraction...", flush=True)
    CURRENT_ENTITY_GRAPH_PATH = extract_graph_from_ocr_run(
        run_dir=CURRENT_OCR_RUN_DIR,
        verbose=True,
    )
    print(f"[entity_extraction] output: {CURRENT_ENTITY_GRAPH_PATH}", flush=True)


def test_entity_alignment() -> None:
    global CURRENT_ALIGNED_GRAPH_PATH
    if CURRENT_OCR_RUN_DIR is None:
        bootstrap_context()

    print("[main] starting entity alignment...", flush=True)
    CURRENT_ALIGNED_GRAPH_PATH = align_entity_graph_from_run(
        run_dir=CURRENT_OCR_RUN_DIR,
        verbose=True,
    )
    print(f"[entity_alignment] output: {CURRENT_ALIGNED_GRAPH_PATH}", flush=True)


def test_entity_fusion() -> None:
    global CURRENT_FUSED_GRAPH_PATH
    if CURRENT_OCR_RUN_DIR is None:
        bootstrap_context()

    print("[main] starting entity fusion...", flush=True)
    CURRENT_FUSED_GRAPH_PATH = fuse_entity_graph_from_run(
        run_dir=CURRENT_OCR_RUN_DIR,
        verbose=True,
    )
    print(f"[entity_fusion] output: {CURRENT_FUSED_GRAPH_PATH}", flush=True)


def test_entity_storage() -> None:
    global CURRENT_STORAGE_REPORT_PATH
    if CURRENT_OCR_RUN_DIR is None:
        bootstrap_context()

    print("[main] starting entity storage...", flush=True)
    CURRENT_STORAGE_REPORT_PATH = store_entity_graph_from_run(
        run_dir=CURRENT_OCR_RUN_DIR,
        verbose=True,
    )
    print(f"[entity_storage] report: {CURRENT_STORAGE_REPORT_PATH}", flush=True)


def test_full_pipeline() -> None:
    if CURRENT_OCR_RUN_DIR is None:
        bootstrap_context()

    test_entity_extraction()
    test_entity_alignment()
    test_entity_fusion()
    test_entity_storage()


if __name__ == "__main__":
    bootstrap_context()

    # test_clear_database()
    test_full_pipeline()
