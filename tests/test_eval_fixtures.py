from pathlib import Path
import pytest
import yaml
from scripts.http_acceptance import validate_cases

ROOT = Path(__file__).resolve().parents[1]


def test_all_current_evaluation_sources_exist_before_provider_calls():
    for path in (ROOT / "eval").glob("*.yaml"):
        validate_cases(yaml.safe_load(path.read_text(encoding="utf-8"))["questions"], ROOT / "corpus")


def test_preflight_rejects_invented_expected_source():
    with pytest.raises(ValueError, match="absent from the corpus"):
        validate_cases([{"id": "bad-fixture", "expected_sources": ["dailymed-nonexistent.md"]}], ROOT / "corpus")
