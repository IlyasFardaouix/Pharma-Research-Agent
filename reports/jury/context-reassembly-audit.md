# Complete source-context evidence

The indexed fragments remain unchanged: 556 chunks, with identical IDs and
embedding text sequence before/after. Captured proof:
`jury-context-baseline.json`, `jury-context-proof.json`.

The loader records optional complete-context start/end offsets for each Markdown
body before size splitting. `app/rag/context.py` reassembles only original
contiguous fragments with matching full document SHA-256, canonical span IDs,
source/heading/product identity and valid lengths. It concatenates exact raw text
without inserted whitespace or normalization. The resulting ID covers the complete
source span. The source files, indexed text, chunk IDs and embeddings are untouched.

Production `CorpusIndex.search_text` and `get_section_passages` expose complete
contexts. Tools also protect corpus facades and the inventory's direct chunk access.
Duplicate contexts collapse to their highest semantic score, keeping deterministic
ordering for ties. Already-complete glossary lookup entries have no context bounds
and retain their exact text and IDs.

Missing, overlapping, inconsistent or oversized contexts are explicit errors.
The default per-context limit is 60000 characters, following configured
max_evidence_chars in the production corpus. Tools return no passages/citations for
the failing batch and explain the error. No partial or truncated batch is exposed.

Real reproduced cut: `dailymed-atorvastatin@6ea369098461:25611-27535` ends
`pregnancies is 2 `; the next indexed fragment starts `to 4% and 15 to 20%`.
Its evidence is now `dailymed-atorvastatin@6ea369098461:25611-30345`, 4734 exact
source characters, including `is 2 to 4% and 15 to 20%, respectively.`.

Verification: 104 targeted tests passed, entirely offline:

```
.venv311/Scripts/python.exe -m pytest tests/test_context.py tests/test_section_safety.py tests/test_sections.py tests/test_loader.py tests/test_rag_safety.py tests/test_index.py tests/test_glossary.py -q
```

18 new context cases cover the real cut, production tools, deduplication/best
ranking, Unicode and CRLF offsets, recomputed original-file SHA and raw span for
every context, missing first/middle/last fragments, overlap, identity/hash/ID/text
mismatch, an exact limit versus one-character overflow, explicit facade errors,
optional metadata, and unchanged complete glossary entries. No provider client or
real embeddings were used.

This guarantees complete evidence within a heading-bounded source body. It does
not guarantee that the selected heading contains every qualification in the full
document, or that exact source extraction establishes a clinical conclusion.
