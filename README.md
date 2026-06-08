# KG2 — ai4s-in-mat

催化剂科学文献知识图谱构建管线。

## 架构

```
PDF → [OCR] → document.md → [LLM Extract] → entity_graph.json
                                ↓
                          [Rule Align] → entity_graph_aligned.json
                                ↓
                          [Entity Fusion] → entity_graph_fused.json
                                ↓
                          [Neo4j Store] → Neo4j 图数据库
```

## 管线阶段

| 阶段 | 模块 | 说明 |
|---|---|---|
| OCR | `scr/ocr/paddle_structured.py` | 在线 PaddleOCR API → 结构化 Markdown |
| Extract | `scr/knowledge_graph/entity_extraction.py` | LLM 驱动实体/关系抽取（DeepSeek） |
| Align | `scr/knowledge_graph/entity_alignment.py` | 规则归一化 + 轻度去重 |
| Fuse | `scr/knowledge_graph/entity_fusion.py` | 跨文档实体融合 |
| Store | `scr/knowledge_graph/entity_storage.py` | Neo4j Cypher MERGE 入库 |

## 本体设计

领域本体定义在 `Data/ontology_runtime/`：

- `node_types.yaml` — 两级节点体系（根节点 + 子属性节点）
- `relation_types.yaml` — 54 种关系类型
- `concept_tree.yaml` — 概念层级

核心实体类型：催化剂、助剂、反应条件、催化性能、表征方法、反应机理、制备工艺

## 快速开始

### 1. 环境配置

```bash
cp .env.example .env
```

`.env` 必填项：

```bash
PADDLEOCR_VL_API_URL="https://..."     # 在线 PaddleOCR API
PADDLEOCR_VL_API_KEY="..."
KG_LLM_API_URL="https://api.deepseek.com/v1/chat/completions"
KG_LLM_API_KEY="sk-..."
KG_LLM_MODEL="deepseek-chat"
NEO4J_URI="bolt://localhost:7687"
NEO4J_USER="neo4j"
NEO4J_PASSWORD="..."
```

### 2. 安装依赖

```bash
pip install requests pyyaml neo4j
```

### 3. 准备论文

```bash
# 方式 A: 自动下载
python run_pipeline.py --download "iron catalyst ammonia"

# 方式 B: 手动放入 Data/ 目录
cp your-papers/*.pdf Data/
```

### 4. 运行全流程

```bash
# 处理 Data/ 下所有 PDF
python run_pipeline.py

# 下载 + 处理 50 篇
python run_pipeline.py --download --target 50

# 单篇测试
python run_pipeline.py --file "Data/test.pdf"

# 全量重入库（清空 Neo4j）
python run_pipeline.py --skip-existing --clear-neo4j

# 分步执行
python run_pipeline.py --steps ocr,extract     # 只做 OCR + 抽取
python run_pipeline.py --steps align,fuse,store # 只做后三步
```

### 参数说明

| 参数 | 默认 | 说明 |
|---|---|---|
| `--download` | 关 | 自动从 Europe PMC 下载论文 |
| `--target` | 50 | 目标论文数 |
| `--file` | — | 处理单篇 PDF |
| `--skip-existing` | 关 | 跳过已有 OCR 产物的论文 |
| `--clear-neo4j` | 关 | 入库前清空 Neo4j |
| `--steps` | all | download/ocr/extract/align/fuse/store |

## 运行产物

每篇论文的产物保存在 `artifacts/ocr/<论文名>/run_<时间戳>/`：

```
run_20260401_085511/
├── document.md              # OCR 提取的 Markdown
├── document_structured.md   # 结构化 Markdown（含图表标注）
├── raw_response.json        # OCR API 原始响应
├── image_index.json         # 图片索引
├── assets/                  # 下载的图片资源
│   ├── layout_det_res_*.jpg
│   └── imgs/
└── knowledge_graph/
    ├── entity_graph.json           # LLM 抽取结果
    ├── entity_graph_raw.txt        # LLM 原始输出
    ├── entity_graph_aligned.json   # 规则对齐后
    ├── entity_graph_fused.json     # 融合后
    └── entity_graph_storage_ready.json  # Neo4j 入库就绪
```

## 项目设计原则

- **算法优先**：管线阶段明确，中间产物可审查
- **本体驱动**：YAML 定义领域 schema，LLM 按本体抽取
- **专家审核优先**：结构化 Markdown + Excel 审核导出 优先于图谱可视化
- **规则优先**：归一化以规则为主，LLM 辅助

详见 [Blueprint.md](Blueprint.md) 和 [Memory.md](Memory.md)。
