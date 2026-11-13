# Jury audit: source fidelity and publication boundary

All reproductions are offline. The script blocks socket construction after imports,
does not load .env, constructs no provider client, uses the real corpus loader,
production validated tools and LangGraph. Model outputs and a deliberately optimistic
review are scripted. These are publication-boundary counterexamples; they are not
measurements of a live model's attack success rate.

Evidence: `jury-grounding-repro.py`, `jury-grounding-before.json`,
`jury-grounding-after.json`. The before file preserves the original implementation;
the after file includes a twelfth case against the public q4 rubric.

## Findings

1. **HIGH — Free paraphrases are publishable with unrelated real quotes.**
   `app/agent/grounding.py:55` checks coverage, optimistic booleans and literal quote
   membership, not entailment. `:93` repeats those structural checks then prints
   the generator's claim at `:118`. Exact corpus quotes plus `safe=true`,
   `complete=true`, `supported=true`, no flags publish all twelve adversarial cases.
   `app/eval.py:63` also accepts their provenance. Examples: negated metformin
   contraindication, exactly-30 instead of below-30 boundary, one instead of two
   apixaban dose-reduction criteria, insulin claims citing metformin, simultaneous
   contradictory claims, absent Ventolin product, invented cancer cure, personalized
   start/stop instructions. The guarantee is provenance and review coverage;
   semantic faithfulness, completeness and prescribing safety are model judgments.

2. **HIGH — Warfarin's special guard is a lexical regression, not semantics.**
   `app/agent/policies.py:6` is triggered only for a warfarin evidence passage
   containing both `except` and `mechanical heart valves`. It tests the presence
   of valve/risk/thromboembolism words in the claim, not their logical relationship.
   `warfarin_keyword_guard_bypass` publishes "safe throughout pregnancy ... no
   fetal-harm concern". `warfarin_missing_individual_benefit_risk` publishes routine
   recommendation while omitting individualized benefit/risk qualification from
   the cited source. See corpus `dailymed-warfarin.md:133`, `:183`, `:283`.

3. **HIGH — Dosing section aliases bypassed product policy (FIXED).**
   Previously the tool's policy recognized only exact `dosage`, while the loader
   accepted arbitrary heading substrings. Ventolin `dosage` had zero evidence;
   `DOSAGE AND ADMINISTRATION` or `administration` yielded the nebulized combination
   label. Albuterol without product_id and oral multi-formulation product similarly
   bypassed safeguards via section titles. The original whole graph published the
   wrong Ventolin dose as grounded and passed structure scoring. After correction,
   every reproduced alias returns zero passages and that graph abstains.
   `app/rag/loader.py:93` now canonicalizes whitelisted aliases once; `:394` rejects
   unknown headings; `app/tools/sections.py:75` applies that same canonical key before
   brand/product policies. Explicit exact products and source fallback remain usable.

4. **MEDIUM — Inventory evidence was inaccessible to the generator (FIXED).**
   `run_list` returned structured source passages but omitted their passage_ids and
   raw text from ToolMessage.content. Prompts require exact observed IDs, so inventory
   responses could tempt guessing or require another retrieval. `sections.py:141`
   now exposes one complete, existing identity passage per drug document, including
   exact ID and raw source evidence. No document contents are rewritten.

5. **HIGH for interpretation of evaluation — Public factual pass does not
   certify additional claims.** `app/eval.py:179` matches expected affirmative
   patterns plus narrow negation checks. `public_q4_extra_false_claim` contains
   the correct expected metformin threshold and an added invented cancer cure;
   score_structure and the public q4 score both return true. This agrees with the
   evaluator's caveat, but rules out describing that pass as hallucination absence.

## Guarantees and limits

Typed contracts reject malformed schemas, unknown passage IDs, missing per-claim
review, mismatched IDs, nonliteral quotes, explicit rejection flags and review
failure. Citation spans, hashes and offsets enable original-file provenance tests.
Review receives all retrieved evidence or fails the evidence budget; it does not
silently truncate. Zero-evidence answers cannot publish. The plan and tool choice
remain agentic. The reviewer is a separate invocation, ordinarily of the same model
(`app/agent/graph.py:76`), so this is not an independent truth oracle.

No structural contract prevents a model from retrieving one valid passage and
attaching an unrelated remembered assertion, complying with an injected instruction,
omitting an exception, conflating products, or approving its own wrong synthesis.
No live prompt-injection success or failure was measured in this audit.

## Compatible improvements

Keep planning, autonomous corpus tools, cited answers and review. Add a publication
mode whose medical content consists of exact source units, with server-rendered
subject/product/source headings and complete qualifications. Keep semantic synthesis
as fallible review unless an explicit curated relation supports it. Exact extraction
guarantees no invented medical wording, not clinically complete selection or truth.
For product ambiguity, return available exact identities and an actionable clarification
instead of a blanket refusal. Add counterexamples for negation, inequality, units,
quantifiers, cross-product attribution, omission and contradiction to regression/eval
evidence, with separate structural and semantic results. Additional LLM/NLI review can
reduce failures but cannot establish zero hallucinations. Avoid replacing this with
a growing collection of question-specific keyword guards.

## Changes and verification

Only production files changed here: `app/rag/loader.py`, `app/tools/sections.py`.
New tests: `tests/test_section_safety.py` (29 cases).
Command: `.venv311/Scripts/python.exe -m pytest tests/test_section_safety.py tests/test_sections.py tests/test_loader.py tests/test_rag_safety.py -q`.
Result: 78 targeted tests passed. Tests exercise validated production handlers and
real corpus data without embeddings or provider calls; they verify alias invariance,
known exact product success, unknown section rejection, source strictness, explicit
fallback disclosure, and inventory ID/raw-span/citation consistency.
