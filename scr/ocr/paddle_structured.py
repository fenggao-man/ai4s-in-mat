from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .paddle_api import PaddleOCRAPIClient, _build_run_output_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEST_ENV_FILE = PROJECT_ROOT / ".env"
TEST_FILE_PATH = PROJECT_ROOT / "Data" / "助剂对Ru:CeO2催化剂的表面性质及氨合成性能的影响.pdf"
TEST_OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "ocr"
TEST_TIMEOUT = 180
TEST_VERBOSE = True
TEST_OPTIONAL_PAYLOAD: dict[str, Any] | None = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": True,
}


def recognize_to_structured_markdown(
    file_path: str | Path,
    env_file: str | Path | None = None,
    output_root: str | Path | None = None,
    timeout: int = 180,
    optional_payload: dict[str, Any] | None = None,
    verbose: bool = False,
) -> Path:
    artifacts_root = Path(output_root) if output_root else TEST_OUTPUT_ROOT
    client = PaddleOCRAPIClient.from_env(env_file=env_file, timeout=timeout)
    run_dir, output_md_path, raw_response_path, assets_dir = _build_run_output_paths(
        file_path=file_path,
        artifacts_root=artifacts_root,
    )

    data = client.recognize(
        file_path=file_path,
        optional_payload=optional_payload,
        verbose=verbose,
    )
    client.write_ocr_outputs(
        data=data,
        output_dir=assets_dir,
        output_md_path=output_md_path,
        download_assets=True,
        verbose=verbose,
    )
    raw_response_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    structured_md_path = run_dir / "document_structured.md"
    structured_text = build_structured_markdown(data=data)
    structured_md_path.write_text(structured_text, encoding="utf-8")

    image_index_path = run_dir / "image_index.json"
    image_index_path.write_text(
        json.dumps(_build_image_index(data=data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if verbose:
        print(f"Saved raw response: {raw_response_path}")
        print(f"Saved structured markdown: {structured_md_path}")
        print(f"Saved image index: {image_index_path}")
        print(f"Run directory: {run_dir}")

    return structured_md_path


def build_structured_markdown(data: dict[str, Any]) -> str:
    pages = ((data.get("result") or {}).get("layoutParsingResults")) or []
    sections: list[str] = []
    appendix_blocks: list[str] = []

    for page in pages:
        page_text = ((page.get("markdown") or {}).get("text")) or ""
        page_body = _annotate_page_markdown(page_text)
        image_entries = _collect_page_images(page)
        parsed_blocks = _collect_structured_blocks(page)

        if page_body.strip():
            sections.append(page_body.strip())
            sections.append("")

        if image_entries:
            sections.append("## PAGE_IMAGES")
            sections.append("")
            for image_path in image_entries:
                sections.append(f"- {image_path}")
            sections.append("")

        if parsed_blocks:
            if not appendix_blocks:
                appendix_blocks.append("## 图表结构化信息")
                appendix_blocks.append("")
            for block in parsed_blocks:
                appendix_blocks.extend(_render_structured_block(block))
                appendix_blocks.append("")

    if appendix_blocks:
        sections.append("")
        sections.extend(appendix_blocks)

    return "\n".join(section for section in sections if section is not None).strip() + "\n"


def _annotate_page_markdown(page_text: str) -> str:
    lines = page_text.splitlines()
    annotated: list[str] = []

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if _is_image_line(stripped):
            image_path = _extract_image_path(stripped)
            context_before = _find_neighbor_text(lines, idx, direction=-1)
            context_after = _find_neighbor_text(lines, idx, direction=1)
            annotated.append("")
            annotated.append("### IMAGE_BLOCK")
            if image_path:
                annotated.append(f"image_path: {image_path}")
            if context_before:
                annotated.append(f"context_before: {context_before}")
            if context_after:
                annotated.append(f"context_after: {context_after}")
            annotated.append(stripped)
            continue

        annotated.append(line)

    return "\n".join(annotated)


def _build_image_index(data: dict[str, Any]) -> list[dict[str, Any]]:
    pages = ((data.get("result") or {}).get("layoutParsingResults")) or []
    index_rows: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages, start=1):
        page_text = ((page.get("markdown") or {}).get("text")) or ""
        lines = page_text.splitlines()
        for idx, line in enumerate(lines):
            if not _is_image_line(line.strip()):
                continue
            index_rows.append(
                {
                    "page": page_index,
                    "image_path": _extract_image_path(line),
                    "context_before": _find_neighbor_text(lines, idx, direction=-1),
                    "context_after": _find_neighbor_text(lines, idx, direction=1),
                }
            )
    return index_rows


def _collect_structured_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    pruned = page.get("prunedResult") or {}
    parsing_res_list = pruned.get("parsing_res_list") if isinstance(pruned, dict) else None
    if not isinstance(parsing_res_list, list):
        return []

    blocks = []
    figure_titles = [item for item in parsing_res_list if item.get("block_label") == "figure_title"]

    for item in parsing_res_list:
        label = item.get("block_label", "")
        if label not in {"chart", "table"}:
            continue

        bbox = item.get("block_bbox") or []
        title_kind = "figure" if label == "chart" else "table"
        nearby_titles = _find_nearby_titles(
            bbox=bbox,
            figure_titles=figure_titles,
            title_kind=title_kind,
        )
        blocks.append(
            {
                "label": label,
                "bbox": bbox,
                "content": str(item.get("block_content") or "").strip(),
                "titles": nearby_titles,
            }
        )
    return blocks


def _find_nearby_titles(
    bbox: list[Any],
    figure_titles: list[dict[str, Any]],
    title_kind: str,
) -> list[str]:
    if not bbox or len(bbox) != 4:
        return []

    x1, y1, x2, y2 = bbox
    matched: list[tuple[int, float, str]] = []
    for title in figure_titles:
        title_bbox = title.get("block_bbox") or []
        if len(title_bbox) != 4:
            continue
        tx1, ty1, tx2, ty2 = title_bbox
        title_text = str(title.get("block_content") or "").strip()
        if not title_text:
            continue

        title_semantic = _classify_title_kind(title_text)
        if title_semantic != title_kind:
            continue

        horizontal_overlap = not (tx2 < x1 - 120 or tx1 > x2 + 120)
        vertical_distance = min(abs(ty2 - y1), abs(ty1 - y2))
        if horizontal_overlap and vertical_distance <= 180:
            is_above = 0 if ty2 <= y1 else 1
            matched.append((is_above, vertical_distance, title_text))

    matched.sort(key=lambda item: (item[0], item[1]))
    result: list[str] = []
    seen: set[str] = set()
    for _, _, text in matched:
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result[:2]


def _render_structured_block(block: dict[str, Any]) -> list[str]:
    content = str(block.get("content", "")).strip()
    titles = [title for title in block.get("titles", []) if title]
    lines: list[str] = []

    if titles:
        primary_title = _pick_primary_title(titles)
        secondary_titles = [title for title in titles if title != primary_title]
        cleaned_primary = _strip_html(primary_title).strip()
        lines.append(f"### {cleaned_primary}")
        for title in secondary_titles:
            cleaned = _strip_html(title).strip()
            if cleaned:
                lines.append(cleaned)
        lines.append("")

    if content:
        lines.append(content)

    return lines


def _pick_primary_title(titles: list[str]) -> str:
    for title in titles:
        cleaned = _strip_html(title).strip()
        if cleaned.startswith("图") or cleaned.startswith("表"):
            return title
    return titles[0]


def _collect_page_images(page: dict[str, Any]) -> list[str]:
    image_paths: list[str] = []
    markdown_images = ((page.get("markdown") or {}).get("images")) or {}
    for relative_path in markdown_images.keys():
        image_paths.append(str(relative_path))

    deduped: list[str] = []
    seen: set[str] = set()
    for value in image_paths:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _find_neighbor_text(lines: list[str], start_index: int, direction: int) -> str:
    index = start_index + direction
    while 0 <= index < len(lines):
        candidate = lines[index].strip()
        if candidate and not _is_image_line(candidate) and not candidate.startswith("<table") and not candidate.startswith("</table"):
            return candidate
        index += direction
    return ""


def _extract_image_path(line: str) -> str:
    match = re.search(r'src="([^"]+)"', line)
    return match.group(1) if match else ""


def _is_image_line(line: str) -> bool:
    return "<img" in line and 'src="' in line


def _is_table_caption(line: str) -> bool:
    plain = _strip_html(line).strip()
    lowered = plain.lower()
    return (
        plain.startswith("表 ")
        or plain.startswith("表")
        or lowered.startswith("table ")
    )


def _is_figure_caption(line: str) -> bool:
    plain = _strip_html(line).strip()
    lowered = plain.lower()
    return (
        plain.startswith("图 ")
        or plain.startswith("图")
        or lowered.startswith("figure ")
        or lowered.startswith("fig. ")
    )


def _classify_title_kind(text: str) -> str:
    plain = _strip_html(text).strip()
    lowered = plain.lower()
    if plain.startswith("表") or lowered.startswith("table "):
        return "table"
    if plain.startswith("图") or lowered.startswith("figure ") or lowered.startswith("fig. "):
        return "figure"
    return "unknown"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def main() -> int:
    result_path = recognize_to_structured_markdown(
        file_path=TEST_FILE_PATH,
        env_file=TEST_ENV_FILE,
        output_root=TEST_OUTPUT_ROOT,
        timeout=TEST_TIMEOUT,
        optional_payload=TEST_OPTIONAL_PAYLOAD,
        verbose=TEST_VERBOSE,
    )
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
