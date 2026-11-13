"""Run a bounded, sequential real-provider campaign through the delivered HTTP API."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import httpx
import yaml
from app.eval import score_answer
from app.models import AnswerResponse
from app.config import get_settings


def validate_cases(items, corpus_dir):
    """Catch invalid expected-source fixtures before any billable request."""
    available = {p.name for p in Path(corpus_dir).glob("*.md")}
    invalid = [(item["id"], name) for item in items for name in item.get("expected_sources", []) if name not in available]
    if invalid:
        raise ValueError(f"Expected source files absent from the corpus: {invalid}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--questions", nargs="+", type=Path, default=[ROOT / "eval/questions.yaml", ROOT / "eval/scenarios.yaml"])
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/http-acceptance.json")
    args = parser.parse_args()
    items = [item for path in args.questions for item in yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]]
    validate_cases(items, ROOT / "corpus")
    configured = get_settings()
    report = {"kind": "real_provider_via_http", "started_utc": datetime.now(timezone.utc).isoformat(),
        "model": configured.openai_model, "embedding_model": configured.openai_embedding_model,
        "limits": {name: getattr(configured, name) for name in ("answer_timeout", "request_timeout", "max_revisions", "max_llm_calls", "max_tool_calls", "max_evidence_chars", "max_context_chars")},
        "question_files": [p.name for p in args.questions], "results": [],
        "source_fingerprints": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("app", "corpus", "frontend", "eval") for p in sorted((ROOT / folder).rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=args.url, timeout=205) as client:
        report["health"] = client.get("/health").json()
        if report["health"]["status"] != "ok":
            raise SystemExit("Server is not ready; no provider calls made.")
        for item in items:
            start = time.monotonic()
            record = {"id": item["id"], "question": item["question"]}
            try:
                result = client.post("/ask", json={"question": item["question"]})
                record["http_status"] = result.status_code
                if result.status_code != 200:
                    record.update(score={"ok": False, "failures": ["HTTP request failed"]}, response=result.json())
                else:
                    response = AnswerResponse.model_validate(result.json())
                    score = score_answer(item, response, ROOT / "corpus")
                    failures = list(score.failures)
                    for citation in response.citations:
                        download = client.get("/sources/" + citation.file, params={"sha256": citation.document_sha256})
                        if download.status_code != 200 or hashlib.sha256(download.content).hexdigest() != citation.document_sha256:
                            failures.append("Cited complete source download did not match its hash")
                    record.update(response=response.model_dump(mode="json"), score={"ok": not failures, "failures": failures})
            except Exception as exc:
                record.update(score={"ok": False, "failures": [f"Local request/evaluation error: {type(exc).__name__}"]})
            record["duration_seconds"] = round(time.monotonic() - start, 3)
            report["results"].append(record)
            report["summary"] = {"passed": sum(r["score"]["ok"] for r in report["results"]),
                "total": len(report["results"]), "planned": len(items),
                "abstained": sum(r.get("response", {}).get("status") == "abstained" for r in report["results"]),
                "http_errors": sum(r.get("http_status") != 200 for r in report["results"])}
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"{item['id']}: {'PASS' if record['score']['ok'] else 'FAIL'} in {record['duration_seconds']}s", flush=True)
    print(json.dumps(report["summary"]), flush=True)
    return 0 if all(r["score"]["ok"] for r in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
