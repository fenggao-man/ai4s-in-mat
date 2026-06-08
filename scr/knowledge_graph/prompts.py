ENTITY_EXTRACT_PROMPT = """
你是一位材料化学知识抽取专家。请严格根据下方【运行时本体定义】，
从输入文本中提取符合合成氨研究范畴的结构化信息，输出为分组 JSON。

【运行时本体定义】
{ontology_text}

【实体类型说明】
- 催化剂：催化剂的综合属性（活性组分、前驱体、晶相、铁比、比表面积、粒径等直接作为属性字段）
- 化学物质：活性组分、前驱体、载体、溶剂、产物等所有化学实体。可附带 composition（组成，如 {"Fe": {"value": 95, "unit": "wt%"}}）和 properties（固有物化属性，如 {"BET_surface_area": {"value": 13.2, "unit": "m²/g"}}）
- 助剂：催化剂中添加的助剂（含量、类型、添加方式作为属性）
- 制备步骤：按时间顺序的制备工艺步骤（可多个，用 step_order 排序）。每步应标注 inputs（消耗的化学物质，逗号分隔）和 outputs（产出的化学物质，逗号分隔）
- 测试：反应条件和催化性能的绑定组合（条件和结果在同一节点中）
- 表征：表征方法及结果（method 字段取值：XRD/BET/TEM/SEM/XPS/H2-TPR/N2-TPD/NH3-TPD/Mossbauer/Raman/FT-IR）
- 机理：反应机理描述（aspect 字段取值：解离吸附/缔合吸附/加氢步骤/脱附机理/活性位模型/速率控制步骤/活化能/反应级数/吸附热/指前因子/动力学参数）

【任务】
1. 输出必须是一个 JSON 对象，不要输出 Markdown，不要输出解释文字。
2. JSON 顶层必须包含以下数组（无数据的可给空数组）：
   - "document": 文档信息对象（标题、文件名）
   - "催化剂": 数组
   - "化学物质": 数组
   - "助剂": 数组
   - "制备步骤": 数组
   - "测试": 数组
   - "表征": 数组
   - "机理": 数组
3. 每个对象按本体定义填写属性字段，信息缺失的字段可省略。
4. 只抽文本中明确出现的信息，不做关系推断，不补充文外知识。
5. 表格优先：若文本含表格，应优先从表格中抽取结构化信息。
6. 每个节点如能追溯到原文具体句子，请加入 "source_text" 字段，引用原文原句。

【输出示例】
{output_example}

【待抽取文本】
{text}
"""

# ── Multi-stage extraction prompts ──────────────────────────────────────────

SYNTHESIS_EXTRACT_PROMPT = """
你是一位合成氨催化剂合成工艺抽取专家。请严格根据下方【运行时本体定义】，
从输入文本中提取催化剂的合成相关信息（组成、助剂、制备工艺、反应机理），
输出为分组 JSON。

【运行时本体定义 - 合成相关部分】
{ontology_text}

【任务】
1. 输出必须是一个 JSON 对象，不要输出 Markdown，不要输出解释文字。
2. JSON 顶层必须包含以下数组（无数据的给空数组）：
   - "document": 文档信息对象
   - "催化剂": 数组
   - "化学物质": 数组（active_component / precursor / support / solvent / product / reagent）
   - "助剂": 数组
   - "制备步骤": 数组
   - "机理": 数组
3. **重点关注**：
   - 催化剂：name、active_component、precursor、crystal_phase、iron_ratio、surface_area、pore_structure、particle_size、preparation_method、mechanical_strength、support
   - 化学物质：name、formula、role（reactant / solvent / catalyst / reagent / additive / support / precursor / intermediate / product）、composition、properties。role 用于确定该物质在反应中的角色、composition（组成，JSON格式，如某些催化剂有明确元素组成）、properties（固有物化属性，JSON格式，如BET比表面积、粒径等来自合成/表征段的数据）
   - 助剂：name、content_value、content_unit、promoter_type、addition_method
   - 制备步骤：step_order（从1开始递增）、step_name、method、temperature、duration、atmosphere、description、inputs（该步消耗的化学物质名称列表，每个名称后可附带角色标签，如 "CeO₂(载体), Ru₃(CO)₁₂(前驱体), THF(溶剂)"）、outputs（该步产出的化学物质名称列表）——inputs/outputs 与化学物质节点的 name 字段对应
   - 机理：aspect（取值见上方说明）、description、value、unit
4. 只抽文本中明确出现的信息，不做关系推断，不补充文外知识。
5. 表格优先：若文本含表格，应优先从表格中抽取结构化信息。
6. source_text 必须引用原文原句。

【输出示例】
{output_example_synthesis}

【待抽取文本】
{text}
"""

SYNTHESIS_CHECK_PROMPT = """
你刚才从文本中抽取了催化剂的合成相关信息。现在请**严格审查**你之前的抽取结果，
对照原文检查是否有遗漏、错误或多余的内容。

请返回一个 JSON 对象，仅包含需要修改的部分，格式如下：

```json
{{
  "nodes_to_add": {{}},
  "nodes_to_update": {{}},
  "node_names_to_delete": {{}}
}}
```

其中每个字段的值是按实体类型分组的对象，例如：
- nodes_to_add: {{ "催化剂": [...], "化学物质": [...], "助剂": [...], "制备步骤": [...], "机理": [...] }}
- nodes_to_update: {{ "催化剂": [...], ... }}（按 name 或唯一标识匹配，提供完整替换对象）
- node_names_to_delete: {{ "催化剂": ["name1"], ... }}

审查要点：
1. 是否遗漏了任何催化剂、助剂、制备步骤、机理描述？
2. 制备步骤的 inputs 中的角色标签（载体/前驱体/溶剂等）是否与对应化学物质的 role 一致？outputs 是否正确反映了该步的产物？
3. 化学物质的 composition/properties 是否正确抽取？
2. 制备步骤的 inputs 中的角色标签（载体/前驱体/溶剂等）是否与对应化学物质的 role 一致？outputs 是否正确反映了该步的产物？
2. 是否有错误的属性值（组成、含量、温度等）？
3. 是否有编造的、文本中不存在的信息？
4. source_text 引用是否准确对应原文？

如果没有需要修改的地方，返回空对象 {{}}。
只输出 JSON，不要输出解释文字。确保以 ```json 开头、``` 结尾。
"""

TESTING_EXTRACT_PROMPT = """
你是一位合成氨催化剂性能测试抽取专家。请严格根据下方【运行时本体定义】，
从输入文本中提取催化剂的反应条件和催化性能数据，输出为分组 JSON。

【运行时本体定义 - 测试相关部分】
{ontology_text}

【注意】以下催化剂已在合成阶段被识别，请使用相同的名称以保持一致：
{catalyst_names_from_synthesis}

【任务】
1. 输出必须是一个 JSON 对象，不要输出 Markdown，不要输出解释文字。
2. JSON 顶层必须包含：
   - "测试": 数组
    每个测试对象将反应条件与对应性能数据绑定在一起：
    - 反应条件：temperature、pressure、ghsv、h2_n2_ratio、feed_composition、gas_purity、duration
    - 催化性能：nh3_activity、conversion、selectivity、stability、lifetime、toxicity_resistance
3. 如果某个催化剂在合成阶段已出现但本文没有其测试数据，可以不输出。
4. 只抽文本中明确出现的信息，不做关系推断，不补充文外知识。
5. 表格优先：若文本含表格，应优先从表格中抽取结构化信息。
6. 每个测试对象需包含 catalyst_name 以关联到对应催化剂。

【输出示例】
{output_example_testing}

【待抽取文本】
{text}
"""

TESTING_CHECK_PROMPT = """
你刚才从文本中抽取了催化剂的测试相关信息。现在请**严格审查**你之前的抽取结果，
对照原文检查是否有遗漏、错误或多余的内容。

请返回一个 JSON 对象，仅包含需要修改的部分，格式如下：

```json
{{
  "nodes_to_add": {{ "测试": [...] }},
  "nodes_to_update": {{ "测试": [...] }},
  "node_names_to_delete": {{ "测试": [...] }}
}}
```

审查要点：
1. 是否遗漏了任何反应条件或性能数据？
2. 数值和单位是否正确？
3. 是否有编造的、文本中不存在的数据？
4. 催化剂名称是否与合成阶段一致？
5. 条件和性能是否正确绑定在同一测试节点中？

如果没有需要修改的地方，返回空对象 {{}}。
只输出 JSON，不要输出解释文字。确保以 ```json 开头、``` 结尾。
"""

CHARACTERIZATION_EXTRACT_PROMPT = """
你是一位催化剂表征数据抽取专家。请严格根据下方【运行时本体定义】，
从输入文本中提取催化剂的表征方法和结果，输出为分组 JSON。

【运行时本体定义 - 表征相关部分】
{ontology_text}

【注意】以下催化剂已在前面阶段被识别，请使用相同的名称以保持一致：
{catalyst_names_from_synthesis}

【任务】
1. 输出必须是一个 JSON 对象，不要输出 Markdown，不要输出解释文字。
2. JSON 顶层必须包含：
   - "表征": 数组
    每个表征对象包含：
    - method: 方法名称（XRD/BET/TEM/SEM/XPS/H2-TPR/N2-TPD/NH3-TPD/Mossbauer/Raman/FT-IR）
    - result_summary: 关键发现摘要
    - confirmed_phase: 表征证实的晶相或化学物种（可选）
    - source_text: 原文引用
    - catalyst_name: 关联催化剂
3. 只抽取对**催化剂**的表征，不抽取对非催化剂材料的表征。
4. 如果某种表征方法在文中提及但没有给出数据，仍然抽取但标记 note 为"未报告数据"。
5. 只抽文本中明确出现的信息，不做关系推断，不补充文外知识。

【输出示例】
{output_example_characterization}

【待抽取文本】
{text}
"""

CHARACTERIZATION_CHECK_PROMPT = """
你刚才从文本中抽取了催化剂的表征信息。现在请**严格审查**你之前的抽取结果，
对照原文检查是否有遗漏、错误或多余的内容。

请返回一个 JSON 对象，仅包含需要修改的部分，格式如下：

```json
{{
  "nodes_to_add": {{ "表征": [...] }},
  "nodes_to_update": {{ "表征": [...] }},
  "node_names_to_delete": {{ "表征": [...] }}
}}
```

审查要点：
1. 是否遗漏了任何表征方法？（XRD、BET、TEM、SEM、XPS、H2-TPR、Raman 等）
2. result_summary 是否准确反映了原文发现？
3. confirmed_phase 是否正确？
4. source_text 引用是否准确？
5. 是否错误地抽取了非催化剂的表征信息？

如果没有需要修改的地方，返回空对象 {{}}。
只输出 JSON，不要输出解释文字。确保以 ```json 开头、``` 结尾。
"""
