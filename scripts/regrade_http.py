"""Re-evaluate immutable HTTP answers after the documented Q4 notation fix.

No provider calls. Preserve every original score and the original campaign file.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.eval import score_answer
from app.models import AnswerResponse
import yaml


def main():
    source = ROOT / "reports/jury/http-focus-final.json"
    report = json.loads(source.read_text(encoding="utf-8"))
    questions = {q["id"]: q for name in ("questions.yaml", "scenarios.yaml", "jury_scenarios.yaml")
        for q in yaml.safe_load((ROOT / "eval" / name).read_text(encoding="utf-8"))["questions"]}
    report["original_summary"] = dict(report["summary"])
    report["regrade"] = {"date_utc": datetime.now(timezone.utc).isoformat(),
        "original_report_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "grader_sha256": hashlib.sha256((ROOT / "eval/grader.py").read_bytes()).hexdigest(),
        "reason": "Q4 coverage recognizer now accepts the closing parenthesis in the literal source '(eGFR) below 30'. Source, normalized units and conditional numeric requirements unchanged; no new provider answer."}
    for record in report["results"]:
        record["original_score"] = record["score"]
        if record.get("http_status") == 200:
            score = score_answer(questions[record["id"]], AnswerResponse.model_validate(record["response"]), ROOT / "corpus")
            record["score"] = {"ok": score.ok, "failures": list(score.failures)}
    report["summary"]["passed"] = sum(r["score"]["ok"] for r in report["results"])
    target = ROOT / "reports/jury/http-focus-regraded.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"raw": report["original_summary"], "regraded": report["summary"]}))


if __name__ == "__main__":
    main()
