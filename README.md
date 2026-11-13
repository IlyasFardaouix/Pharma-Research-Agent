# Pharma Research Agent

Public repository: [IlyasFardaouix/Pharma-Research-Agent](https://github.com/IlyasFardaouix/Pharma-Research-Agent).

A research assistant for a fixed local pharmacology corpus: DailyMed labels,
MedlinePlus monographs and a glossary. It plans a search, chooses its own corpus
tools, reviews the evidence and publishes **literal source excerpts with citations**.

The public response mode is `source_excerpts`. The agent selects each context with
a short verbatim focus quote; it does not need to compose a clinical paraphrase.
The server publishes the complete selected source contexts. This preserves source
wording while keeping the agent's planning, retrieval and review workflow.

> This is a technical demonstration, not medical advice. The corpus is fixed and
> is not updated automatically. Exact wording does not guarantee that the selected
> sources are relevant, complete or clinically sufficient.

Open **http://localhost:8000** after starting the service. See [DEMO.md](DEMO.md) for
simple user instructions and an optional ten-minute walkthrough.

## How an answer is produced

```text
POST /ask → internal plan → agent chooses corpus tools
                              ↓
                  complete source contexts + exact IDs
                              ↓
                  compact typed context selection
                              ↓
                  full-context review ↔ bounded revision
                              ↓
                  server publishes source excerpts or abstains
```

- **Plan and tools.** LangGraph lets the model decompose compound questions and
  choose among four tools. There is no question-to-tool keyword router.
- **Retrieval.** Cosine similarity runs in a NumPy matrix over **556 indexed
  fragments from 21 unchanged documents**. Embeddings are cached. Before a result
  reaches the agent or reviewer, contiguous fragments from the same heading-bounded
  Markdown body are reassembled into one complete context. No text is rewritten
  and no new embeddings are required for this step.
- **Selection and review.** The internal `DraftAnswer` shape is retained, but each
  `claims.text` is a verbatim focus quote of 12–1800 characters from exactly one
  retrieved passage ID. It locates evidence; it is not a synthesized medical
  assertion. The critic judges each full context's relevance and applicability,
  and the selected contexts' collective coverage of the question. A focus quote
  does not need to reproduce all qualifications already present in its context.
  Review supplies exact evidence and an explicit `entailed`, `contradicted` or
  `insufficient` verdict. Approval requires a complete, safe, supported selection
  without flags. `entailed` here records a justified documentary selection; this
  remains a fallible judgment, ordinarily from the same configured model.
- **Publication.** The server validates the links again, then copies the complete
  selected raw source contexts into public `claims` and `citations`. It does not
  shorten a source to the focus quote or the critic's evidence quote.
  Missing, inconsistent or oversized evidence is refused rather than truncated.
- **Inspection.** Each citation includes the file, section, product when documented,
  SHA-256, character offsets and canonical passage ID. A source link opens the
  original document through `/sources/{filename}?sha256=...`; a changed fingerprint
  is refused. The public plan is a neutral process summary, not the model's internal
  research instructions or an additional source of medical assertions.
  The public trace retains the actual tool sequence; free search queries and
  partial result summaries remain internal so they cannot masquerade as findings.

| Corpus tool | Use |
|---|---|
| `search_corpus(query, k?, drug?)` | Semantic search for open questions. |
| `get_drug_section(drug, section, source?, product_id?, allow_fallback?)` | Labelled section lookup; strict source by default and explicit fallback. Dosage aliases share the same brand/product checks. |
| `lookup_glossary(term)` | Exact glossary entry; unavailable terms are not defined from memory. |
| `list_drugs()` | Available documents and product identities, with visible IDs and source evidence. |

For comparisons, the output presents the relevant source wording with its scope:
absence from one selected list does not establish clinical safety or exclusivity.
For an explicit eGFR input and a literal source threshold, a separate numerical
observation may show a relation such as `25 < 30`. Both units are retained. This is
conditional arithmetic, with no silent conversion, body-surface normalization or
clinical eligibility decision.

## Stack and structure

- **Python 3.11, FastAPI and Uvicorn:** HTTP API and the static interface.
- **LangGraph:** explicit tool and revision transitions with bounded execution.
- **langchain-openai:** configured OpenAI-compatible chat and embedding endpoints,
  including the assignment's LiteLLM proxy.
- **NumPy:** in-memory similarity at this corpus size, without an external vector DB.
- **Pydantic:** typed draft, review, citation and public response contracts.

```text
app/main.py          /health, /ask, source documents, frontend
app/answer.py        internal selection and public evidence contracts
app/models.py        HTTP schemas and safe public diagnostics
app/runtime.py       startup, admission, workers
app/execution.py     per-request budgets and cancellation
app/http_limits.py   request-body size and receive deadline
app/rag/             loader, embeddings/cache, index, context reassembly
app/tools/           search, sections, glossary, inventory
app/agent/           planning, tools, review, fidelity checks, numeric observation, render
app/eval.py          generic provenance checks and narrow public factual checks
frontend/index.html  question, source excerpts, citations and execution details
eval/                public questions and additional scenarios
tests/               network-free regression tests
```

[ARCHITECTURE.md](ARCHITECTURE.md) explains the requirement matrix, design choices
and the precise limits of the guarantees.

## Configuration

Copy [`.env.example`](.env.example) to `.env` and fill in authorized provider values.
Keep that file local. The application reads configuration from the environment.

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | empty | Required to use the configured provider. |
| `OPENAI_BASE_URL` | provider default | OpenAI-compatible proxy URL, including `/v1` when required. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model allowed by the configured provider. |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model. |
| `EMBEDDING_DIMENSIONS`, `EMBEDDING_CACHE_VERSION` | unset, `v1` | Optional dimensions and cache version. |
| `CORPUS_DIR`, `CACHE_DIR` | project directories | Local source and cache paths; Docker cache is `/app/.cache`. |
| `TOP_K`, `MAX_REVISIONS`, `TEMPERATURE` | `5`, `2`, unset | Retrieval and bounded review tuning. |
| `REQUEST_TIMEOUT`, `ANSWER_TIMEOUT` | `45`, `180` seconds | Per provider call and whole answer. |
| `MAX_CONCURRENT_REQUESTS`, `MAX_TOOL_CALLS`, `MAX_LLM_CALLS` | `2`, `24`, `16` | Resource limits. |
| `MAX_COMPLETION_TOKENS`, `MAX_EVIDENCE_CHARS`, `MAX_CONTEXT_CHARS` | `4096`, `60000`, `100000` | Generation and complete-evidence budgets. |

The container includes the code, corpus and frontend. Chat, query embeddings and
initial document embeddings require the external provider. Reusing a warm cache
can still require a short provider check of vector dimensions. `/health` reports
local initialization and configuration, not continuous provider availability.

## Start with Docker

```powershell
docker build -t agent .
docker run --name pharma-demo --rm -p 127.0.0.1:8000:8000 --env-file .env agent
```

Open **http://localhost:8000**. To keep the embedding cache between runs, add
`-v pharma-cache:/app/.cache` to `docker run`.

```powershell
Invoke-RestMethod http://localhost:8000/health
$body = @{ question = 'Define INR using only the provided local glossary.' } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/ask -Method Post -ContentType application/json -Body $body -TimeoutSec 200
```

The response includes `status`, `response_mode`, `answer`, `claims`, `citations`,
`grounding`, `plan`, `tool_trace`, `numeric_comparisons` and the disclaimer.
`grounding.scope = source_provenance` describes literal source publication; it is
not a certificate of clinical truth.

## Start locally

```powershell
python3.11 -m venv .venv311
.venv311\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

On systems using a Unix shell, activate with `source .venv311/bin/activate`.
Bind the demo to localhost. Public hosting needs deployment-specific access control
and transport protection. Publishing this repository does not expose the local API.

## Verify the current version

```powershell
python -B -m pytest -p no:cacheprovider
```

The tests use local corpus data and scripted provider substitutes. The evaluator
below makes real provider calls and needs the configured key:

```powershell
python -m app.eval --output .cache/eval-latest.json
python -m app.eval --questions eval/scenarios.yaml --output .cache/eval-scenarios.json
```

Generic checks cover status, passage links, literal spans, hashes, offsets and review
coverage. The four public questions add limited factual checks: warfarin
contraindications, warfarin/apixaban comparison, warfarin/sertraline evidence and
metformin/eGFR. Passing these checks does not prove every interpretation correct.

**Measured validation:** 271 offline tests, 87 Edge checks and 14 Docker/HTTP
checks passed. The real-provider campaign has 11 answers and four expected
abstentions. Its raw score was 14/15; the same answers score 15/15 after fixing a
documented Q4 notation false negative, without a new model call or weaker criteria.
See [VALIDATION.md](VALIDATION.md) and the retained evidence in `reports/jury/`.
Exact wording does not guarantee relevance, completeness or clinical correctness.

With the server running and Edge installed, the browser smoke script is:

```powershell
uv tool run --from playwright python -B scripts/browser_smoke.py
```

It intercepts model calls to exercise the UI; a live provider check is separate.

## Delivery and AI transparency

[DEMO.md](DEMO.md) provides the ten-minute walkthrough and
[ARCHITECTURE.md](ARCHITECTURE.md) maps the assignment requirements to the code.
[`.claude/CLAUDE.md`](.claude/CLAUDE.md) documents the AI
working configuration and the retained original implementation plan.

The repository includes the code, original corpus, frontend, Dockerfile, pinned
dependencies, tests, evaluation cases, essential documentation and project AI
configuration. Secrets, caches, local environments, the confidential assignment,
intermediate audits and PDF-authoring tools are excluded from the current tree.
Final evidence is retained with its original failures and documented regrading;
older development records remain available in Git history.

The assignment requires emailing the public repository link and a short approach
summary to the recruitment contact before **13 November 2026, 23:59 Casablanca**.
The last commit pushed before that deadline is assessed. Repository publication
does not send that email. A ten-minute presentation is also required; slides are
optional and a code walkthrough is accepted. See [DEMO.md](DEMO.md).
