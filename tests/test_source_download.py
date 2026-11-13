"""A cited source can be inspected without exposing arbitrary local files."""
import hashlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app


def test_source_download_is_whitelisted_and_hash_bound(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    content = "# Document\nLittéral : épreuve <script>alert(1)</script>\n".encode()
    (corpus / "dailymed-example.md").write_bytes(content)
    (tmp_path / ".env").write_text("PRIVATE", encoding="utf-8")
    cfg = SimpleNamespace(has_llm=False, corpus_dir=corpus, answer_timeout=1, max_concurrent_requests=1)
    digest = hashlib.sha256(content).hexdigest()
    with TestClient(create_app(settings=cfg)) as client:
        route = "/sources/dailymed-example.md"
        response = client.get(route, params={"sha256": digest})
        assert response.status_code == 200 and response.content == content
        assert response.headers["content-type"].startswith("text/plain")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "sandbox" in response.headers["content-security-policy"]
        assert response.headers["etag"] == f'"{digest}"'
        assert client.get(route, params={"sha256": "0" * 64}).status_code == 409
        assert client.get(route).status_code == 422
        assert client.get(route, params={"sha256": "invalid"}).status_code == 422
        for path in ("/sources/.env", "/sources/..%5C.env", "/sources/%2e%2e%2f.env", "/corpus/dailymed-example.md"):
            assert client.get(path, params={"sha256": digest}).status_code == 404
        (corpus / "dailymed-example.md").write_bytes(b"Changed")
        assert client.get(route, params={"sha256": digest}).status_code == 409
