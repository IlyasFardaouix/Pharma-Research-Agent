# Project: Pharma Research Agent

This file is the project-scoped AI working configuration, prepared for inclusion
with the assignment deliverable. The retained [original plan](plan.md) records the
initial implementation approach. It is historical; [ARCHITECTURE.md](../ARCHITECTURE.md)
describes the current `source_excerpts` contract and requirement matrix.

## Product and workflow

The service researches a fixed local corpus of DailyMed labels, MedlinePlus
monographs and a glossary. It exposes `/health`, `/ask`, a static frontend and
hash-bound source-document links.

The LangGraph flow remains agentic:

```text
internal plan → agent chooses corpus tools → complete-context evidence
             → literal focus-quote selection → full-context review ↔ revision
             → server publishes literal source excerpts or abstains
```

The user's current preference is **exact source excerpts first**. Preserve useful
planning, autonomous tool choice and review; do not replace the product with a
blanket refusal workflow. The server publishes selected complete raw contexts,
not a synthesized medical paraphrase or only a short critic quote. The agent's
selection protocol must match that public result.

## Implementation conventions

- Use Python 3.11 and the dependencies declared in `pyproject.toml`, hash-locked in
  `requirements.txt` and `requirements-dev.txt`.
- Read provider configuration from `OPENAI_*` settings. Keep credentials in the
  local environment; never hardcode them or print provider secrets.
- Keep the 21 original corpus files unchanged. Indexed fragments remain **556**
  with unchanged text and IDs; context metadata does not invalidate their embedding
  cache. Reassembly occurs after retrieval and before evidence reaches the model.
- `app/rag/context.py` joins contiguous fragments of one Markdown body without
  rewriting whitespace, Unicode or line endings. Require matching SHA-256,
  canonical IDs, offsets and source/product identity. Refuse missing, overlapping
  or oversized contexts explicitly instead of truncating them.
- Context bounds are optional for fixtures and already complete glossary entries.
  Do not broaden a glossary lookup result to the entire glossary.
- Canonicalize section aliases before brand/product policies. Source selection is
  strict unless fallback is explicitly requested; an absent product's dose must
  not be borrowed from a different route, formulation or combination.
- Preserve the `DraftAnswer` JSON shape, but treat internal claims as context
  selections: each `text` is a verbatim contiguous focus quote of 12–1800 characters
  from exactly one retrieved passage ID. Do not require medical paraphrasing,
  one sentence or one proposition. A literal focus can contain several sentences
  or list items; all context qualifications need not fit inside that short focus.
- Review each SELECTED FULL CONTEXT for relevance, drug/product/route/population
  applicability and qualifications, then review the union of those contexts for
  coverage of every requested documentary topic. Do not assess completeness using
  only focus quotes or evidence that was retrieved but not selected. Require an
  additional referenced section when necessary for a material qualification.
- Keep explicit `entailed` / `contradicted` / `insufficient` verdicts and exact
  evidence from each selection's same passage. `entailed` with `supported=true`
  means a justified documentary selection; complete/safe review and no unresolved
  flags are also required. None of these model judgments proves clinical truth.
- In public `source_excerpts` responses, each claim is one literal complete context,
  equal to its citation excerpt, with `grounding.scope=source_provenance`. The
  focus quote is only a locator, never a shortened public answer. The public plan
  is a neutral process summary; free internal planning and unverified
  review diagnostics are not extra medical evidence.
- Numerical eGFR observations are conditional arithmetic over explicit input and
  source values. Retain both units and the normalization caveat. Do not infer
  medication eligibility, prescribe treatment or silently convert units.
- Source links include the document SHA-256. `/sources/{filename}?sha256=...` must
  serve only the corresponding corpus file version; changed hashes and path
  escapes are refused. Dynamic UI content is rendered as text.

## Code map

| Area | Files |
|---|---|
| Retrieval and context | `app/rag/loader.py`, `context.py`, `index.py`, `embeddings.py` |
| Corpus tools | `app/tools/search.py`, `sections.py`, `glossary.py`, `registry.py` |
| Agent and publication | `app/agent/`, `app/answer.py`, `app/models.py` |
| Runtime and HTTP limits | `app/runtime.py`, `execution.py`, `http_limits.py`, `main.py` |
| User interface | `frontend/index.html` |
| Evaluation | `app/eval.py`, `eval/questions.yaml`, `eval/scenarios.yaml`, `tests/` |

## Verification and limits

Keep `pytest` network-free, using local data and provider substitutes. Run:

```text
python -B -m pytest -p no:cacheprovider
```

Real model evaluations and browser calls to a live provider are separate checks;
record their configuration, timing and failures honestly. Verify the final Docker
image and UI after changes to the public contract. The grader injects its own `.env`
and expects the container to contain the code, corpus and frontend. Model and
embedding services remain external dependencies.

Consolidated validation evidence is under `reports/jury/`: 271 offline tests,
87 browser checks, 14 Docker/HTTP checks, and 15/15 real-provider cases after a
documented evaluator notation fix (14/15 raw retained). The former **144 tests**, **18 browser checks** and **6/7 complete
model run** are historical results from the earlier contract, with a separate
comparison retest. Do not relabel or combine them as a pass for the current version.
Check or regenerate delivery reports, screenshots and archives after validation.

Exact source wording and verified provenance prevent invented public medical
wording. They do not certify relevance, completeness, up-to-date source material,
clinical interpretation or patient safety. A growing set of keyword guards or
another LLM review does not establish a universal no-hallucination guarantee.

## AI assistance and accountability

The initial implementation used Claude Code with an Opus model and the retained
project plan. Later hardening used OpenAI Codex, including separate adversarial
review of grounding, products, runtime and interface behavior. Project-scoped
retrieval requires no MCP server; it uses the supplied local corpus.
The requested technical jury used GPT-6 Astra in a separate context. It later
contributed the extractive grader and its tests; this is not blind external
evaluation. Its initial and final critiques, and all campaign corrections, are
preserved under reports/jury/.

The human author remains responsible for explaining and verifying the deliverable,
including AI-assisted changes. This revision prepares a local result for validation;
it does not publish a Git repository or deploy a public service.
