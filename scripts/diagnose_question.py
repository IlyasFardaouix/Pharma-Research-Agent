"""Opt-in provider run with private review diagnostics, never served by HTTP.

Keep its output under .cache (excluded from delivery and version control).
"""
from pathlib import Path
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.agent.graph import PharmaAgent
from app.config import get_settings
from app.rag.index import CorpusIndex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/jury/private-diagnostic.json")
    args = parser.parse_args()
    settings = get_settings()
    agent = PharmaAgent(CorpusIndex.build(settings), settings)
    compiled, records = agent.graph, []

    class Recorder:
        def stream(self, *arguments, **kwargs):
            for state in compiled.stream(*arguments, **kwargs):
                review = state.get("grounding")
                draft = state.get("draft")
                records.append({"revision_count": state.get("revision_count"),
                    "draft": draft.model_dump() if draft else None,
                    "review": review.model_dump() if review else None,
                    "draft_error": state.get("draft_error"), "response_error": state.get("response_error"),
                    "tools": [t.model_dump() for t in state.get("tool_trace", [])]})
                yield state

    agent.graph = Recorder()
    started = time.monotonic()
    try:
        response = agent.answer(args.question)
        result = {"status": response.status, "duration_seconds": round(time.monotonic() - started, 3),
            "response": response.model_dump(), "internal_diagnostics": records}
    except Exception as exc:
        result = {"error_type": type(exc).__name__, "internal_diagnostics": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"response", "internal_diagnostics"}}))
    return 0 if result.get("status") == "answered" else 1


if __name__ == "__main__":
    raise SystemExit(main())
