# KG2 Blueprint

## Project Positioning

KG2 is an algorithm-first knowledge graph workspace for scientific literature.

The project optimizes for:
- Inspectable intermediate artifacts
- Stable local execution for a single algorithm developer
- Explicit pipeline stages instead of platform-first workflows
- Readable ontology and normalization standards

The project does not currently optimize for:
- Frontend-first interaction
- Multi-user platform workflows
- Complex orchestration infrastructure
- Aggressive semantic inference

## Current Goal

Build a stable OCR-to-graph pipeline for catalyst literature, with clear intermediate artifacts and a controllable Neo4j import path.

Current pipeline boundary:
1. OCR
2. Entity extraction
3. Entity alignment
4. Entity fusion
5. Graph storage

## Current Status

### Version

- Current version: `0.0.8`
- Commit description: `入库清理与属性收缩`

### Completed

- [x] Created independent Git repository for `KG2`
- [x] Added project-level `.gitignore`
- [x] Implemented online PaddleOCR client in [paddle_api.py](/Users/nakilea/Desktop/Code/KG2/scr/ocr/paddle_api.py)
- [x] Added `.env`-based OCR and LLM configuration loading
- [x] Added fixed-variable local `__main__` test entry for OCR
- [x] Standardized OCR output directory naming
- [x] Added OCR tests
- [x] Converted ontology source into reviewable YAML: [ontology_source_review.yaml](/Users/nakilea/Desktop/Code/KG2/Data/ontology_source_review.yaml)
- [x] Created runtime ontology:
  - [node_types.yaml](/Users/nakilea/Desktop/Code/KG2/Data/ontology_runtime/node_types.yaml)
  - [relation_types.yaml](/Users/nakilea/Desktop/Code/KG2/Data/ontology_runtime/relation_types.yaml)
  - [concept_tree.yaml](/Users/nakilea/Desktop/Code/KG2/Data/ontology_runtime/concept_tree.yaml)
- [x] Rewrote extraction around runtime ontology in [entity_extraction.py](/Users/nakilea/Desktop/Code/KG2/scr/knowledge_graph/entity_extraction.py)
- [x] Added grouped-output graph drafting with `document/nodes/edges`
- [x] Added runtime stage logs for extraction and LLM timing
- [x] Added manual pipeline runner in [main.py](/Users/nakilea/Desktop/Code/KG2/main.py)
- [x] Added first-pass format standard in [format_standard.yaml](/Users/nakilea/Desktop/Code/KG2/Data/normalization/format_standard.yaml)
- [x] Implemented rule-based entity alignment in [entity_alignment.py](/Users/nakilea/Desktop/Code/KG2/scr/knowledge_graph/entity_alignment.py)
- [x] Implemented first-pass entity fusion in [entity_fusion.py](/Users/nakilea/Desktop/Code/KG2/scr/knowledge_graph/entity_fusion.py)
- [x] Implemented Neo4j storage in [entity_storage.py](/Users/nakilea/Desktop/Code/KG2/scr/knowledge_graph/entity_storage.py)
- [x] Added storage projection before Neo4j import
- [x] Added Neo4j database clear function for reruns
- [x] Added tests for extraction, alignment, fusion, storage, and manual runner

### In Progress

- [ ] Shrink graph node properties to domain-essential fields only
- [ ] Improve Neo4j graph readability and caption behavior
- [ ] Validate whether current node granularity is scientifically useful

### Pending

- [ ] Rename `scr` to `src` if confirmed
- [ ] Add chunked extraction for long review articles
- [ ] Add curated alias dictionaries where rules are insufficient
- [ ] Decide whether some value nodes should remain nodes or move to edge/property form

### Confirmed Decisions

- [x] Keep [main.py](/Users/nakilea/Desktop/Code/KG2/main.py) as the current manual pipeline runner
- [x] `scr -> src` should be changed later
- [x] Use runtime ontology YAML as the active schema source
- [x] Use rule-first normalization before any LLM-assisted advanced alignment
- [x] Keep fused graph for auditability
- [x] Project Neo4j storage from fused graph instead of storing all fused properties directly

## Workstreams

### A. OCR Layer

Objective:
Turn PDF into stable markdown and image artifacts.

Checklist:
- [x] Online PaddleOCR API client
- [x] Environment loading
- [x] Markdown output writing
- [x] Asset downloading
- [x] Debug logging switch
- [x] Raw API response archival
- [ ] OCR failure classification
- [ ] Batch OCR support

Deliverables:
- OCR markdown file
- Downloaded page assets
- Raw OCR response JSON

### B. Ontology Layer

Objective:
Keep domain schema readable, reviewable, and operational.

Checklist:
- [x] Source ontology review YAML
- [x] Runtime node types
- [x] Runtime relation types
- [x] Runtime concept tree
- [ ] Property-level governance by node type
- [ ] Review whether current node granularity is too fine or too coarse

### C. Extraction Layer

Objective:
Extract graph-ready entities and relations from OCR output.

Checklist:
- [x] Runtime-ontology-driven extraction
- [x] Grouped JSON output
- [x] Graph draft generation
- [x] Real-document manual validation
- [ ] Chunking strategy for long documents
- [ ] Better markdown cleanup before extraction

### D. Normalization Layer

Objective:
Make extracted entities readable and mergeable.

Checklist:
- [x] First-pass format standard
- [x] Rule-based display normalization
- [x] Same-type light deduplication
- [ ] Alias dictionary support
- [ ] Better number/unit normalization coverage
- [ ] Controlled advanced alignment strategy

### E. Fusion Layer

Objective:
Aggregate aligned entities into an auditable fused graph.

Checklist:
- [x] Alias aggregation
- [x] Source-node tracking
- [x] Merge count and fusion status
- [x] Fused graph export
- [ ] Revisit which fusion metadata should stay local only

### F. Storage Layer

Objective:
Store a clean graph in Neo4j without importing pipeline noise.

Checklist:
- [x] Neo4j connection via `.env`
- [x] Node/edge MERGE storage
- [x] Database clear function
- [x] Storage-ready graph projection
- [x] Minimal property policy draft
- [ ] Finalize minimal property policy by node type
- [ ] Re-import and inspect graph readability after each policy change
- [ ] Decide whether some numeric nodes should remain nodes

### G. Evaluation Layer

Objective:
Judge whether the graph is scientifically usable.

Checklist:
- [ ] Node readability checklist
- [ ] Edge correctness checklist
- [ ] Storage property checklist
- [ ] Error case registry
- [ ] Small gold-sample review set

## Current Files of Interest

Core modules:
- [paddle_api.py](/Users/nakilea/Desktop/Code/KG2/scr/ocr/paddle_api.py)
- [entity_extraction.py](/Users/nakilea/Desktop/Code/KG2/scr/knowledge_graph/entity_extraction.py)
- [entity_alignment.py](/Users/nakilea/Desktop/Code/KG2/scr/knowledge_graph/entity_alignment.py)
- [entity_fusion.py](/Users/nakilea/Desktop/Code/KG2/scr/knowledge_graph/entity_fusion.py)
- [entity_storage.py](/Users/nakilea/Desktop/Code/KG2/scr/knowledge_graph/entity_storage.py)
- [main.py](/Users/nakilea/Desktop/Code/KG2/main.py)

Normalization / schema files:
- [ontology_source_review.yaml](/Users/nakilea/Desktop/Code/KG2/Data/ontology_source_review.yaml)
- [node_types.yaml](/Users/nakilea/Desktop/Code/KG2/Data/ontology_runtime/node_types.yaml)
- [relation_types.yaml](/Users/nakilea/Desktop/Code/KG2/Data/ontology_runtime/relation_types.yaml)
- [concept_tree.yaml](/Users/nakilea/Desktop/Code/KG2/Data/ontology_runtime/concept_tree.yaml)
- [format_standard.yaml](/Users/nakilea/Desktop/Code/KG2/Data/normalization/format_standard.yaml)
- [storage_property_policy.yaml](/Users/nakilea/Desktop/Code/KG2/Data/normalization/storage_property_policy.yaml)

## Immediate Next Tasks

Priority order for the next iteration:

1. Finalize minimal Neo4j property policy by node type
2. Re-import after clear and inspect the graph again
3. Decide whether value-like nodes such as `粒径` and `比表面积` should remain nodes or move to properties
4. Add chunked extraction for long review documents
5. Introduce alias dictionary support only where rule normalization is insufficient

## Recommended Next Focus

The next correct focus is not new modules.

It is:
- Graph readability
- Property governance
- Node granularity control

More concretely:
- Keep the current extraction/alignment/fusion/storage chain stable
- Reduce noisy node properties further if needed
- Evaluate whether some low-value numeric nodes should remain first-class nodes
- Only after graph quality is acceptable, move to relation enrichment or chunked extraction

## Dev Rules

- Each version commit uses strict version title form such as `0.0.8`
- Commit body should describe the completed milestone in one short phrase
- Do not commit `.env`, raw `Data/` files by default, or `artifacts/`
- Prefer one stable pipeline improvement per iteration
- Verify behavior with tests before marking a step complete

## Change Log

### 0.0.8

- 入库清理与属性收缩
- Added storage projection before Neo4j import
- Added minimal storage property policy
- Added clear-database support

### 0.0.7

- 知识图谱入库初步完成
- Added initial Neo4j storage module

### 0.0.6

- 实体融合初步完成
- Added fused graph generation

### 0.0.5

- 实体对齐初步完成
- Added rule-based alignment and light dedup

### 0.0.4

- 格式标准初版与抽取日志增强
- Added format normalization baseline
- Added extraction runtime logging

### 0.0.3

- 新本体基线与实体抽取迁移
- Added runtime ontology and extraction migration

### 0.0.2

- OCR输出目录规范化
- Standardized OCR artifact naming

### 0.0.1

- OCR初步完成
- Added online PaddleOCR API module
- Added OCR unit tests
- Added standalone Git repository and ignore rules
