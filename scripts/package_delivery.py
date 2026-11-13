"""Build a reviewable source delivery without credentials or local environments."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DIRECTORIES = ("app", "corpus", "frontend", "eval", "tests", "scripts", "docs", "reports")
FILES = (
    "README.md", "ARCHITECTURE.md", "DEMO.md", "VALIDATION.md", "LIVRAISON.md", "AUDIT_FINAL.md",
    "Dockerfile", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
    ".env.example", ".gitignore", ".gitattributes", ".dockerignore", ".python-version",
    ".github/workflows/tests.yml", ".vscode/settings.json",
    ".claude/CLAUDE.md", ".claude/plan.md",
    "output/pdf/Rapport_Projet_Pharma.pdf",
    "output/preview/desktop.png", "output/preview/mobile.png",
)


def build() -> Path:
    selected = {ROOT / name for name in FILES}
    for directory in DIRECTORIES:
        selected.update(p for p in (ROOT / directory).rglob("*")
                        if p.is_file() and "__pycache__" not in p.parts
                        and p.suffix not in {".pyc", ".pyo"})
    missing = [p.relative_to(ROOT).as_posix() for p in selected if not p.is_file()]
    if missing:
        raise RuntimeError(f"Missing delivery files: {missing}")

    # Read the local key only to reject accidental inclusion; never log its value.
    from dotenv import dotenv_values
    key = (dotenv_values(ROOT / ".env").get("OPENAI_API_KEY") or "").strip("\"'")
    manifest = {}
    for path in sorted(selected):
        relative = path.relative_to(ROOT).as_posix()
        if path.name.startswith(".env") and relative != ".env.example":
            raise RuntimeError("An environment file was selected")
        content = path.read_bytes()
        if key and len(key) >= 12 and key.encode() in content:
            raise RuntimeError(f"Credential occurrence in {relative}")
        manifest[relative] = hashlib.sha256(content).hexdigest()

    target = ROOT / "dist" / "assignment-pharma-final.zip"
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in manifest:
            archive.write(ROOT / relative, "assignment-pharma/" + relative)
        archive.writestr("assignment-pharma/MANIFEST_SHA256.json",
                         json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    # Check archive integrity and every embedded checksum after publication.
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Corrupt delivery archive")
        for relative, expected in manifest.items():
            if hashlib.sha256(archive.read("assignment-pharma/" + relative)).hexdigest() != expected:
                raise RuntimeError("Delivery checksum mismatch")
    print(f"Delivery: {target.name}; {len(manifest)} files; no local API key occurrence.")
    return target


if __name__ == "__main__":
    build()
