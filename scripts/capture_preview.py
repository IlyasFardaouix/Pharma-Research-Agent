"""Capture one real answer from the running demo, without intercepting requests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--report", type=Path, default=ROOT / "reports/jury/preview-live.json")
args = parser.parse_args()
out = ROOT / "output/preview"
out.mkdir(parents=True, exist_ok=True)
(ROOT / "reports").mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_function("!document.getElementById('ask').disabled", timeout=60000)
        question = "Define INR using only the provided local glossary."
        page.locator("#q").fill(question)
        started = time.monotonic()
        with page.expect_response(lambda r: r.url.endswith("/ask") and r.request.method == "POST", timeout=195000) as event:
            page.locator("#ask").click()
        response = event.value
        payload = response.json()
        assert response.status == 200 and payload["status"] == "answered", "Real preview did not answer"
        assert payload["response_mode"] == "source_excerpts" and payload["grounding"]["scope"] == "source_provenance"
        page.locator("#claimBox").wait_for(state="visible")
        page.locator("#sources details summary").first.click()
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(out / "desktop.png"), full_page=True)
        assert page.locator("#claims a").count() >= 1
        assert page.locator("#sources blockquote").first.is_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(out / "mobile.png"), full_page=True)
        receipt = {"kind": "real_provider_http_browser", "question": question,
                   "date_utc": datetime.now(timezone.utc).isoformat(),
                   "frontend_sha256": hashlib.sha256((ROOT / "frontend/index.html").read_bytes()).hexdigest(),
                   "http_status": response.status, "duration_seconds": round(time.monotonic() - started, 3),
                   "response": payload, "mobile_no_overflow": True}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Real preview captured: {len(payload['claims'])} claims, {len(payload['citations'])} passages.")
    finally:
        browser.close()
