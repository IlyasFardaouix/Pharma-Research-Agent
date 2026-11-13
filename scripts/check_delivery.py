"""Read-only checks against the built container; no model-generation calls."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys

import httpx

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="pharma-final")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/jury/docker-validation.json")
    args = parser.parse_args()
    checks = {}
    remote_code = """from pathlib import Path
import hashlib,json,os
root=Path('/app')
files={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('app','corpus','frontend','eval') for p in sorted((root/folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
print(json.dumps({'files':files,'uid':os.getuid(),'env_file_present':(root/'.env').exists(),'source_writable':os.access(root/'app/main.py',os.W_OK),'cache_writable':os.access(root/'.cache',os.W_OK)}))
"""
    runtime = json.loads(subprocess.run(["docker", "exec", args.container, "python", "-c", remote_code],
        capture_output=True, text=True, check=True).stdout)
    local = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("app", "corpus", "frontend", "eval") for p in sorted((ROOT / folder).rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts}
    checks["container_sources_match_workspace"] = runtime["files"] == local
    checks["non_root_readonly_sources_writable_cache"] = runtime["uid"] == 10001 and not runtime["source_writable"] and runtime["cache_writable"]
    checks["no_embedded_env"] = not runtime["env_file_present"]
    inspect = json.loads(subprocess.run(["docker", "inspect", args.container], capture_output=True, text=True, check=True).stdout)[0]
    # Do not write inspect.Config.Env: it contains the injected secret.
    with httpx.Client(base_url=args.url, timeout=10) as client:
        health = client.get("/health")
        checks["health_ready"] = health.status_code == 200 and health.json()["status"] == "ok"
        checks["served_html_matches_workspace"] = client.get("/").content == (ROOT / "frontend/index.html").read_bytes()
        checks["blank_422"] = client.post("/ask", json={"question": " "}).status_code == 422
        checks["oversized_413"] = client.post("/ask", content=b"x" * 16385).status_code == 413
        checks["long_question_422"] = client.post("/ask", json={"question": "a" * 4001}).status_code == 422
        checks["secret_not_served"] = client.get("/.env").status_code == 404
        checks["traversal_not_served"] = client.get("/sources/..%5C.env", params={"sha256": "0" * 64}).status_code == 404
        checks["raw_corpus_not_served"] = client.get("/corpus/dailymed-warfarin.md").status_code == 404
        doc = ROOT / "corpus/dailymed-warfarin.md"
        digest = hashlib.sha256(doc.read_bytes()).hexdigest()
        original = client.get("/sources/" + doc.name, params={"sha256": digest})
        checks["hash_bound_source_exact"] = original.status_code == 200 and original.content == doc.read_bytes()
        checks["source_inert_text"] = original.headers.get("content-type", "").startswith("text/plain") and original.headers.get("x-content-type-options") == "nosniff" and "sandbox" in original.headers.get("content-security-policy", "")
        checks["source_changed_409"] = client.get("/sources/" + doc.name, params={"sha256": "0" * 64}).status_code == 409
    report = {"kind": "delivered_container_readonly_no_generation", "date_utc": datetime.now(timezone.utc).isoformat(),
        "container": args.container, "image": inspect["Image"], "ports": inspect["NetworkSettings"]["Ports"],
        "model_configuration": {value.split("=", 1)[0]: value.split("=", 1)[1].strip("\"'")
            for value in inspect["Config"]["Env"] if value.split("=", 1)[0] in {"OPENAI_MODEL", "OPENAI_EMBEDDING_MODEL"}},
        "health": health.json(), "checks": checks, "source_fingerprints": local}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": sum(checks.values()), "total": len(checks), "failed": [k for k,v in checks.items() if not v]}))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
