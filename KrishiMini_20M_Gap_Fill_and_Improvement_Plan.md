# AGRIMIND / KrishiMini-20M
## Principal AI Systems Architect Gap-Fill & Improvement Plan
### From the current implementation to an autonomous, from-scratch 20M agricultural foundation model

**Document status:** Implementation directive  
**Audience:** Coding agents, AI engineers, ML engineers, data engineers, MLOps engineers, Principal AI Architect  
**Primary objective:** Convert the current AGRIMIND platform into a disciplined autonomous data-to-model system capable of producing and continuously improving a ~20M-parameter KrishiMini model from scratch.

---

## 0. Executive Decision

The existing AGRIMIND architecture should **not be discarded**.

The current implementation already has a valuable foundation:

- real/demo acquisition isolation
- `run_id`-scoped data runs
- multilingual EN/HI/MR discovery
- trusted-source allow-list and trust scoring
- ingestion stages and progress reporting
- PII/toxicity/relevance/deduplication concepts
- provenance and quarantine concepts
- GraphRAG/vector retrieval architecture
- safety gates
- evaluation and golden-set concepts
- immutable dataset/model manifest concepts
- self-improvement/flywheel design
- production infrastructure and observability design

The principal correction is **direction and sequencing**.

The current plan is stronger as a production agricultural AI platform than as a from-scratch foundation-model program. The current Model Factory is centered on dataset validation, tokenizer matching, instruction/DPO preparation, LoRA/QLoRA fine-tuning, evaluation, ONNX export and registry upload. That is not yet a complete scratch-pretraining factory.

Therefore:

> **Keep the platform. Add a dedicated Foundation Model Factory and reorder delivery around data quality, tokenizer quality, exact model architecture, scratch pretraining, evaluation, and only then RAG/agents/production scale.**

---

# 1. Target State

## 1.1 Canonical product/model

Use one canonical first-model identity:

```text
KrishiMini-20M
```

Do not maintain ambiguity between "18M" and "20M" as competing targets.

The 18M target can remain in historical documentation, but the new development contract should use:

```text
model_family = krishimini
target_parameter_budget = 20_000_000
```

The exact architecture must be generated and validated by code, not estimated manually.

---

# 2. New Development Strategy

Replace the old model-centric sequence:

```text
DAQ
→ GraphRAG
→ Agents
→ Fine-tuning
→ Deployment
```

with:

```text
K0  Repository & engineering safety
 ↓
K1  Autonomous data acquisition
 ↓
K2  Data refinement & factual validation
 ↓
K3  Corpus Factory
 ↓
K4  Tokenizer Factory
 ↓
K5  KrishiMini architecture factory
 ↓
K6  Scratch pretraining
 ↓
K7  Continued agricultural pretraining
 ↓
K8  SFT / instruction tuning
 ↓
K9  Evaluation / KrishiBench
 ↓
K10 Retrieval + GraphRAG
 ↓
K11 Safety + Agent layer
 ↓
K12 Autonomous improvement flywheel
 ↓
K13 Edge/cloud production
```

This order is deliberate.

Do not spend significant engineering effort on advanced agents or Kubernetes before the model/data loop is measurable.

---

# 3. P0 — Immediate Corrections

## P0.1 Fix the tokenizer target

The current plan specifies a 64K vocabulary. A 20M-parameter model cannot safely use that as the default without explicitly accounting for the embedding matrix.

For a hidden size of 384:

```text
64,000 × 384 = 24,576,000
```

parameters before considering the rest of the transformer.

Therefore 64K is incompatible with the intended small parameter budget unless architecture dimensions are drastically reduced.

### Action

Implement tokenizer benchmarking for:

```text
12K
16K
24K
```

Use **16K as the initial candidate**, not as an irreversible assumption.

### Required benchmark

Measure:

- token fertility
- bytes/token
- tokens/character
- language-specific fertility
- agricultural vocabulary coverage
- code-switch handling
- number/unit handling
- Unicode normalization
- Marathi Devanagari behavior
- Hindi Devanagari behavior
- English behavior
- common transliteration behavior

Create:

```text
packages/models/tokenizer/
├── train.py
├── evaluate.py
├── normalization.py
├── coverage.py
├── fertility.py
├── manifest.py
└── tests/
```

---

# 4. P0.2 Introduce a Foundation Model Factory

Create:

```text
packages/foundation_model/
```

Recommended structure:

```text
packages/foundation_model/
├── architecture/
│   ├── config.py
│   ├── param_count.py
│   ├── model.py
│   └── validation.py
├── tokenizer/
├── dataset/
├── pretraining/
│   ├── trainer.py
│   ├── checkpoint.py
│   ├── scheduler.py
│   └── resume.py
├── posttraining/
│   ├── sft.py
│   └── dpo.py
├── evaluation/
├── manifests/
└── tests/
```

The factory must own the complete path:

```text
raw/curated corpus
→ dataset manifest
→ tokenizer
→ tokenized shards
→ architecture
→ initialization
→ pretraining
→ checkpoint
→ evaluation
→ post-training
→ export
```

---

# 5. P0.3 Add True Scratch Pretraining

The existing LoRA/QLoRA pipeline should remain for later post-training and teacher-model adaptation.

Add:

```text
Scratch Pretraining
```

Pipeline:

```text
Dataset Manifest Validation
→ Tokenizer Manifest Validation
→ Tokenization
→ Shard Validation
→ Train/Validation Split Validation
→ Model Initialization From Scratch
→ Pretraining
→ Periodic Evaluation
→ Checkpoint
→ Resume
→ Final Evaluation
```

No pretrained language-model checkpoint is allowed in this stage.

Add an explicit manifest field:

```json
{
  "training_mode": "scratch",
  "base_checkpoint": null
}
```

CI must fail if a scratch run references a pretrained checkpoint.

---

# 6. P0.4 Exact 20M Architecture Contract

Create:

```text
configs/models/krishimini_20m.yaml
```

Candidate starting architecture:

```yaml
model_family: krishimini
target_parameters: 20000000

architecture:
  type: decoder_only_transformer
  layers: 10
  hidden_size: 384
  attention_heads: 6
  kv_heads: 2
  head_dim: 64
  ffn_hidden_size: 1024
  activation: swiglu
  normalization: rmsnorm
  positional_encoding: rope
  tie_embeddings: true

tokenizer:
  vocab_size: 16000

training:
  context_length: 1024
```

This is a **starting configuration**, not a final parameter guarantee.

Implement:

```text
scripts/model_param_count.py
```

and:

```text
architecture/validation.py
```

The build must report:

```text
total_parameters
trainable_parameters
embedding_parameters
attention_parameters
ffn_parameters
norm_parameters
```

and fail when the result is outside the declared budget.

---

# 7. P0.5 Fix Robots Policy

The project policy says robots rules must be respected.

Therefore production/default configuration must not bypass them.

Change:

```text
SKIP_ROBOTS=true
```

to:

```text
SKIP_ROBOTS=false
```

Any bypass must be:

- explicit
- local/test-only
- logged
- disabled by default
- unavailable to autonomous production acquisition

Add a CI configuration test that rejects production configuration with a robots bypass.

---

# 8. P0.6 Add Training Eligibility Gate

Source discovery and source licensing are not the same as training permission.

Create:

```text
data_kernel/governance/training_eligibility.py
```

Every source/document must pass:

```text
DISCOVERED
→ ACCESSIBLE
→ LICENSE IDENTIFIED
→ LICENSE POLICY CHECK
→ TRAINING ELIGIBILITY
→ ATTRIBUTION REQUIREMENT
→ APPROVED / QUARANTINED
```

Store:

```json
{
  "license_id": "...",
  "license_confidence": 0.98,
  "training_allowed": true,
  "commercial_use_allowed": "...",
  "attribution_required": true,
  "redistribution_allowed": "...",
  "policy_version": "..."
}
```

Never infer "training allowed" merely because a document was publicly accessible.

---

# 9. P0.7 Separate Data Products

Do not use one corpus for every purpose.

Build:

```text
Raw Data
  ↓
Curated Data
  ├── Foundation Dataset
  ├── RAG Dataset
  ├── Knowledge Graph Facts
  ├── SFT Dataset
  ├── DPO Dataset
  ├── Safety Dataset
  └── Evaluation Dataset
```

Each must have its own manifest and eligibility policy.

---

# 10. P0.8 Prevent Evaluation Contamination

Create a dataset lineage field:

```text
document_group_id
translation_group_id
source_family_id
semantic_cluster_id
```

A multilingual translation set must remain in the same split.

For example:

```text
English document
Hindi translation
Marathi translation
```

must not become:

```text
English → train
Hindi → validation
Marathi → test
```

because that can artificially inflate evaluation.

Implement split assignment at the **group level**, not document level.

---

# 11. P1 — Data Refinement Engine

Create:

```text
packages/data_kernel/refinement/
```

Components:

```text
unicode_normalizer
text_cleaner
ocr_repair
boilerplate_remover
sentence_segmenter
table_reconstructor
number_normalizer
unit_normalizer
date_normalizer
crop_name_normalizer
scientific_name_normalizer
language_normalizer
transliteration_normalizer
```

Important rule:

> Refinement may repair formatting, but must not silently alter factual claims.

Store original and refined versions.

Example:

```json
{
  "raw_text_hash": "...",
  "refined_text_hash": "...",
  "transformations": [
    "unicode_normalization",
    "whitespace_normalization"
  ]
}
```

---

# 12. P1 — Factual Validation Engine

Create:

```text
packages/data_kernel/validation/
```

Validate:

- source authority
- date validity
- region applicability
- crop applicability
- season
- units
- dosage formatting
- scientific naming
- cross-source consistency
- temporal conflicts
- geographic conflicts

A conflict must be represented explicitly:

```json
{
  "claim_a": "...",
  "claim_b": "...",
  "conflict": true,
  "resolution_status": "unresolved"
}
```

Never silently overwrite one source with another.

---

# 13. P1 — Quality Score Redesign

Do not use only:

```text
quality_score = 0.91
```

Use multidimensional quality:

```json
{
  "source_quality": 0.98,
  "language_quality": 0.94,
  "structure_quality": 0.91,
  "agri_relevance": 0.99,
  "factual_confidence": 0.93,
  "duplication_risk": 0.02,
  "license_confidence": 1.0,
  "training_utility": 0.95
}
```

Then calculate a policy-defined aggregate.

Store both:

- component scores
- aggregate score
- scoring policy version

---

# 14. P1 — Autonomous Discovery Source Graph

The current keyword discovery should evolve into source expansion.

Create:

```text
packages/data_kernel/sources/source_graph/
```

Model:

```text
source
→ publisher
→ organization
→ repository
→ publication
→ related source
→ linked dataset
```

The autonomous discovery loop becomes:

```text
Seed sources
→ Discover related sources
→ Validate trust
→ Validate license
→ Probe accessibility
→ Rank
→ Acquire
→ Learn from success/failure
→ Discover next sources
```

The system should learn which source classes are productive.

---

# 15. P1 — Acquisition Funnel Metrics

Create a mandatory funnel:

```text
discovered
→ reachable
→ license-approved
→ downloaded
→ extracted
→ language-valid
→ agriculture-relevant
→ quality-valid
→ deduplicated
→ training-eligible
```

Track counts and percentages per:

- run
- source
- language
- category
- country
- publisher
- date

Primary autonomous data KPI:

```text
training_eligible_tokens_per_acquisition_hour
```

Do not optimize for document count alone.

---

# 16. P1 — Corpus Factory

Create:

```text
packages/foundation_model/dataset/
```

Responsibilities:

1. consume approved curated data
2. apply dataset policy
3. assign dataset splits
4. balance languages
5. balance agricultural categories
6. remove evaluation contamination
7. generate token shards
8. calculate corpus statistics
9. write immutable dataset manifest

Recommended output:

```text
datasets/
└── krishimini/
    └── ds-YYYY-MM-DD-vN/
        ├── manifest.json
        ├── train/
        ├── validation/
        ├── metadata/
        ├── statistics.json
        └── lineage.json
```

---

# 17. P1 — Token-Based Training, Not Record-Based Training

Training sessions must be controlled by tokens.

Bad:

```text
15,000 records/session
```

Better:

```text
max_tokens_per_session
max_wall_clock_minutes
max_temperature
```

For laptop development:

```yaml
training:
  max_session_minutes: 60
  checkpoint_interval_minutes: 10
  checkpoint_interval_tokens: 1000000
```

The exact values are configurable.

---

# 18. P1 — Laptop Training Controller

Create:

```text
packages/foundation_model/pretraining/laptop_controller.py
```

It should support:

```text
session time limit
GPU memory limit
checkpoint interval
safe stop
resume
cooldown
manual pause
automatic pause
```

A run should be safely interruptible at any checkpoint boundary.

---

# 19. P1 — Complete Checkpoint State

A checkpoint must contain:

```text
model weights
optimizer state
scheduler state
gradient scaler state
global step
tokens seen
dataset manifest ID
tokenizer manifest ID
model config ID
current shard
current offset
dataloader state
random state
Python RNG
NumPy RNG
PyTorch RNG
Git commit
training configuration
hardware metadata
```

This is required for reproducible resume.

---

# 20. P1 — Pretraining Metrics

Every training run must record:

```text
loss
validation loss
perplexity
tokens/sec
samples/sec
learning rate
gradient norm
GPU memory
CPU RAM
checkpoint duration
data loading time
training time
tokens seen
estimated remaining tokens
```

Store machine-readable JSON/Parquet metrics.

---

# 21. P1 — Training Curriculum

Do not blindly concatenate every source.

Recommended initial curriculum:

### Stage A — Language foundation

Clean multilingual text.

### Stage B — Agriculture foundation

High-quality agricultural documents.

### Stage C — Specialized agriculture

Crops, soil, pests, diseases, irrigation, agronomy, markets, schemes.

### Stage D — Reasoning-oriented data

High-quality explanations and structured agricultural reasoning.

### Stage E — Instruction tuning

Farmer-oriented supervised examples.

### Stage F — Preference/safety tuning

DPO or equivalent, only after base model quality is established.

---

# 22. P1 — Language Mixture

Initial candidate:

```text
Hindi:   35%
Marathi: 35%
English: 30%
```

Do not permanently hard-code this.

The sampler should accept a configuration:

```yaml
language_mix:
  hi: 0.35
  mr: 0.35
  en: 0.30
```

Then evaluate:

- token efficiency
- language quality
- agricultural vocabulary
- downstream performance

and revise based on evidence.

Add a separate code-mixed evaluation bucket.

---

# 23. P1 — Agriculture Taxonomy

Create a canonical ontology shared by:

- acquisition
- corpus sampling
- graph
- retrieval
- evaluation
- training analytics

Example:

```text
Crop
Disease
Pest
Symptom
Treatment
Fertilizer
Chemical
Soil
Weather
Season
Region
State
District
Agro-climatic Zone
Irrigation
Market
Government Scheme
Variety
Practice
Growth Stage
```

Add aliases for:

```text
English
Hindi
Marathi
Romanized Marathi
Romanized Hindi
scientific names
local crop names
```

---

# 24. P1 — Dynamic vs Static Knowledge

Do not train rapidly changing information into the foundation model unless there is a strong reason.

Separate:

```text
STATIC / FOUNDATIONAL
→ model training

CURRENT / DYNAMIC
→ API + RAG
```

Examples of dynamic information:

- current weather
- current mandi prices
- current government notices
- current scheme status
- current disease alerts

These should normally be retrieved at runtime.

---

# 25. P1 — Synthetic Data Governance

Synthetic data is allowed only through a controlled pipeline:

```text
approved source
→ teacher generation
→ citation attachment
→ independent verification
→ safety filter
→ quality filter
→ deduplication
→ provenance
→ synthetic dataset manifest
→ SFT/DPO eligibility
```

Every synthetic record must include:

```json
{
  "synthetic": true,
  "teacher_model": "...",
  "source_evidence": ["..."],
  "verification_status": "verified",
  "generator_version": "..."
}
```

Do not treat synthetic output as equivalent to ground-truth human-authored data.

---

# 26. P1 — Active Learning / Expert Review

Expert time should be spent only where it has high value.

Create review prioritization based on:

```text
uncertainty
+
impact
+
novelty
+
source conflict
+
safety risk
```

High-risk examples:

- pesticide dosage
- chemical mixing
- new treatment
- disease identification
- human/animal health claims
- legal/financial advice

These require stronger review.

---

# 27. P2 — Evaluation System

The existing evaluation strategy is strong and should be extended into a dedicated:

# KrishiBench

Create:

```text
packages/eval/krishibench/
```

Evaluation groups:

```text
language
agriculture knowledge
crop disease
pest
soil
fertilizer
irrigation
weather reasoning
market reasoning
scheme reasoning
multilingual
code-mixed
safety
uncertainty
citation grounding
```

---

# 28. Golden Dataset Protection

Evaluation data must be isolated from acquisition/training.

Recommended:

```text
eval_private/
├── golden/
├── red_team/
├── safety/
├── multilingual/
└── regression/
```

The acquisition pipeline must not be able to ingest private evaluation data.

---

# 29. Model Promotion Gates

Every candidate model must pass:

```text
1. checkpoint load test
2. tokenizer compatibility
3. dataset manifest compatibility
4. parameter-count validation
5. golden evaluation
6. safety evaluation
7. language evaluation
8. agriculture evaluation
9. latency evaluation
10. memory evaluation
11. edge export test
```

Never promote based only on training loss.

---

# 30. P2 — RAG and GraphRAG

Keep the existing GraphRAG architecture.

It is valuable for:

```text
Crop
→ Disease
→ Treatment
→ Dosage
```

and other multi-hop factual queries.

The graph should remain:

```text
source-aware
confidence-aware
time-aware
region-aware
language-aware
```

Production graph should only contain approved facts.

---

# 31. P2 — Agent Layer

Keep the bounded LangGraph design:

```text
intent
→ language
→ retrieval planning
→ retrieval
→ tools
→ generation
→ safety
→ confidence
→ fallback
→ response
```

Do not allow unrestricted autonomous tool execution.

Every tool needs:

```text
timeout
retry
schema
authorization
audit
failure handling
```

---

# 32. P2 — Autonomous Improvement Flywheel

The current plan already has a good repair loop. Preserve it and connect it to the model factory:

```text
farmer interaction
→ feedback
→ evaluation signal
→ error classification
→ root cause
→ data gap
→ source discovery
→ validation
→ dataset candidate
→ training candidate
→ evaluation
→ canary
→ promote / rollback
```

Root-cause taxonomy:

```text
retrieval_failure
graph_failure
source_quality
knowledge_gap
language_gap
prompt_failure
tool_failure
model_failure
safety_failure
data_duplication
stale_information
```

The system must not automatically retrain for every failure.

First determine the root cause.

---

# 33. P2 — Data vs Model Decision Engine

Before retraining, classify:

```text
Is the failure caused by:

1. missing data?
2. bad data?
3. wrong retrieval?
4. wrong graph?
5. wrong tool?
6. prompt/orchestration?
7. model capability?
```

Only #7 should normally trigger model-training work.

This prevents unnecessary model churn.

---

# 34. Development Profiles

Do not run the entire production infrastructure during laptop model development.

Add:

```text
PROFILE=research-laptop
PROFILE=dev
PROFILE=staging
PROFILE=production
PROFILE=offline-edge
```

## Research laptop

Use:

```text
local filesystem
Parquet
DuckDB
PyTorch
tokenizer
trainer
optional Qdrant
```

## Production

Use:

```text
MinIO/S3
Iceberg
Temporal
Postgres
Neo4j/FalkorDB
Qdrant
Redis
Kubernetes
vLLM/SGLang
OTEL
Prometheus/Grafana
```

This separation keeps the development loop fast.

---

# 35. Data Storage Strategy

Do not make Iceberg a prerequisite for first 20M experiments.

Use:

```text
raw:
  immutable files

curated:
  JSONL / Parquet

training:
  Parquet token shards

analytics:
  DuckDB

production lakehouse:
  Iceberg + object storage
```

Promote to Iceberg when scale requires it.

---

# 36. Repository Changes

Recommended target structure:

```text
AGRIMIND/
├── configs/
│   ├── models/
│   │   └── krishimini_20m.yaml
│   ├── tokenizers/
│   ├── datasets/
│   ├── training/
│   └── environments/
│
├── packages/
│   ├── agrimind-kernel/
│   ├── data_kernel/
│   │   ├── sources/
│   │   ├── pipeline/
│   │   ├── refinement/
│   │   ├── validation/
│   │   ├── governance/
│   │   └── lakehouse/
│   │
│   ├── foundation_model/
│   │   ├── architecture/
│   │   ├── tokenizer/
│   │   ├── dataset/
│   │   ├── pretraining/
│   │   ├── posttraining/
│   │   └── evaluation/
│   │
│   ├── memory/
│   ├── models/
│   ├── agents/
│   └── eval/
│
├── datasets/
│   └── manifests/
│
├── eval_private/
│
├── scripts/
│   ├── discover_agri_sources.py
│   ├── build_dataset.py
│   ├── train_tokenizer.py
│   ├── evaluate_tokenizer.py
│   ├── count_parameters.py
│   ├── pretrain.py
│   ├── resume_training.py
│   └── evaluate_model.py
│
├── runs/
│   ├── acquisition/
│   ├── tokenizer/
│   ├── dataset/
│   ├── training/
│   └── evaluation/
│
└── docs/
    ├── architecture/
    ├── data/
    ├── model/
    ├── evaluation/
    └── operations/
```

---

# 37. Manifest System

Every important artifact must be immutable and addressable.

## Dataset manifest

```json
{
  "dataset_id": "ds-...",
  "version": 1,
  "source_policy_version": "...",
  "tokenizer_id": "...",
  "split_policy": "...",
  "languages": ["en", "hi", "mr"],
  "token_count": 0,
  "document_count": 0,
  "hash": "sha256:..."
}
```

## Tokenizer manifest

```json
{
  "tokenizer_id": "krishimini-tokenizer-v1",
  "vocab_size": 16000,
  "languages": ["en", "hi", "mr"],
  "normalization": "...",
  "training_corpus_manifest": "...",
  "checksum": "sha256:..."
}
```

## Model manifest

```json
{
  "model_id": "krishimini-20m-v0.1",
  "architecture": "krishimini_20m",
  "training_mode": "scratch",
  "tokenizer_manifest_id": "...",
  "dataset_manifest_id": "...",
  "git_commit": "...",
  "parameter_count": 0,
  "tokens_seen": 0,
  "eval_results": {}
}
```

---

# 38. CI Gates

Add these blocking checks:

```text
lint
type-check
unit tests
contract tests
import-layer checks
security scan
data schema tests
manifest validation
tokenizer compatibility
parameter-count validation
dataset split contamination
safety evaluation
golden evaluation
checkpoint restore test
```

For model PRs:

```text
model config
→ parameter count
→ model instantiate
→ forward pass
→ backward pass
→ checkpoint save
→ checkpoint restore
→ deterministic smoke test
```

---

# 39. Required Test Pyramid

Maintain:

```text
70% unit
15% contract
10% integration
5% E2E/golden
```

Add model-specific tests:

```text
architecture tests
tokenizer tests
dataset tests
split tests
checkpoint tests
resume tests
determinism tests
OOM handling tests
export tests
```

---

# 40. First Training Program

Do not immediately attempt the final model.

Use progressive validation.

## Run 0 — architecture smoke

```text
tiny dataset
tiny model
100–1000 steps
```

Verify:

- forward
- backward
- loss decrease
- checkpoint
- resume

## Run 1 — small corpus

Verify:

- tokenizer
- data loader
- training throughput
- validation

## Run 2 — multilingual corpus

Verify:

- language mixture
- loss by language

## Run 3 — agriculture corpus

Verify:

- agriculture perplexity
- domain evaluation

## Run 4 — KrishiMini-20M

Only after all previous runs pass.

---

# 41. Training Acceptance Criteria

A training run is not "successful" because it finished.

It must satisfy:

```text
model loads
checkpoint restores
no NaN
no unexplained loss spike
validation loss improves
language regression absent
agriculture benchmark improves
safety benchmark does not regress
tokenizer manifest matches
dataset manifest matches
parameter budget matches
```

---

# 42. Error Budget

Track separately:

```text
data error
retrieval error
graph error
tool error
generation error
language error
safety error
latency error
```

Do not use one generic "accuracy" number.

---

# 43. Priority Matrix

## P0 — Must do before scratch training

- 20M canonical target
- tokenizer redesign
- exact architecture config
- parameter-count validator
- scratch pretraining
- checkpoint/resume
- dataset manifests
- contamination-safe splits
- license/training eligibility
- robots policy correction
- corpus factory

## P1 — Must do during first serious training

- refinement engine
- factual validation
- multidimensional quality
- source graph
- token-based scheduling
- language balancing
- curriculum
- laptop controller
- training telemetry
- KrishiBench initial version

## P2 — After base model works

- GraphRAG
- agent orchestration
- SFT
- DPO
- semantic cache
- vision
- voice
- edge/cloud routing

## P3 — Production scale

- Kubernetes
- large distributed training
- Iceberg at scale
- canary fleet
- multi-region
- disaster recovery
- large-model teacher infrastructure

---

# 44. What NOT to Do

Do not:

```text
❌ start with Kubernetes complexity
❌ train on every discovered document
❌ assume public = training allowed
❌ use 64K vocabulary for a 20M target without parameter accounting
❌ train dynamic market/weather data blindly
❌ use the golden test set for training
❌ mix translated copies across train/test
❌ silently correct conflicting facts
❌ let synthetic data become unverified ground truth
❌ retrain for every user complaint
❌ optimize documents instead of tokens
❌ use training loss as the only success metric
❌ treat RAG data and foundation-training data as identical
❌ allow unsafe autonomous graph updates
```

---

# 45. New Principal Architect Rules

The coding agent must follow these rules:

### Rule 1 — Evidence before implementation

Before modifying code:

```text
inspect current repository
inspect tests
inspect configs
inspect existing contracts
identify current behavior
```

Never replace an existing implementation based only on documentation.

### Rule 2 — Preserve working paths

If an existing feature works:

```text
extend > replace
```

unless there is a documented architectural reason.

### Rule 3 — Every new feature gets:

```text
contract
implementation
unit test
integration test where applicable
observability
documentation
```

### Rule 4 — Fail loud

Missing:

- tokenizer
- checkpoint
- dataset manifest
- configuration
- license decision
- model manifest

must fail explicitly.

### Rule 5 — No silent data mutation

All transformations require lineage.

### Rule 6 — No silent model changes

Every model artifact must map to:

```text
git commit
dataset manifest
tokenizer manifest
training configuration
```

---

# 46. Coding Agent Execution Protocol

When the coding agent receives a task, it should execute:

```text
STEP 1
Read repository structure.

STEP 2
Find relevant implementation.

STEP 3
Read tests.

STEP 4
Compare implementation with this plan.

STEP 5
Create a gap list.

STEP 6
Implement the smallest coherent change.

STEP 7
Add/update tests.

STEP 8
Run targeted tests.

STEP 9
Run relevant integration tests.

STEP 10
Run lint/type checks.

STEP 11
Update manifest/documentation.

STEP 12
Report:
  - changed files
  - behavior changed
  - tests
  - remaining risks
  - next recommended step
```

The agent must not perform broad rewrites without first mapping dependencies.

---

# 47. First Implementation Sprint

Recommended order:

## Sprint 1

```text
1. Create KrishiMini config
2. Create parameter-count utility
3. Create tokenizer package
4. Remove 64K hard dependency
5. Add tokenizer benchmark
6. Add tokenizer manifest
7. Add training manifest schema
```

## Sprint 2

```text
1. Corpus refinement
2. Training eligibility
3. dataset split engine
4. contamination checks
5. Parquet token shards
6. dataset statistics
```

## Sprint 3

```text
1. scratch model
2. trainer
3. checkpoint
4. resume
5. laptop controller
6. training telemetry
```

## Sprint 4

```text
1. tiny-model training
2. checkpoint restore tests
3. multilingual training test
4. agriculture corpus test
5. initial KrishiBench
```

## Sprint 5

```text
1. KrishiMini-20M training
2. validation
3. evaluation
4. error analysis
5. corpus gap discovery
```

Only after this should the full autonomous retraining loop be connected.

---

# 48. Definition of Done — KrishiMini-20M

The first model is complete only when:

```text
[ ] exact parameter count verified
[ ] tokenizer manifest immutable
[ ] dataset manifest immutable
[ ] scratch initialization confirmed
[ ] no pretrained base checkpoint
[ ] multilingual corpus validated
[ ] agriculture corpus validated
[ ] train/test contamination checked
[ ] checkpoint restore works
[ ] interrupted training resumes
[ ] validation metrics recorded
[ ] KrishiBench exists
[ ] safety benchmark exists
[ ] Marathi benchmark exists
[ ] Hindi benchmark exists
[ ] English benchmark exists
[ ] code-mixed benchmark exists
[ ] model manifest generated
[ ] artifact checksum recorded
[ ] inference smoke test passes
[ ] regression report generated
```

---

# 49. Definition of Done — Autonomous Data Flywheel

The autonomous system is complete when:

```text
[ ] source discovery is automated
[ ] source governance is automated
[ ] training eligibility is enforced
[ ] acquisition is run-scoped
[ ] raw data is immutable
[ ] refinement is lineage-aware
[ ] factual conflicts are detectable
[ ] dataset generation is reproducible
[ ] tokenizer versions are immutable
[ ] model training is reproducible
[ ] evaluation is automatic
[ ] failures are classified
[ ] data gaps are identified
[ ] new sources can be discovered
[ ] candidate improvements are generated
[ ] unsafe changes require human approval
[ ] model promotion is evaluation-gated
[ ] rollback is automatic
```

---

# 50. Final Principal Architect Recommendation

The most important architectural decision is:

> **Do not build AGRIMIND as "a chatbot with an 18/20M model attached." Build it as a closed-loop agricultural intelligence system where the data factory, foundation model factory, knowledge factory, evaluation factory, and safety factory continuously improve each other.**

The moat should become:

```text
             ┌──────────────────────┐
             │ Autonomous Discovery │
             └──────────┬───────────┘
                        ↓
             ┌──────────────────────┐
             │ Governed Agri Corpus │
             └──────────┬───────────┘
                        ↓
             ┌──────────────────────┐
             │ KrishiMini Foundation│
             │       Model          │
             └──────────┬───────────┘
                        ↓
             ┌──────────────────────┐
             │ RAG + Knowledge Graph│
             └──────────┬───────────┘
                        ↓
             ┌──────────────────────┐
             │ Farmer Intelligence  │
             └──────────┬───────────┘
                        ↓
             ┌──────────────────────┐
             │ Feedback / Evaluation│
             └──────────┬───────────┘
                        ↓
             ┌──────────────────────┐
             │ Root Cause / Data Gap│
             └──────────┬───────────┘
                        ↓
                  back to discovery
```

The existing AGRIMIND plan already has strong foundations for provenance, safety, GraphRAG, evaluation, autonomous repair, and production infrastructure. The highest-impact work now is to make the **data-to-foundation-model path concrete, reproducible, parameter-budget-aware, legally governed, contamination-safe, and laptop-executable**.

That is the path I recommend for the first `KrishiMini-20M` model.
