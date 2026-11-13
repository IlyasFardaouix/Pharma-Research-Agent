"""Conservative smoke test for four public questions; not clinical validation."""

from __future__ import annotations

import sys
import re
import argparse
import json
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import ROOT_DIR, get_settings
from app.models import AnswerResponse

QUESTIONS_FILE = ROOT_DIR / "eval" / "questions.yaml"
_FILE = r"(?:dailymed|medlineplus)-[a-z0-9-]+\.md"
_SECTION = r"(?:,\s*(?:\d+(?:\.\d+)*\s+)?[A-Z][A-Z0-9 /:-]{2,90})?"
_REFERENCE = _FILE + _SECTION
INLINE = re.compile(rf"\({_REFERENCE}(?:\s*[;,]\s*{_REFERENCE})*\)", re.I)
INLINE_FILE = re.compile(_FILE, re.I)
SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])|(?<=\))\s+(?=[A-Z0-9])|\n+")
CONTRA_NEGATED = re.compile(
    r"\b(?:not|never)\s+(?:a\s+)?contraindicat\w*\b"
    r"|\bno\s+contraindicat\w*\b(?!\s+(?:unique|specific)\b)",
    re.I,
)
RISK_NEGATED = re.compile(
    r"\b(?:does\s+not|do\s+not|doesn.t|don.t|not)\s+(?:increas\w*|raise|heighten|add\s+to)\b"
    r"|\bno\s+(?:increas\w*|additional|greater|higher)\s+(?:bleed\w*\s+)?risk\b",
    re.I,
)
MONITOR_NEGATED = re.compile(
    r"\b(?:INR\s+)?monitor(?:ing)?\s+(?:is\s+)?not\s+recommend\w*\b"
    r"|\b(?:do\s+not|don.t|no\s+need\s+to)\s+monitor\w*\b"
    r"|\bno\s+(?:INR\s+)?monitoring\s+(?:needed|required|recommended)\b",
    re.I,
)
EXCEPTION_NEGATED = re.compile(r"\bno\s+(?:high[- ]risk\s+)?exception\b|\bexception\s+does\s+not\s+apply\b", re.I)


def _negates(check_id: str, claim: str) -> bool:
    if check_id == "high_risk_mechanical_valve_exception":
        pattern = EXCEPTION_NEGATED
    elif check_id == "increased_bleeding_risk":
        pattern = RISK_NEGATED
    elif check_id == "monitor_inr":
        pattern = MONITOR_NEGATED
    else:
        pattern = CONTRA_NEGATED
    return bool(pattern.search(claim))


@dataclass(frozen=True)
class Score:
    ok: bool
    failures: tuple[str, ...]


def score_structure(response: AnswerResponse, corpus_dir: Path | None = None) -> Score:
    """Check evidence links for any question, without a medical keyword rubric.

    Passage IDs and exact quotes establish provenance and review coverage. They
    do not prove that the cited passage entails a paraphrased clinical claim.
    """
    failures: list[str] = []
    status = getattr(response, "status", None)
    claims = list(getattr(response, "claims", []))
    citations = list(response.citations)
    report = response.grounding
    if status == "abstained":
        if claims or citations:
            failures.append("abstention contains claims or citations")
        if report is None or report.supported is not False or report.verdict != "ungrounded":
            failures.append("abstention lacks an unsupported grounding verdict")
        return Score(not failures, tuple(failures))
    if status != "answered":
        failures.append("unknown answer status")
    if not claims:
        failures.append("answered response has no claims")
    if report is None or report.verdict not in {"grounded", "revised"} or report.supported is not True or report.flags:
        failures.append("grounding is absent, unsupported, or flagged")

    claim_ids = [claim.id for claim in claims]
    if len(set(claim_ids)) != len(claim_ids) or any(not cid for cid in claim_ids):
        failures.append("claim IDs are empty or duplicated")
    by_passage: dict[str, set[str]] = {}
    for claim in claims:
        if not claim.text.strip() or claim.text not in response.answer:
            failures.append(f"claim {claim.id} is empty or absent from rendered answer")
        if not claim.passage_ids or len(set(claim.passage_ids)) != len(claim.passage_ids):
            failures.append(f"claim {claim.id} has no unique passage IDs")
        for pid in claim.passage_ids:
            by_passage.setdefault(pid, set()).add(claim.id)

    citation_ids = [citation.passage_id for citation in citations]
    if any(not pid for pid in citation_ids) or len(set(citation_ids)) != len(citation_ids):
        failures.append("citation passage IDs are empty or duplicated")
    by_citation = {citation.passage_id: citation for citation in citations if citation.passage_id}
    if set(by_citation) != set(by_passage):
        failures.append("citation passage IDs do not match claim passage IDs")
    for pid, citation in by_citation.items():
        if not citation.excerpt:
            failures.append(f"citation {pid} has no exact passage excerpt")
        linked = list(getattr(citation, "claim_ids", []))
        if len(set(linked)) != len(linked) or set(linked) != by_passage.get(pid, set()):
            failures.append(f"citation {pid} has incorrect claim links")
        if corpus_dir is not None:
            file_name = citation.file
            if Path(file_name).name != file_name or not file_name.endswith((".md", ".txt")):
                failures.append(f"citation {pid} has an invalid corpus filename")
                continue
            try:
                source_bytes = (corpus_dir / file_name).read_bytes()
                document = source_bytes.decode("utf-8")
                start, end = citation.start_offset, citation.end_offset
                digest = hashlib.sha256(source_bytes).hexdigest()
                expected_pid = f"{Path(file_name).stem}@{digest[:12]}:{start}-{end}"
                if (citation.document_sha256 != digest or not isinstance(start, int)
                        or not isinstance(end, int) or start < 0 or end <= start
                        or end > len(document) or document[start:end] != citation.excerpt
                        or pid != expected_pid):
                    failures.append(f"citation {pid} does not match the original corpus span")
            except (OSError, UnicodeError):
                failures.append(f"citation {pid} source document is unavailable")

    checks = list(getattr(report, "claim_checks", [])) if report is not None else []
    check_ids = [check.claim_id for check in checks]
    if len(set(check_ids)) != len(check_ids) or set(check_ids) != set(claim_ids):
        failures.append("review does not cover each claim exactly once")
    by_claim = {claim.id: claim for claim in claims}
    for check in checks:
        claim = by_claim.get(check.claim_id)
        if check.supported is not True or check.flags:
            failures.append(f"claim {check.claim_id} is unsupported or flagged")
        if claim is None:
            continue
        evidence_by_pid: dict[str, list[str]] = {}
        for evidence in check.evidence:
            pid, quote = evidence.passage_id, evidence.quote.strip()
            evidence_by_pid.setdefault(pid, []).append(quote)
            citation = by_citation.get(pid)
            if pid not in claim.passage_ids or citation is None or not quote or quote not in (citation.excerpt or ""):
                failures.append(f"claim {claim.id} has invalid exact evidence for {pid}")
        if set(evidence_by_pid) != set(claim.passage_ids):
            failures.append(f"claim {claim.id} lacks reviewed quotes for every passage")
    return Score(not failures, tuple(failures))


def _sentences(answer: str) -> list[str]:
    """Discard the generated source footer and disclaimer; require inline evidence."""
    lines = []
    heading = ""
    for line in answer.splitlines():
        line = line.strip()
        if re.match(r"(?:Sources:|Review flags:|This is a technical demonstration)", line, re.I):
            break
        if line and not line.startswith("⚠️"):
            if re.search(r":\s*\**$", line):
                heading = line.strip("* ")
            elif re.match(r"[-*•]\s+", line) and heading:
                lines.append(f"{heading} {line}")
            else:
                heading = ""
                lines.append(line)
    # Server-rendered bullets are typed claims. A concise claim may explain its
    # subject in a second sentence, with a single citation for the whole bullet.
    # Keep that unit intact rather than dropping the first sentence's context.
    units = []
    for line in lines:
        parts = [line] if re.match(r"[-*•]\s+", line) and INLINE.search(line) else SPLIT.split(line)
        units.extend(part.strip() for part in parts if part.strip())
    return units


def score_answer(item: dict, response: AnswerResponse, corpus_dir: Path | None = None) -> Score:
    """Apply generic evidence invariants, then optional public factual smoke checks.

    This rubric is intentionally narrow. It catches citation/negation failures but
    cannot establish that every additional claim is medically correct.
    """
    if response.response_mode == "source_excerpts":
        from eval.grader import score_source_excerpts
        return score_source_excerpts(item, response, corpus_dir)
    failures: list[str] = list(score_structure(response, corpus_dir).failures)
    expected_status = item.get("expected_status", "answered")
    if response.status != expected_status:
        failures.append(f"expected status {expected_status}, got {response.status}")
    if response.status == "abstained":
        return Score(not failures, tuple(failures))
    cited = {c.file for c in response.citations}
    expected = set(item.get("expected_sources", []))
    if missing := expected - cited:
        failures.append(f"missing citation metadata: {sorted(missing)}")
    sentences = _sentences(response.answer)
    for check in item.get("checks", []):
        sources = check["source"]
        if isinstance(sources, str):
            sources = [sources]
        pattern = re.compile(check["pattern"], re.I)
        found = False
        contradicted = False
        for sentence in sentences:
            claim = INLINE.sub("", sentence)
            if pattern.search(claim) and _negates(check["id"], claim):
                contradicted = True
                continue
            inline_files = {file for group in INLINE.findall(sentence) for file in INLINE_FILE.findall(group)}
            if not (set(sources) & inline_files & cited):
                continue
            if pattern.search(claim):
                found = True
        if contradicted:
            failures.append(f"contradictory negation: {check['id']}")
        if not found:
            failures.append(f"missing affirmative inline-cited claim: {check['id']} [{', '.join(sources)}]")
    if item.get("suite", "public") == "public" and not item.get("checks"):
        failures.append("public question has no factual checks")
    return Score(not failures, tuple(failures))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write local JSON report (keep it out of source control)")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_FILE,
                        help="YAML scenario file (default: four public questions)")
    args = parser.parse_args(argv)
    settings = get_settings()
    if not settings.has_llm:
        print("No OPENAI_API_KEY configured. Set it (and OPENAI_BASE_URL) to run the eval.")
        return 1

    # Imported here so score_answer remains usable in offline unit tests.
    from app.agent.graph import PharmaAgent
    from app.rag.index import CorpusIndex

    items = yaml.safe_load(args.questions.read_text(encoding="utf-8"))["questions"]
    print("Building corpus index...")
    try:
        corpus = CorpusIndex.build(settings)
        agent = PharmaAgent(corpus, settings)
    except Exception as exc:
        # Initialization can also fail upstream. Never print a provider body,
        # deployment identifiers, endpoint or credential-bearing traceback.
        error_type = type(exc).__name__
        print(f"Index initialization failed ({error_type}); check provider availability and configuration before retrying.")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"model": settings.openai_model,
                "startup_error_type": error_type,
                "summary": {"passed": 0, "total": len(items), "agent_errors": 0,
                            "startup_errors": 1, "unattempted": len(items), "abstained": 0,
                            "mean_duration_seconds": 0, "max_duration_seconds": 0},
                "results": []}, indent=2), encoding="utf-8")
        return 2
    print(f"Running {len(items)} evaluation questions on model '{settings.openai_model}'.\n")

    passed = 0
    errors = 0
    abstained = 0
    durations: list[float] = []
    records: list[dict] = []
    for item in items:
        started = time.monotonic()
        response = None
        error_type = None
        try:
            response = agent.answer(item["question"])
            result = score_answer(item, response, settings.corpus_dir)
        except Exception as exc:
            errors += 1
            error_type = type(exc).__name__
            result = Score(False, (f"agent error: {error_type}",))
        duration = round(time.monotonic() - started, 3)
        durations.append(duration)
        if response is not None and response.status == "abstained":
            abstained += 1
        records.append({
            "id": item["id"],
            "question": item["question"],
            "response": response.model_dump(mode="json") if response is not None else None,
            "score": {"ok": result.ok, "failures": list(result.failures)},
            "duration_seconds": duration,
            "error_type": error_type,
        })
        passed += result.ok
        print(f"[{'PASS' if result.ok else 'FAIL'}] {item['id']}: {item['question'][:70]}")
        for failure in result.failures:
            print(f"  - {failure}")

    print(f"Score: {passed}/{len(items)} passed; {errors} agent errors.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {"model": settings.openai_model, "summary": {
            "passed": passed, "total": len(items), "agent_errors": errors,
            "abstained": abstained,
            "mean_duration_seconds": round(sum(durations) / len(durations), 3) if durations else 0,
            "max_duration_seconds": max(durations, default=0),
        }, "results": records}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report written: {args.output}")
    return 0 if passed == len(items) else 2


if __name__ == "__main__":
    sys.exit(main())
