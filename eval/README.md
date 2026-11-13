# Evaluation contracts

Historical responses with `response_mode=synthesis` keep the existing public-question
smoke rubric in `app.eval`. Their scores are not silently relabeled as extractive
scores. New `source_excerpts` responses are dispatched to `eval.grader`.

The new rubric tests three distinct properties:

1. **Source fidelity and context.** Every public claim must equal exactly one cited
   source span. The grader reads the original bytes, recalculates SHA-256 and IDs,
   and checks character offsets. It independently identifies full Markdown bodies,
   or full glossary entries, so a real but truncated substring does not pass.
   Drug, source, product and section metadata are checked. Every public claim needs
   an explicit `entailed` source-provenance check and a literal supporting quote.
2. **Controlled publication.** Text outside the excerpts must be the approved server
   introduction, source identities, comparison limitation, verified word overlap,
   qualified numerical observations and disclaimer. Unverified prose appended to a
   valid answer, hidden in a title/diagnostic, or emitted during abstention fails.
3. **Coverage of the four public questions.** These requirements were specified
   from the question and source documents, rather than inferred from whichever
   model output happened to pass. They are intentionally stricter than source-name
   presence or keyword counts in arbitrary prose.

| Question | Required coverage |
|---|---|
| Warfarin contraindications | Complete contraindications context, pregnancy with the mechanical-valve/high-risk exception, and the other principal categories, rather than pregnancy alone. |
| Warfarin/apixaban comparison | Both contraindications contexts, bleeding and hypersensitivity as literally shared terms, pregnancy qualification, and an explicit restriction to wording. Two documents without any comparison do not pass. Literal overlap is not clinical equivalence, and absent wording is not proof of clinical safety or exclusivity. |
| Warfarin/sertraline interaction | Evidence for the association's bleeding risk **and** an INR-monitoring recommendation, with both expected source documents. A glossary definition of INR is insufficient. |
| Metformin and eGFR 25 | Source contraindication threshold below 30 with its complete normalized unit, plus a server-calculated `25 < 30` observation. Its question value/unit and source value/unit must match the actual input and source text; qualification about identical units, body-surface normalization and patient context must remain. It is not an unqualified patient-specific contraindication decision. |

Numerical relations are independently recomputed with `Decimal`. Negative tests
change the comparator, threshold, input, units, qualification and passage identity
while keeping the visible answer consistent with the corrupted metadata. General
boundary tests cover values below, equal to and above the source threshold. This
prevents the renderer and evaluator from agreeing on the same unchecked string.

The tests retain historical prose behavior and add full-source positive fixtures,
authentic but incomplete contexts, irrelevant authentic sections, missing comparison,
missing interaction dimensions, altered product metadata, free-text leaks, and an
optimistic reviewer explicitly returning `verdict=entailed` for a false draft.

Run the offline tests with:

```text
python -B -m pytest tests/test_eval.py -p no:cacheprovider
```

Limitations: this is a finite acceptance suite. It does not clinically validate the
source documents, demonstrate universal relevance of every selected passage, prove
coverage of unseen compound questions, or measure independent human comprehension
of the comparison UI. General scenarios without a public factual rubric measure
structure and expected status, not semantic completeness. Record these dimensions
separately, preserve failures and abstentions, and do not merge selective retests
into an artificially perfect full-run score.
