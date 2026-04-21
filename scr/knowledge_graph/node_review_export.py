from __future__ import annotations

import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def export_node_review_excel(json_path: str | Path, output_path: str | Path | None = None) -> Path:
    source_path = Path(json_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))

    output = Path(output_path) if output_path else source_path.with_name(source_path.stem + "_node_review.xlsx")
    document = data.get("document", {})
    nodes = data.get("nodes", [])

    summary_rows = _build_summary_rows(document=document, nodes=nodes)
    review_rows = _build_review_rows(document=document, nodes=nodes)

    _write_xlsx(
        output_path=output,
        sheets=[
            ("NodeSummary", summary_rows),
            ("NodeReview", review_rows),
        ],
    )
    return output


def _build_summary_rows(document: dict, nodes: list[dict]) -> list[list[str]]:
    counts: dict[str, list[str]] = {}
    for node in nodes:
        node_type = node.get("type", "")
        props = node.get("properties") or {}
        label = props.get("display_name") or props.get("original_name") or props.get("value") or ""
        counts.setdefault(node_type, [])
        if label:
            counts[node_type].append(str(label))

    rows = [["paper_title", "node_type", "count", "sample_values"]]
    paper_title = str(document.get("title", ""))
    for node_type in sorted(counts):
        samples = counts[node_type][:3]
        rows.append(
            [
                paper_title,
                node_type,
                str(len(counts[node_type])),
                " | ".join(samples),
            ]
        )
    return rows


def _build_review_rows(document: dict, nodes: list[dict]) -> list[list[str]]:
    rows = [[
        "paper_title",
        "node_id",
        "node_type",
        "display_name",
        "original_name",
        "value",
        "unit",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_value",
    ]]

    paper_title = str(document.get("title", ""))
    sorted_nodes = sorted(
        nodes,
        key=lambda node: (
            str(node.get("type", "")),
            str((node.get("properties") or {}).get("display_name", "")),
            str(node.get("id", "")),
        ),
    )
    for node in sorted_nodes:
        props = node.get("properties") or {}
        rows.append(
            [
                paper_title,
                str(node.get("id", "")),
                str(node.get("type", "")),
                str(props.get("display_name", "")),
                str(props.get("original_name", "")),
                str(props.get("value", "")),
                str(props.get("unit", "")),
                str(props.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _write_xlsx(output_path: Path, sheets: list[tuple[str, list[list[str]]]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml(sheets))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets)))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, (_, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(rows))


def _worksheet_xml(rows: list[list[str]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for col_index, value in enumerate(row, start=1):
            cell_ref = f"{_col_letter(col_index)}{row_index}"
            safe_value = escape(str(value))
            cells.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{safe_value}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        "</worksheet>"
    )


def _content_types_xml(sheet_count: int) -> str:
    overrides = [
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for index in range(1, sheet_count + 1):
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'{"".join(overrides)}'
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml(sheets: list[tuple[str, list[list[str]]]]) -> str:
    sheet_tags = []
    for index, (name, _) in enumerate(sheets, start=1):
        sheet_tags.append(
            f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(sheet_tags)}</sheets>'
        "</workbook>"
    )


def _workbook_rels_xml(sheet_count: int) -> str:
    rels = []
    for index in range(1, sheet_count + 1):
        rels.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    rels.append(
        f'<Relationship Id="rId{sheet_count + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(rels)}'
        "</Relationships>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="1"><xf xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def _col_letter(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result
