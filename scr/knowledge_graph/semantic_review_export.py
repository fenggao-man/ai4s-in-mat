from __future__ import annotations

import json
from pathlib import Path

from .node_review_export import _write_xlsx


def export_semantic_review_excel(
    json_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    source_path = Path(json_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))

    output = Path(output_path) if output_path else source_path.with_name(source_path.stem + "_semantic_review.xlsx")
    document = data.get("document", {})

    # 针对催化剂数据进行精简导出（3个核心页签 -> 恢复详细视角）
    if "catalyst_inventory" in data or "catalyst_assertions" in data:
        catalyst_map = {
            str(catalyst.get("catalyst_id", "")): catalyst
            for catalyst in data.get("catalyst_inventory", [])
        }
        sheets = [
            ("PaperSummary", _build_paper_summary_rows_v3(document=document, data=data)),
            ("ExpertReview", _build_catalyst_combined_view(document=document, data=data)),
            ("PerformanceView", _build_catalyst_assertion_rows_by_focus(document=document, data=data, catalyst_map=catalyst_map, focus="performance")),
            ("CharacterizationView", _build_catalyst_assertion_rows_by_focus(document=document, data=data, catalyst_map=catalyst_map, focus="characterization")),
            ("MechanismView", _build_catalyst_assertion_rows_by_focus(document=document, data=data, catalyst_map=catalyst_map, focus="mechanism")),
            ("ReviewFlags", _build_review_flag_rows_v3(document=document, data=data)),
        ]
    elif "sample_inventory" in data or "sample_assertions" in data:
        sample_map = {
            str(sample.get("sample_id", "")): sample
            for sample in data.get("sample_inventory", [])
        }
        sheets = [
            ("PaperSummary", _build_paper_summary_rows_v2(document=document, data=data)),
            ("ExpertReview", _build_sample_overview_rows(document=document, data=data)),
            ("PerformanceView", _build_assertion_rows_by_focus(document=document, data=data, sample_map=sample_map, focus="performance")),
            ("CharacterizationView", _build_assertion_rows_by_focus(document=document, data=data, sample_map=sample_map, focus="characterization")),
            ("MechanismView", _build_assertion_rows_by_focus(document=document, data=data, sample_map=sample_map, focus="mechanism")),
            ("ReviewFlags", _build_review_flag_rows_v2(document=document, data=data)),
        ]
    else:
        nodes = data.get("nodes", [])
        sheets = [
            ("PaperSummary", _build_paper_summary_rows(document=document)),
            ("ExpertReview", _build_catalyst_sample_rows(document=document, nodes=nodes)),
        ]

    _write_xlsx(output_path=output, sheets=sheets)
    return output


def export_expert_review_excel(
    json_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    source_path = Path(json_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    output = Path(output_path) if output_path else source_path.with_name(source_path.stem + "_expert_review.xlsx")
    document = data.get("document", {})

    # 检查是否存在催化剂相关数据
    if "catalyst_inventory" in data or "catalyst_assertions" in data:
        catalyst_map = {
            str(catalyst.get("catalyst_id", "")): catalyst
            for catalyst in data.get("catalyst_inventory", [])
        }

        sheets = [
            ("PaperSummary", _build_paper_summary_rows_expert_v2(document=document, data=data)),
            ("CatalystOverview", _build_catalyst_overview_rows(document=document, data=data)),
            ("PerformanceView", _build_catalyst_assertion_rows_by_focus(document=document, data=data, catalyst_map=catalyst_map, focus="performance")),
            ("CharacterizationView", _build_catalyst_assertion_rows_by_focus(document=document, data=data, catalyst_map=catalyst_map, focus="characterization")),
            ("MechanismView", _build_catalyst_assertion_rows_by_focus(document=document, data=data, catalyst_map=catalyst_map, focus="mechanism")),
            ("ReviewFlags", _build_review_flag_rows_v3(document=document, data=data)),
            ("OntologyView", _build_ontology_view_rows_v2(document=document, data=data, catalyst_map=catalyst_map)),
        ]
    else:
        sample_map = {
            str(sample.get("sample_id", "")): sample
            for sample in data.get("sample_inventory", [])
        }

        sheets = [
            ("PaperSummary", _build_paper_summary_rows_expert(document=document, data=data)),
            ("SampleOverview", _build_sample_overview_rows(document=document, data=data)),
            ("PerformanceView", _build_assertion_rows_by_focus(document=document, data=data, sample_map=sample_map, focus="performance")),
            ("CharacterizationView", _build_assertion_rows_by_focus(document=document, data=data, sample_map=sample_map, focus="characterization")),
            ("MechanismView", _build_assertion_rows_by_focus(document=document, data=data, sample_map=sample_map, focus="mechanism")),
            ("ReviewFlags", _build_review_flag_rows_v2(document=document, data=data)),
            ("OntologyView", _build_ontology_view_rows(document=document, data=data, sample_map=sample_map)),
        ]
    _write_xlsx(output_path=output, sheets=sheets)
    return output


def _build_paper_summary_rows(document: dict) -> list[list[str]]:
    return [
        ["field", "value", "expert_note"],
        ["paper_title", str(document.get("title", "")), ""],
        ["source", str(document.get("source", "")), ""],
        ["filename", str(document.get("filename", "")), ""],
        ["review_goal", "判断抽取结果是否准确表达论文中的样品、表征、性能和机理信息", ""],
        ["how_to_review", "优先按样品查看是否抽全，再看表征/性能/机理是否与样品绑定正确", ""],
    ]


def _build_paper_summary_rows_v2(document: dict, data: dict) -> list[list[str]]:
    return [
        ["field", "value", "expert_note"],
        ["paper_title", str(document.get("title", "")), ""],
        ["source", str(document.get("source", "")), ""],
        ["filename", str(document.get("filename", "")), ""],
        ["sample_count", str(len(data.get("sample_inventory", []))), ""],
        ["assertion_count", str(len(data.get("sample_assertions", []))), ""],
        ["review_flag_count", str(len(data.get("review_flags", []))), ""],
        ["figure_assertion_count", str(len(data.get("figure_assertions", []))), ""],
        ["review_goal", "先核对样品身份，再逐条审核样品断言，最后集中处理 review flags", ""],
        ["how_to_review", "优先查看 Samples 与 Assertions 的 sample_id/sample_refs 是否一致，再审 evidence 与 corrected_record", ""],
    ]


def _build_paper_summary_rows_expert(document: dict, data: dict) -> list[list[str]]:
    return [
        ["field", "value", "expert_note"],
        ["paper_title", str(document.get("title", "")), ""],
        ["source", str(document.get("source", "")), ""],
        ["filename", str(document.get("filename", "")), ""],
        ["sample_count", str(len(data.get("sample_inventory", []))), ""],
        ["performance_item_count", str(_count_assertions_by_focus(data=data, focus="performance")), ""],
        ["characterization_item_count", str(_count_assertions_by_focus(data=data, focus="characterization")), ""],
        ["mechanism_item_count", str(_count_assertions_by_focus(data=data, focus="mechanism")), ""],
        ["review_flag_count", str(len(data.get("review_flags", []))), ""],
        ["review_goal", "按样品、性能、表征、机理和疑点五个视角审核论文抽取结果", ""],
        ["how_to_review", "先看样品是否找全，再看性能是否可信，随后核对表征和机理，最后处理复核问题", ""],
    ]


def _build_catalyst_sample_rows(document: dict, nodes: list[dict]) -> list[list[str]]:
    rows = [[
        "paper_title",
        "sample_node_id",
        "sample_name",
        "sample_evidence",
        "active_component",
        "promoters",
        "promoter_contents",
        "precursor_or_support",
        "preparation_route",
        "reaction_conditions",
        "catalytic_performance",
        "characterization_summary",
        "mechanism_summary",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]

    paper_title = str(document.get("title", ""))
    catalyst_nodes = _sorted_nodes_by_type(nodes=nodes, node_type="催化剂")

    if not catalyst_nodes:
        rows.append(
            [
                paper_title,
                "",
                "<样品名>",
                "<支持该样品存在的原文短句>",
                "<活性组分>",
                "<助剂/单助剂/多助剂>",
                "<助剂含量>",
                "<前驱体或载体>",
                "<制备方法，如共沉淀+浸渍>",
                "<如 400 °C / 10 MPa / 10000 h⁻¹ / H₂:N₂=3:1>",
                "<如氨浓度/活性/稳定性>",
                "<如XRD、BET及对应结论>",
                "<如解离/缔合>",
                "",
                "",
                "",
            ]
        )
        return rows

    for node in catalyst_nodes:
        props = node.get("properties") or {}
        rows.append(
            [
                paper_title,
                str(node.get("id", "")),
                str(props.get("display_name", "")),
                str(props.get("evidence_text", "")),
                "<待补：活性组分>",
                "<待补：助剂>",
                "<待补：助剂含量>",
                "<待补：前驱体/载体>",
                "<待补：制备方式>",
                "<待补：反应条件>",
                "<待补：催化性能>",
                "<待补：表征结论>",
                "<待补：机理结论>",
                "",
                "",
                "",
            ]
        )
    return rows


def _build_sample_rows_v2(document: dict, samples: list[dict]) -> list[list[str]]:
    rows = [[
        "paper_title",
        "sample_id",
        "display_name",
        "original_names",
        "sample_category",
        "promoters",
        "promoter_contents",
        "sample_key_components",
        "sample_identity_evidence",
        "evidence_anchor",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))

    for sample in samples:
        rows.append(
            [
                paper_title,
                str(sample.get("sample_id", "")),
                str(sample.get("display_name", "")),
                _join_list(sample.get("original_names")),
                str(sample.get("sample_category", "")),
                _join_list(sample.get("promoters")),
                _join_list(sample.get("promoter_contents")),
                _join_list(sample.get("sample_key_components")),
                str(sample.get("sample_identity_evidence", "")),
                str(sample.get("evidence_anchor", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_sample_overview_rows(document: dict, data: dict) -> list[list[str]]:
    rows = [[
        "paper_title",
        "sample_id",
        "sample_name",
        "sample_category",
        "promoters",
        "promoter_contents",
        "key_components",
        "preparation_summary",
        "test_condition_summary",
        "performance_summary",
        "characterization_summary",
        "mechanism_summary",
        "sample_identity_evidence",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    assertions = data.get("sample_assertions", [])

    for sample in data.get("sample_inventory", []):
        sample_id = str(sample.get("sample_id", ""))
        related = [item for item in assertions if sample_id in [str(ref) for ref in item.get("sample_refs", [])]]
        rows.append(
            [
                paper_title,
                sample_id,
                str(sample.get("display_name", "")),
                str(sample.get("sample_category", "")),
                _join_list(sample.get("promoters")),
                _join_list(sample.get("promoter_contents")),
                _join_list(sample.get("sample_key_components")),
                _summarize_assertions(related, focus="preparation"),
                _summarize_assertions(related, focus="reaction_condition"),
                _summarize_assertions(related, focus="performance"),
                _summarize_assertions(related, focus="characterization"),
                _summarize_assertions(related, focus="mechanism"),
                str(sample.get("sample_identity_evidence", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_characterization_rows(document: dict, nodes: list[dict]) -> list[list[str]]:
    rows = [[
        "paper_title",
        "method_node_id",
        "method_type",
        "method_name",
        "what_information_it_should_express",
        "key_result_or_conclusion",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))

    characterization_nodes = []
    for node_type in ("表征方法", "XRD", "BET", "TEM", "SEM", "XPS", "H₂-TPR", "N₂-TPD", "NH₃-TPD", "Mössbauer", "Raman", "FT-IR"):
        characterization_nodes.extend(_sorted_nodes_by_type(nodes=nodes, node_type=node_type))

    if not characterization_nodes:
        rows.append(
            [
                paper_title,
                "",
                "BET",
                "BET",
                "比表面积、孔体积、孔径分布等",
                "<关键表征结论>",
                "<原文证据>",
                "",
                "",
                "",
            ]
        )
        return rows

    for node in characterization_nodes:
        props = node.get("properties") or {}
        rows.append(
            [
                paper_title,
                str(node.get("id", "")),
                str(node.get("type", "")),
                str(props.get("display_name", "")),
                "<该方法想表达的信息类型>",
                "<该方法对应的关键结果或结论>",
                str(props.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_assertion_rows_v2(document: dict, data: dict) -> list[list[str]]:
    rows = [[
        "paper_title",
        "assertion_id",
        "sample_refs",
        "sample_names",
        "assertion_type",
        "property_name",
        "value_type",
        "property_value",
        "unit",
        "method",
        "condition_context",
        "comparison_context",
        "source_type",
        "support_level",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    sample_name_map = {
        str(sample.get("sample_id", "")): str(sample.get("display_name", ""))
        for sample in data.get("sample_inventory", [])
    }

    for assertion in data.get("sample_assertions", []):
        sample_refs = [str(item) for item in assertion.get("sample_refs", [])]
        sample_names = [sample_name_map.get(sample_id, sample_id) for sample_id in sample_refs]
        rows.append(
            [
                paper_title,
                str(assertion.get("assertion_id", "")),
                " | ".join(sample_refs),
                " | ".join(sample_names),
                str(assertion.get("assertion_type", "")),
                str(assertion.get("property_name", "")),
                str(assertion.get("value_type", "")),
                str(assertion.get("property_value", "")),
                str(assertion.get("unit", "")),
                str(assertion.get("method", "")),
                str(assertion.get("condition_context", "")),
                str(assertion.get("comparison_context", "")),
                str(assertion.get("source_type", "")),
                str(assertion.get("support_level", "")),
                str(assertion.get("evidence_anchor", "")),
                str(assertion.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_assertion_rows_by_focus(
    document: dict,
    data: dict,
    sample_map: dict[str, dict],
    focus: str,
) -> list[list[str]]:
    rows = [[
        "paper_title",
        "assertion_id",
        "sample_refs",
        "sample_names",
        "property_name",
        "property_value",
        "unit",
        "method",
        "condition_context",
        "comparison_context",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))

    for assertion in data.get("sample_assertions", []):
        assertion_type = str(assertion.get("assertion_type", ""))
        if assertion_type != focus:
            continue

        refs = [str(item) for item in assertion.get("sample_refs", [])]
        rows.append(
            [
                paper_title,
                str(assertion.get("assertion_id", "")),
                " | ".join(refs),
                " | ".join(str(sample_map.get(ref, {}).get("display_name", ref)) for ref in refs),
                str(assertion.get("property_name", "")),
                str(assertion.get("property_value", "")),
                str(assertion.get("unit", "")),
                str(assertion.get("method", "")),
                str(assertion.get("condition_context", "")),
                str(assertion.get("comparison_context", "")),
                str(assertion.get("evidence_anchor", "")),
                str(assertion.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_mechanism_rows(document: dict, nodes: list[dict]) -> list[list[str]]:
    rows = [[
        "paper_title",
        "mechanism_node_id",
        "mechanism_type",
        "mechanism_name",
        "bound_sample_or_system",
        "conclusion",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))

    mechanism_nodes = []
    for node_type in ("反应机理", "解离吸附", "缔合吸附", "加氢步骤", "脱附机理", "活性位模型", "速率控制步骤", "活化能", "反应级数", "吸附热", "指前因子", "动力学参数"):
        mechanism_nodes.extend(_sorted_nodes_by_type(nodes=nodes, node_type=node_type))

    if not mechanism_nodes:
        rows.append(
            [
                paper_title,
                "",
                "反应机理",
                "<如解离吸附/缔合吸附>",
                "<样品或体系>",
                "<机理结论>",
                "<原文证据>",
                "",
                "",
                "",
            ]
        )
        return rows

    for node in mechanism_nodes:
        props = node.get("properties") or {}
        rows.append(
            [
                paper_title,
                str(node.get("id", "")),
                str(node.get("type", "")),
                str(props.get("display_name", "")),
                "<待补：对应样品或体系>",
                "<待补：机理结论>",
                str(props.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_review_flag_rows_v2(document: dict, data: dict) -> list[list[str]]:
    rows = [[
        "paper_title",
        "flag_id",
        "related_sample_refs",
        "related_sample_names",
        "issue_type",
        "issue",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    sample_name_map = {
        str(sample.get("sample_id", "")): str(sample.get("display_name", ""))
        for sample in data.get("sample_inventory", [])
    }

    for flag in data.get("review_flags", []):
        refs = [str(item) for item in flag.get("related_sample_refs", [])]
        rows.append(
            [
                paper_title,
                str(flag.get("flag_id", "")),
                " | ".join(refs),
                " | ".join(sample_name_map.get(sample_id, sample_id) for sample_id in refs),
                str(flag.get("issue_type", "")),
                str(flag.get("issue", "")),
                str(flag.get("evidence_anchor", "")),
                str(flag.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_figure_rows_v2(document: dict, data: dict) -> list[list[str]]:
    rows = [[
        "paper_title",
        "figure_assertion_id",
        "figure_id",
        "sample_refs",
        "sample_names",
        "figure_type",
        "visual_information",
        "conclusion",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    sample_name_map = {
        str(sample.get("sample_id", "")): str(sample.get("display_name", ""))
        for sample in data.get("sample_inventory", [])
    }

    for figure_assertion in data.get("figure_assertions", []):
        refs = [str(item) for item in figure_assertion.get("sample_refs", [])]
        rows.append(
            [
                paper_title,
                str(figure_assertion.get("figure_assertion_id", "")),
                str(figure_assertion.get("figure_id", "")),
                " | ".join(refs),
                " | ".join(sample_name_map.get(sample_id, sample_id) for sample_id in refs),
                str(figure_assertion.get("figure_type", "")),
                str(figure_assertion.get("visual_information", "")),
                str(figure_assertion.get("conclusion", "")),
                str(figure_assertion.get("evidence_anchor", "")),
                str(figure_assertion.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_ontology_view_rows(document: dict, data: dict, sample_map: dict[str, dict]) -> list[list[str]]:
    rows = [[
        "paper_title",
        "sample_id",
        "sample_name",
        "ontology_category",
        "ontology_field",
        "value",
        "unit",
        "method_or_source",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))

    category_by_assertion_type = {
        "composition": "催化剂",
        "preparation": "制备工艺",
        "reaction_condition": "反应条件",
        "performance": "催化性能",
        "characterization": "表征方法",
        "mechanism": "反应机理",
        "comparison": "催化性能",
    }
    field_aliases = {
        "Ru precursor": "前驱体",
        "preparation route": "混合方式",
        "Ru loading basis": "活性组分",
        "ammonia synthesis test pressure": "压力",
        "ammonia synthesis feed ratio": "进料组成",
        "catalyst amount per test": "反应物质",
        "NH3 concentration at 400 °C": "氨浓度",
        "NH3 concentration at 425 °C": "氨浓度",
        "TOF at 400 °C": "转化率",
        "TOF at 425 °C": "转化率",
        "BET surface area": "比表面积",
        "pore volume": "孔结构",
        "pore size": "粒径",
        "particle size": "粒径",
        "actual CeO₂ content": "载体",
        "actual RuO₂ content": "活性组分",
        "Ru dispersion": "活性位",
        "2θ of CeO₂ (111)": "晶相结构",
        "lattice constant": "晶相结构",
        "dominant catalytic factor": "活性位模型",
        "F promoter role": "解离机理",
    }

    existing_fields_by_sample: dict[str, set[str]] = {}

    for sample in data.get("sample_inventory", []):
        sample_id = str(sample.get("sample_id", ""))
        sample_name = str(sample.get("display_name", ""))
        existing_fields_by_sample.setdefault(sample_id, set())

        rows.append(
            [
                paper_title,
                sample_id,
                sample_name,
                "催化剂",
                "活性组分",
                _join_list([item for item in sample.get("sample_key_components", []) if item == "Ru"]),
                "",
                "sample_inventory",
                str(sample.get("evidence_anchor", "")),
                str(sample.get("sample_identity_evidence", "")),
                "",
                "",
                "",
            ]
        )
        existing_fields_by_sample[sample_id].add("活性组分")
        rows.append(
            [
                paper_title,
                sample_id,
                sample_name,
                "催化剂",
                "助剂类型",
                _join_list(sample.get("promoters")),
                "",
                "sample_inventory",
                str(sample.get("evidence_anchor", "")),
                str(sample.get("sample_identity_evidence", "")),
                "",
                "",
                "",
            ]
        )
        existing_fields_by_sample[sample_id].add("助剂类型")
        rows.append(
            [
                paper_title,
                sample_id,
                sample_name,
                "助剂",
                "添加方式",
                _join_list(sample.get("promoter_contents")),
                "",
                "sample_inventory",
                str(sample.get("evidence_anchor", "")),
                str(sample.get("sample_identity_evidence", "")),
                "",
                "",
                "",
            ]
        )
        existing_fields_by_sample[sample_id].add("添加方式")

    for assertion in data.get("sample_assertions", []):
        refs = [str(item) for item in assertion.get("sample_refs", [])]
        if not refs:
            continue
        property_name = str(assertion.get("property_name", ""))
        ontology_field = field_aliases.get(property_name, property_name)
        ontology_category = category_by_assertion_type.get(str(assertion.get("assertion_type", "")), "催化剂")
        for sample_id in refs:
            sample_name = str(sample_map.get(sample_id, {}).get("display_name", sample_id))
            existing_fields_by_sample.setdefault(sample_id, set()).add(ontology_field)
            rows.append(
                [
                    paper_title,
                    sample_id,
                    sample_name,
                    ontology_category,
                    ontology_field,
                    str(assertion.get("property_value", "")),
                    str(assertion.get("unit", "")),
                    str(assertion.get("method", "") or assertion.get("source_type", "")),
                    str(assertion.get("evidence_anchor", "")),
                    str(assertion.get("evidence_text", "")),
                    "",
                    "",
                    "",
                ]
            )

    required_placeholder_fields = [
        ("催化剂", "前驱体"),
        ("催化剂", "晶相结构"),
    ]
    for sample in data.get("sample_inventory", []):
        sample_id = str(sample.get("sample_id", ""))
        sample_name = str(sample.get("display_name", ""))
        existing = existing_fields_by_sample.get(sample_id, set())
        for category, field_name in required_placeholder_fields:
            if field_name in existing:
                continue
            rows.append(
                [
                    paper_title,
                    sample_id,
                    sample_name,
                    category,
                    field_name,
                    "",
                    "",
                    "pending_review",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
    return rows


def _build_paper_summary_rows_expert_v2(document: dict, data: dict) -> list[list[str]]:
    return [
        ["field", "value", "expert_note"],
        ["paper_title", str(document.get("title", "")), ""],
        ["source", str(document.get("source", "")), ""],
        ["filename", str(document.get("filename", "")), ""],
        ["catalyst_count", str(len(data.get("catalyst_inventory", []))), ""],
        ["performance_item_count", str(_count_catalyst_assertions_by_focus(data=data, focus="performance")), ""],
        ["characterization_item_count", str(_count_catalyst_assertions_by_focus(data=data, focus="characterization")), ""],
        ["mechanism_item_count", str(_count_catalyst_assertions_by_focus(data=data, focus="mechanism")), ""],
        ["review_flag_count", str(len(data.get("review_flags", []))), ""],
        ["review_goal", "按催化剂、性能、表征、机理和疑点五个视角审核论文抽取结果", ""],
        ["how_to_review", "先看催化剂是否找全，再看性能是否可信，随后核对表征和机理，最后处理复核问题", ""],
    ]


def _build_catalyst_overview_rows(document: dict, data: dict) -> list[list[str]]:
    rows = [[
        "paper_title",
        "catalyst_id",
        "catalyst_name",
        "catalyst_category",
        "promoters",
        "promoter_contents",
        "key_components",
        "preparation_summary",
        "test_condition_summary",
        "performance_summary",
        "characterization_summary",
        "mechanism_summary",
        "catalyst_identity_evidence",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    assertions = data.get("catalyst_assertions", [])

    for catalyst in data.get("catalyst_inventory", []):
        catalyst_id = str(catalyst.get("catalyst_id", ""))
        related = [item for item in assertions if catalyst_id in [str(ref) for ref in item.get("catalyst_refs", [])]]
        rows.append(
            [
                paper_title,
                catalyst_id,
                str(catalyst.get("display_name", "")),
                str(catalyst.get("catalyst_category", "")),
                _join_list(catalyst.get("promoters")),
                _join_list(catalyst.get("promoter_contents")),
                _join_list(catalyst.get("catalyst_key_components")),
                _summarize_catalyst_assertions(related, focus="preparation"),
                _summarize_catalyst_assertions(related, focus="reaction_condition"),
                _summarize_catalyst_assertions(related, focus="performance"),
                _summarize_catalyst_assertions(related, focus="characterization"),
                _summarize_catalyst_assertions(related, focus="mechanism"),
                str(catalyst.get("catalyst_identity_evidence", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_catalyst_assertion_rows_by_focus(
    document: dict,
    data: dict,
    catalyst_map: dict[str, dict],
    focus: str,
) -> list[list[str]]:
    rows = [[
        "paper_title",
        "assertion_id",
        "catalyst_refs",
        "catalyst_names",
        "property_name",
        "property_value",
        "unit",
        "method",
        "condition_context",
        "comparison_context",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))

    for assertion in data.get("catalyst_assertions", []):
        assertion_type = str(assertion.get("assertion_type", ""))
        if assertion_type != focus:
            continue

        refs = [str(item) for item in assertion.get("catalyst_refs", [])]
        rows.append(
            [
                paper_title,
                str(assertion.get("assertion_id", "")),
                " | ".join(refs),
                " | ".join(str(catalyst_map.get(ref, {}).get("display_name", ref)) for ref in refs),
                str(assertion.get("property_name", "")),
                str(assertion.get("property_value", "")),
                str(assertion.get("unit", "")),
                str(assertion.get("method", "")),
                str(assertion.get("condition_context", "")),
                str(assertion.get("comparison_context", "")),
                str(assertion.get("evidence_anchor", "")),
                str(assertion.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_ontology_view_rows_v2(document: dict, data: dict, catalyst_map: dict[str, dict]) -> list[list[str]]:
    rows = [[
        "paper_title",
        "catalyst_id",
        "catalyst_name",
        "ontology_category",
        "ontology_field",
        "value",
        "unit",
        "method_or_source",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))

    category_by_assertion_type = {
        "composition": "催化剂",
        "preparation": "制备工艺",
        "reaction_condition": "反应条件",
        "performance": "催化性能",
        "characterization": "表征方法",
        "mechanism": "反应机理",
        "comparison": "催化性能",
    }
    field_aliases = {
        "Ru precursor": "前驱体",
        "preparation route": "混合方式",
        "Ru loading basis": "活性组分",
        "ammonia synthesis test pressure": "压力",
        "ammonia synthesis feed ratio": "进料组成",
        "catalyst amount per test": "反应物质",
        "NH3 concentration at 400 °C": "氨浓度",
        "NH3 concentration at 425 °C": "氨浓度",
        "TOF at 400 °C": "转化率",
        "TOF at 425 °C": "转化率",
        "BET surface area": "比表面积",
        "pore volume": "孔结构",
        "pore size": "粒径",
        "particle size": "粒径",
        "actual CeO₂ content": "载体",
        "actual RuO₂ content": "活性组分",
        "Ru dispersion": "活性位",
        "2θ of CeO₂ (111)": "晶相结构",
        "lattice constant": "晶相结构",
        "dominant catalytic factor": "活性位模型",
        "F promoter role": "解离机理",
    }

    existing_fields_by_catalyst: dict[str, set[str]] = {}

    for catalyst in data.get("catalyst_inventory", []):
        catalyst_id = str(catalyst.get("catalyst_id", ""))
        catalyst_name = str(catalyst.get("display_name", ""))
        existing_fields_by_catalyst.setdefault(catalyst_id, set())

        rows.append(
            [
                paper_title,
                catalyst_id,
                catalyst_name,
                "催化剂",
                "活性组分",
                _join_list([item for item in catalyst.get("catalyst_key_components", []) if item == "Ru"]),
                "",
                "catalyst_inventory",
                str(catalyst.get("evidence_anchor", "")),
                str(catalyst.get("catalyst_identity_evidence", "")),
                "",
                "",
                "",
            ]
        )
        existing_fields_by_catalyst[catalyst_id].add("活性组分")
        rows.append(
            [
                paper_title,
                catalyst_id,
                catalyst_name,
                "催化剂",
                "助剂类型",
                _join_list(catalyst.get("promoters")),
                "",
                "catalyst_inventory",
                str(catalyst.get("evidence_anchor", "")),
                str(catalyst.get("catalyst_identity_evidence", "")),
                "",
                "",
                "",
            ]
        )
        existing_fields_by_catalyst[catalyst_id].add("助剂类型")
        rows.append(
            [
                paper_title,
                catalyst_id,
                catalyst_name,
                "助剂",
                "添加方式",
                _join_list(catalyst.get("promoter_contents")),
                "",
                "catalyst_inventory",
                str(catalyst.get("evidence_anchor", "")),
                str(catalyst.get("catalyst_identity_evidence", "")),
                "",
                "",
                "",
            ]
        )
        existing_fields_by_catalyst[catalyst_id].add("添加方式")

    for assertion in data.get("catalyst_assertions", []):
        refs = [str(item) for item in assertion.get("catalyst_refs", [])]
        if not refs:
            continue
        property_name = str(assertion.get("property_name", ""))
        ontology_field = field_aliases.get(property_name, property_name)
        ontology_category = category_by_assertion_type.get(str(assertion.get("assertion_type", "")), "催化剂")
        for catalyst_id in refs:
            catalyst_name = str(catalyst_map.get(catalyst_id, {}).get("display_name", catalyst_id))
            existing_fields_by_catalyst.setdefault(catalyst_id, set()).add(ontology_field)
            rows.append(
                [
                    paper_title,
                    catalyst_id,
                    catalyst_name,
                    ontology_category,
                    ontology_field,
                    str(assertion.get("property_value", "")),
                    str(assertion.get("unit", "")),
                    str(assertion.get("method", "") or assertion.get("source_type", "")),
                    str(assertion.get("evidence_anchor", "")),
                    str(assertion.get("evidence_text", "")),
                    "",
                    "",
                    "",
                ]
            )

    required_placeholder_fields = [
        ("催化剂", "前驱体"),
        ("催化剂", "晶相结构"),
    ]
    for catalyst in data.get("catalyst_inventory", []):
        catalyst_id = str(catalyst.get("catalyst_id", ""))
        catalyst_name = str(catalyst.get("display_name", ""))
        existing = existing_fields_by_catalyst.get(catalyst_id, set())
        for category, field_name in required_placeholder_fields:
            if field_name in existing:
                continue
            rows.append(
                [
                    paper_title,
                    catalyst_id,
                    catalyst_name,
                    category,
                    field_name,
                    "",
                    "",
                    "pending_review",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
    return rows


def _count_catalyst_assertions_by_focus(data: dict, focus: str) -> int:
    return sum(1 for item in data.get("catalyst_assertions", []) if str(item.get("assertion_type", "")) == focus)


def _summarize_catalyst_assertions(assertions: list[dict], focus: str) -> str:
    relevant = [item for item in assertions if str(item.get("assertion_type", "")) == focus]
    if not relevant:
        return ""

    summaries: list[str] = []
    for item in relevant:
        property_name = str(item.get("property_name", ""))
        property_value = str(item.get("property_value", ""))
        unit = str(item.get("unit", ""))
        method = str(item.get("method", ""))
        
        # 格式化输出
        if focus == "characterization" and method:
            summary = f"[{method}] {property_name}: {property_value}"
        elif focus == "composition":
            summary = f"{property_name}: {property_value}"
        else:
            summary = f"{property_name}: {property_value}"
            
        if unit and unit not in ["None", ""]:
            summary += f" {unit}"
            
        summaries.append(summary)

    return " \n".join(summaries)


def _build_catalyst_combined_view(document: dict, data: dict) -> list[list[str]]:
    rows = [[
        "paper_title",
        "catalyst_id",
        "catalyst_name",
        "main_catalyst",
        "promoters",
        "Promoter Content (wt%)",
        "Actual Composition (wt%)",
        "key_components",
        "preparation",
        "reaction_conditions",
        "performance",
        "characterization",
        "mechanism",
        "catalyst_identity_evidence",
        "evidence_anchor",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    assertions = data.get("catalyst_assertions", [])

    for catalyst in data.get("catalyst_inventory", []):
        catalyst_id = str(catalyst.get("catalyst_id", ""))
        related = [item for item in assertions if catalyst_id in [str(ref) for ref in item.get("catalyst_refs", [])]]
        
        # 从catalyst_key_components中提取主催化剂
        main_catalyst = ""
        key_components = catalyst.get("catalyst_key_components", [])
        for component in key_components:
            if component in ["Ru", "Pt", "Pd", "Au", "Ag", "Rh", "Ir", "Ni", "Co", "Fe"]:
                main_catalyst = component
                break
        
        rows.append(
            [
                paper_title,
                catalyst_id,
                str(catalyst.get("display_name", "")),
                str(catalyst.get("main_catalyst", main_catalyst)),
                _join_list(catalyst.get("promoters")),
                _join_list(catalyst.get("promoter_contents")),
                _summarize_catalyst_assertions(related, focus="composition"),
                _join_list(catalyst.get("catalyst_key_components")),
                _summarize_catalyst_assertions(related, focus="preparation"),
                _summarize_catalyst_assertions(related, focus="reaction_condition"),
                _summarize_catalyst_assertions(related, focus="performance"),
                _summarize_catalyst_assertions(related, focus="characterization"),
                _summarize_catalyst_assertions(related, focus="mechanism"),
                str(catalyst.get("catalyst_identity_evidence", "")),
                str(catalyst.get("evidence_anchor", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _count_assertions_by_focus(data: dict, focus: str) -> int:
    return sum(1 for item in data.get("sample_assertions", []) if str(item.get("assertion_type", "")) == focus)


def _sorted_nodes_by_type(nodes: list[dict], node_type: str) -> list[dict]:
    filtered = [node for node in nodes if str(node.get("type", "")) == node_type]
    return sorted(
        filtered,
        key=lambda node: (
            str((node.get("properties") or {}).get("display_name", "")),
            str(node.get("id", "")),
        ),
    )


def _join_list(values: object) -> str:
    if not isinstance(values, list):
        return str(values or "")
    return " | ".join(str(value) for value in values)


def _summarize_assertions(assertions: list[dict], focus: str) -> str:
    relevant = [item for item in assertions if str(item.get("assertion_type", "")) == focus]
    if not relevant:
        return ""

    summaries: list[str] = []
    for item in relevant:
        property_name = str(item.get("property_name", ""))
        property_value = str(item.get("property_value", ""))
        unit = str(item.get("unit", ""))
        method = str(item.get("method", ""))
        
        # 格式化输出
        if focus == "characterization" and method:
            summary = f"[{method}] {property_name}: {property_value}"
        else:
            summary = f"{property_name}: {property_value}"
            
        if unit and unit not in ["None", ""]:
            summary += f" {unit}"
            
        summaries.append(summary)

    return " \n".join(summaries)


def _build_paper_summary_rows_v3(document: dict, data: dict) -> list[list[str]]:
    return [
        ["field", "value", "expert_note"],
        ["paper_title", str(document.get("title", "")), ""],
        ["source", str(document.get("source", "")), ""],
        ["filename", str(document.get("filename", "")), ""],
        ["catalyst_count", str(len(data.get("catalyst_inventory", []))), ""],
        ["assertion_count", str(len(data.get("catalyst_assertions", []))), ""],
        ["review_flag_count", str(len(data.get("review_flags", []))), ""],
        ["figure_assertion_count", str(len(data.get("figure_assertions", []))), ""],
        ["review_goal", "先核对催化剂身份，再逐条审核催化剂断言，最后集中处理 review flags", ""],
        ["how_to_review", "优先查看 Catalysts 与 Assertions 的 catalyst_id/catalyst_refs 是否一致，再审 evidence 与 corrected_record", ""],
    ]


def _build_catalyst_rows_v3(document: dict, catalysts: list[dict]) -> list[list[str]]:
    rows = [[
        "paper_title",
        "catalyst_id",
        "display_name",
        "original_names",
        "catalyst_category",
        "main_catalyst",
        "promoters",
        "promoter_contents",
        "catalyst_key_components",
        "catalyst_identity_evidence",
        "evidence_anchor",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    
    metals = ["Ru", "Fe", "Co", "Ni", "Cu", "Pt", "Pd", "Au", "Ag", "Rh", "Ir"]

    for catalyst in catalysts:
        # 改进主催化剂提取逻辑
        main_catalyst = str(catalyst.get("main_catalyst", ""))
        if not main_catalyst:
            key_components = catalyst.get("catalyst_key_components", [])
            found_metals = [c for c in key_components if c in metals]
            if found_metals:
                main_catalyst = " + ".join(found_metals)
            else:
                # 最后的备选：从名称中提取
                display_name = str(catalyst.get("display_name", ""))
                for m in metals:
                    if m in display_name:
                        main_catalyst = m
                        break
        
        rows.append(
            [
                paper_title,
                str(catalyst.get("catalyst_id", "")),
                str(catalyst.get("display_name", "")),
                _join_list(catalyst.get("original_names")),
                str(catalyst.get("catalyst_category", "")),
                main_catalyst,
                _join_list(catalyst.get("promoters")),
                _join_list(catalyst.get("promoter_contents")),
                _join_list(catalyst.get("catalyst_key_components")),
                str(catalyst.get("catalyst_identity_evidence", "")),
                str(catalyst.get("evidence_anchor", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_catalyst_assertion_rows_v3(document: dict, data: dict) -> list[list[str]]:
    rows = [[
        "paper_title",
        "assertion_id",
        "catalyst_refs",
        "catalyst_names",
        "assertion_type",
        "property_name",
        "value_type",
        "property_value",
        "unit",
        "method",
        "condition_context",
        "comparison_context",
        "source_type",
        "support_level",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    catalyst_name_map = {
        str(catalyst.get("catalyst_id", "")): str(catalyst.get("display_name", ""))
        for catalyst in data.get("catalyst_inventory", [])
    }

    for assertion in data.get("catalyst_assertions", []):
        catalyst_refs = [str(item) for item in assertion.get("catalyst_refs", [])]
        catalyst_names = [catalyst_name_map.get(catalyst_id, catalyst_id) for catalyst_id in catalyst_refs]
        rows.append(
            [
                paper_title,
                str(assertion.get("assertion_id", "")),
                " | ".join(catalyst_refs),
                " | ".join(catalyst_names),
                str(assertion.get("assertion_type", "")),
                str(assertion.get("property_name", "")),
                str(assertion.get("value_type", "")),
                str(assertion.get("property_value", "")),
                str(assertion.get("unit", "")),
                str(assertion.get("method", "")),
                str(assertion.get("condition_context", "")),
                str(assertion.get("comparison_context", "")),
                str(assertion.get("source_type", "")),
                str(assertion.get("support_level", "")),
                str(assertion.get("evidence_anchor", "")),
                str(assertion.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_review_flag_rows_v3(document: dict, data: dict) -> list[list[str]]:
    rows = [[
        "paper_title",
        "flag_id",
        "related_catalyst_refs",
        "related_catalyst_names",
        "issue_type",
        "issue",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    catalyst_name_map = {
        str(catalyst.get("catalyst_id", "")): str(catalyst.get("display_name", ""))
        for catalyst in data.get("catalyst_inventory", [])
    }

    for flag in data.get("review_flags", []):
        refs = [str(item) for item in flag.get("related_catalyst_refs", [])]
        rows.append(
            [
                paper_title,
                str(flag.get("flag_id", "")),
                " | ".join(refs),
                " | ".join(catalyst_name_map.get(catalyst_id, catalyst_id) for catalyst_id in refs),
                str(flag.get("issue_type", "")),
                str(flag.get("issue", "")),
                str(flag.get("evidence_anchor", "")),
                str(flag.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows


def _build_figure_rows_v3(document: dict, data: dict) -> list[list[str]]:
    rows = [[
        "paper_title",
        "figure_assertion_id",
        "figure_id",
        "catalyst_refs",
        "catalyst_names",
        "figure_type",
        "visual_information",
        "conclusion",
        "evidence_anchor",
        "evidence_text",
        "review_status",
        "review_comment",
        "corrected_record",
    ]]
    paper_title = str(document.get("title", ""))
    catalyst_name_map = {
        str(catalyst.get("catalyst_id", "")): str(catalyst.get("display_name", ""))
        for catalyst in data.get("catalyst_inventory", [])
    }

    for figure_assertion in data.get("figure_assertions", []):
        refs = [str(item) for item in figure_assertion.get("catalyst_refs", [])]
        rows.append(
            [
                paper_title,
                str(figure_assertion.get("figure_assertion_id", "")),
                str(figure_assertion.get("figure_id", "")),
                " | ".join(refs),
                " | ".join(catalyst_name_map.get(catalyst_id, catalyst_id) for catalyst_id in refs),
                str(figure_assertion.get("figure_type", "")),
                str(figure_assertion.get("visual_information", "")),
                str(figure_assertion.get("conclusion", "")),
                str(figure_assertion.get("evidence_anchor", "")),
                str(figure_assertion.get("evidence_text", "")),
                "",
                "",
                "",
            ]
        )
    return rows
