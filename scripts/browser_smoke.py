"""Browser smoke checks without provider calls.

Run with: uv tool run --from playwright python -B scripts/browser_smoke.py
The Edge browser channel must be installed on the test machine.
"""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description="Run isolated UI and API smoke checks")
parser.add_argument("--url", default=os.getenv("PHARMA_BASE_URL", "http://127.0.0.1:8000"))
parser.add_argument("--report", default=".cache/browser-smoke.json")
parser.add_argument("--frontend", type=Path, help="Serve this HTML through request interception; do not change the running server")
args = parser.parse_args()
BASE = args.url.rstrip("/")
READY = {"status": "ok", "retriever_ready": True, "corpus_files": 21, "chunks": 556,
         "llm_configured": True, "answer_timeout": 1.0}
DEGRADED = {"status": "degraded", "retriever_ready": True, "corpus_files": 21, "chunks": 556,
            "llm_configured": False, "answer_timeout": 1.0}
results = {}
REFUSAL = {"status": "abstained", "answer": "No complete answer could be verified from the supplied documents.",
           "claims": [], "citations": [], "warnings": [],
           "grounding": {"verdict": "ungrounded", "supported": False, "flags": []}}

def check(name, condition):
    results[name] = bool(condition)
    if not condition:
        raise AssertionError(name)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    try:
        def new_page(**options):
            current = browser.new_page(**options)
            if args.frontend:
                html = args.frontend.read_text(encoding="utf-8")
                current.route(BASE + "/", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
            return current

        def close_page(current):
            # Drain route callbacks before the sync event loop/browser closes.
            # Do not use ignoreErrors: routing failures should still fail the run.
            current.unroute_all(behavior="wait")
            current.close()

        page = new_page(viewport={"width": 390, "height": 844})
        page.route("**/health", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(DEGRADED)))
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_function("document.getElementById('health').textContent.includes('not configured')")
        check("disclaimer_visible_degraded", page.locator(".disclaimer").is_visible())
        check("ask_disabled_degraded", page.locator("#ask").is_disabled())
        attack = "<img src=x onerror=window.__xss=1>"
        mock = {
            "status": "answered", "claims": [{"id": "c1", "text": attack, "passage_ids": ["a", "b"]}],
            "answer": attack + " **bold**",
            "warnings": [attack],
            "citations": [
                {"file": attack, "section": attack, "drug": attack, "source": attack, "passage_id": "a", "excerpt": attack},
                {"file": attack, "section": attack, "passage_id": "b", "excerpt": attack + " second"},
            ],
            "plan": [attack],
            "tool_trace": [{"tool": attack, "args": {"x": attack}, "result_summary": attack}],
            "grounding": {"verdict": "grounded", "supported": True, "notes": attack, "flags": []},
        }
        page.evaluate("data => { window.__xss = 0; render(data); }", mock)
        check("xss_no_dom_execution", page.evaluate("window.__xss") == 0 and page.locator("img").count() == 0)
        check("xss_answer_escaped", attack in page.locator("#claims").inner_text())
        check("warnings_public_notice", page.locator("#warnings").is_visible() and attack not in page.locator("#warningList").inner_text())
        check("citations_distinct_passages", page.locator("#sources li").count() == 2)
        page.locator("#sources details").first.locator("summary").click()
        check("excerpt_readable", page.locator("#sources details").count() == 2 and attack in page.locator("#sources blockquote").first.inner_text())
        page.locator("#traceBox summary").click()
        check("trace_safe", attack in page.locator("#trace").inner_text() and page.locator("#trace img").count() == 0)
        check("mobile_no_overflow", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        structured = {
            "status": "answered",
            "answer": "A claim.\nSources: dailymed-warfarin.md\nMedical disclaimer",
            "disclaimer": "Medical disclaimer",
            "claims": [{"id": "c1", "text": "A claim.", "passage_ids": ["warfarin#1"]}],
            "citations": [{"file": "dailymed-warfarin.md", "passage_id": "warfarin#1",
                           "excerpt": "The exact source passage.", "claim_ids": ["c1"]}],
            "grounding": {"supported": True, "verdict": "grounded", "flags": [], "claim_checks": [
                {"claim_id": "c1", "supported": True, "evidence": [
                    {"passage_id": "warfarin#1", "quote": "The exact source passage."},
                    {"passage_id": "warfarin#1", "quote": "Invented quote absent from source."}]}]},
        }
        page.evaluate("data => render(data)", structured)
        check("structured_claim_link", page.locator("#claimBox").is_visible()
              and page.locator("#claims a").count() == 1
              and page.locator("#claims a").first.get_attribute("href") == "#source-1")
        check("structured_answer_no_duplicate_footer", page.locator("#answer").is_hidden()
              and "Medical disclaimer" not in page.locator("#claimBox").inner_text())
        page.locator("#claims a").first.click()
        check("source_link_opens_and_focuses_evidence", page.locator("#sources details").first.get_attribute("open") is not None
              and page.locator("#sources blockquote").first.is_visible()
              and page.evaluate("document.activeElement.id") == "source-1")
        page.locator("#claims .exact-evidence summary").first.click()
        check("exact_quote_rendered_from_review", page.locator("#claims blockquote").count() == 1
              and page.locator("#claims blockquote").inner_text() == "The exact source passage.")
        check("invented_review_quote_not_rendered", "Invented quote" not in page.locator("#claimBox").inner_text())
        check("automated_review_not_clinical_validation", "not clinical validation" in page.locator("#claimBox").inner_text())
        check("result_heading_hierarchy", page.locator("#result h2").count() == 1 and page.locator("#result h4").count() == 0)
        page.evaluate("data => render(data)", dict(structured, plan_kind="workflow_summary", plan=[
            "Search the local corpus", "Review the selected evidence", "Publish literal source excerpts or abstain"]))
        check("workflow_summary_labeled_honestly", "Workflow summary" in page.locator("#trace h3").all_text_contents()
              and "Plan" not in page.locator("#trace h3").all_text_contents()
              and "(plan" not in page.locator("#traceBox summary").inner_text().lower())
        page.evaluate("data => render(data)", dict(structured, plan_kind="research_plan", plan=["Retrieve the requested source section"]))
        check("legacy_research_plan_label_preserved", "Plan" in page.locator("#trace h3").all_text_contents()
              and "Workflow summary" not in page.locator("#trace h3").all_text_contents())
        for width in (320, 360, 390, 768, 1440):
            page.set_viewport_size({"width": width, "height": 844})
            check("no_overflow_" + str(width), page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        raw_a = "  First source includes bleeding and hypersensitivity.\n\neGFR below 30 mL/min/1.73 m². Keep the exception and context.\n"
        raw_b = "Second source includes bleeding and hypersensitivity.\r\nKeep this separate attribution.\r\n"
        comparison_scope = "Comparison is limited to wording in the selected source sections; absence of a listed condition does not establish clinical safety or exclusivity."
        numeric_condition = "Numerical comparison only. Clinical interpretation requires identical units, body-surface normalization and applicable patient context."
        excerpts = {
            "status": "answered", "response_mode": "source_excerpts", "answer": "UNVERIFIED_GENERATED_SUMMARY_DO_NOT_SHOW",
            "claims": [{"id": "c1", "text": raw_a, "passage_ids": ["passage-a"]},
                       {"id": "c2", "text": raw_b, "passage_ids": ["passage-b"]}],
            "citations": [
                {"file": "dailymed-drug-a.md", "drug": "drug-a", "product": "Tablet A", "section": "4 CONTRAINDICATIONS",
                 "passage_id": "passage-a", "excerpt": raw_a, "claim_ids": ["c1"], "document_sha256": "a" * 64},
                {"file": "dailymed-drug-b.md", "drug": "drug-b", "product": "Capsule B", "section": "5 WARNINGS",
                 "passage_id": "passage-b", "excerpt": raw_b, "claim_ids": ["c2"], "document_sha256": "b" * 64},
            ],
            "grounding": {"supported": True, "verdict": "grounded", "flags": [], "scope": "source_provenance"},
            "comparison_scope": comparison_scope,
            "common_terms": ["bleeding", "hypersensitivity", "inventedcommon", "stop taking", attack],
            "numeric_comparisons": [{"variable": "eGFR", "question_value": "25", "source_threshold": "30",
                                     "relation": "below", "question_unit": "mL/min", "source_unit": "mL/min/1.73 m²",
                                     "passage_id": "passage-a", "condition": numeric_condition}],
        }
        page.evaluate("data => render(data, 'Which documents apply?')", excerpts)
        check("source_excerpts_explicit_presentation", page.locator("#resultTitle").inner_text() == "Evidence from the documents"
              and page.locator("#findingsTitle").inner_text() == "Exact source passages")
        check("source_excerpts_preserve_full_raw_text", page.locator("#claims .document-excerpt").nth(0).text_content() == raw_a
              and page.locator("#claims .document-excerpt").nth(1).text_content() == raw_b)
        check("source_excerpts_identity_per_passage", "Drug: drug-a · Product: Tablet A · Section: 4 CONTRAINDICATIONS"
              == page.locator("#claims .excerpt-identity").nth(0).inner_text()
              and "Drug: drug-b · Product: Capsule B · Section: 5 WARNINGS"
              == page.locator("#claims .excerpt-identity").nth(1).inner_text())
        check("source_excerpts_do_not_publish_summary", "UNVERIFIED_GENERATED_SUMMARY" not in page.locator("#result").inner_text()
              and page.locator("#claims .exact-evidence").count() == 0)
        check("source_excerpts_question_and_caution", page.locator("#submittedQuestion").inner_text() == "Which documents apply?"
              and "not clinical validation" in page.locator("#claimBox").inner_text()
              and "completeness" in page.locator("#resultState").inner_text())
        check("comparison_scope_visible_without_exclusivity_claim", page.locator("#comparisonScope").is_visible()
              and page.locator("#comparisonScope").inner_text() == comparison_scope)
        check("comparison_terms_only_literal_common_words", page.locator("#literalOverlap").inner_text()
              == "Shared literal terms: bleeding, hypersensitivity. Word overlap does not establish clinical equivalence.")
        check("numeric_observation_separate_and_conditional", page.locator("#numericBox").is_visible()
              and "not a clinical eligibility decision" in page.locator("#numericBox").inner_text()
              and numeric_condition in page.locator("#numericBox").inner_text())
        numeric_rows = page.locator("#numericBox tbody tr")
        check("numeric_units_and_values_preserved_separately", numeric_rows.nth(0).locator("td").nth(0).inner_text() == "25"
              and numeric_rows.nth(0).locator("td").nth(1).inner_text() == "mL/min"
              and numeric_rows.nth(1).locator("td").nth(0).inner_text() == "30"
              and numeric_rows.nth(1).locator("td").nth(1).inner_text() == "mL/min/1.73 m²"
              and "25 < 30 (below)" in page.locator("#numericBox").inner_text())
        page.locator("#numericBox a").click()
        check("numeric_source_context_opens_and_focuses", page.locator("#sources details").first.get_attribute("open") is not None
              and page.evaluate("document.activeElement.id") == "source-1")
        document_link = page.locator("#sources a").first
        check("full_document_link_content_pinned_local", document_link.get_attribute("href")
              == "/sources/dailymed-drug-a.md?sha256=" + "a" * 64)
        check("full_document_new_tab_protected", document_link.get_attribute("target") == "_blank"
              and {"noopener", "noreferrer"}.issubset(set(document_link.get_attribute("rel").split())))
        for width in (320, 390, 1440):
            page.set_viewport_size({"width": width, "height": 844})
            check("source_excerpts_no_overflow_" + str(width), page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
            positions = page.locator("#claims > .comparison-group").evaluate_all("items => items.map(x => ({x:x.getBoundingClientRect().x, y:x.getBoundingClientRect().y, bottom:x.getBoundingClientRect().bottom}))")
            check("comparison_columns_" + str(width), len(positions) == 2 and
                  ((positions[1]["x"] > positions[0]["x"] and abs(positions[0]["y"] - positions[1]["y"]) < 1)
                   if width == 1440 else (abs(positions[0]["x"] - positions[1]["x"]) < 1 and positions[1]["y"] >= positions[0]["bottom"])))
        grouped = deepcopy(excerpts)
        grouped["claims"].append({"id": "c3", "text": "Another complete context for the first product.", "passage_ids": ["passage-a2"]})
        grouped["citations"].append(dict(grouped["citations"][0], passage_id="passage-a2", claim_ids=["c3"],
                                          excerpt="Another complete context for the first product."))
        page.evaluate("data => render(data)", grouped)
        check("comparison_contexts_grouped_by_product", page.locator("#claims > .comparison-group").count() == 2
              and page.locator("#claims > .comparison-group").nth(0).locator(".document-excerpt").count() == 2
              and page.locator("#claims > .comparison-group").nth(1).locator(".document-excerpt").count() == 1)
        for label, question_value, relation, expected in (("equal", "30", "equal", "30 = 30 (equal)"),
                                                           ("above", "40", "above", "40 > 30 (above)"),
                                                           ("decimal_comma", "25,5", "below", "25,5 < 30 (below)")):
            numerical_case = deepcopy(excerpts)
            numerical_case["numeric_comparisons"][0].update(question_value=question_value, relation=relation)
            page.evaluate("data => render(data)", numerical_case)
            check("numeric_relation_" + label, expected in page.locator("#numericBox").inner_text()
                  and numeric_condition in page.locator("#numericBox").inner_text())
        for label, field, bad_value in (("unpublished_source", "passage_id", "unknown"),
                                        ("untrusted_condition", "condition", "UNVERIFIED_CLINICAL_DECISION"),
                                        ("nonnumeric_value", "question_value", "UNVERIFIED_CLINICAL_DECISION"),
                                        ("unknown_relation", "relation", "UNVERIFIED_CLINICAL_DECISION")):
            invalid_number = deepcopy(excerpts)
            invalid_number["numeric_comparisons"][0][field] = bad_value
            page.evaluate("data => render(data)", invalid_number)
            check("numeric_reject_" + label, page.locator("#numericBox").is_hidden()
                  and "UNVERIFIED_CLINICAL_DECISION" not in page.locator("#result").inner_text())
        wrong_scope = deepcopy(excerpts)
        wrong_scope["grounding"]["scope"] = "semantic_review"
        page.evaluate("data => render(data)", wrong_scope)
        check("source_excerpts_require_provenance_scope", page.locator("#claimBox").is_hidden()
              and page.locator("#sourceBox").is_hidden() and page.locator("#numericBox").is_hidden())
        for problem in ("text_mismatch", "wrong_passage", "duplicate_passage", "multiple_passages", "ambiguous_citation"):
            invalid = deepcopy(excerpts)
            if problem == "text_mismatch":
                invalid["claims"][0]["text"] = "A rewritten statement not present verbatim."
            elif problem == "wrong_passage":
                invalid["claims"][0]["passage_ids"] = ["passage-b"]
            elif problem == "duplicate_passage":
                invalid["claims"].append({"id": "c3", "text": raw_a, "passage_ids": ["passage-a"]})
                invalid["citations"][0]["claim_ids"].append("c3")
            elif problem == "multiple_passages":
                invalid["claims"][0]["passage_ids"] = ["passage-a", "passage-b"]
            else:
                invalid["citations"].append(deepcopy(invalid["citations"][0]))
            page.evaluate("data => render(data)", invalid)
            check("source_excerpts_reject_" + problem, page.locator("#claimBox").is_hidden()
                  and page.locator("#sourceBox").is_hidden() and "No excerpts were published" in page.locator("#answer").inner_text())
        escaped = deepcopy(excerpts)
        escaped["citations"][0]["product"] = attack
        page.evaluate("data => render(data)", escaped)
        check("source_excerpts_metadata_escaped", attack in page.locator("#claims .excerpt-identity").first.inner_text()
              and page.locator("img").count() == 0)
        for label, bad_file, bad_hash in (("traversal", "../.env", "a" * 64),
                                         ("external", "https://example.invalid/file.md", "a" * 64),
                                         ("query_injection", "dailymed-drug-a.md", "a" * 64 + "&redirect=evil")):
            unsafe = deepcopy(structured)
            unsafe["citations"][0].update(file=bad_file, document_sha256=bad_hash)
            page.evaluate("data => render(data)", unsafe)
            check("full_document_reject_unsafe_" + label, page.locator("#sources a").count() == 0)
        internal = "INTERNAL_MEDICAL_DRAFT_DO_NOT_SHOW"
        refusal = dict(REFUSAL, warnings=[internal], plan=[internal],
                       tool_trace=[{"tool": "search_corpus", "args": {"query": internal}, "result_summary": internal}],
                       grounding={"verdict": "ungrounded", "supported": False, "flags": [internal], "notes": internal})
        page.evaluate("data => render(data)", refusal)
        page.locator("#traceBox summary").click()
        check("abstention_hides_unverified_diagnostics", internal not in page.locator("#result").inner_text()
              and page.locator("#claims").inner_text() == "" and page.locator("#sourceBox").is_hidden())
        check("abstention_explicit_state", page.locator("#resultTitle").inner_text() == "No verified answer")
        page.evaluate("data => render(data)", dict(structured, grounding={"verdict": "ungrounded", "supported": False}))
        check("unapproved_answer_not_published", page.locator("#claimBox").is_hidden()
              and "A claim." not in page.locator("#result").inner_text())
        page.route("**/health", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(
            dict(READY, status="starting", retriever_ready=False))))
        page.evaluate("checkHealth()")
        check("starting_state_explained", page.locator("#ask").is_disabled() and "Building" in page.locator("#health").inner_text())
        page.route("**/health", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(READY)))
        page.evaluate("checkHealth()")
        check("health_recovers_in_same_page", page.locator("#ask").is_enabled() and "Ready" in page.locator("#health").inner_text())
        close_page(page)

        page = new_page()
        page.route("**/health", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(READY)))
        posts = []
        reply = REFUSAL
        def answer_route(route):
            posts.append(route.request.post_data)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(reply))
        page.route("**/ask", answer_route)
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_function("!document.getElementById('ask').disabled")
        check("ui_uses_server_timeout", page.evaluate("answerTimeoutMs") == 1000)
        page.locator("#q").fill("warfarin?")
        page.evaluate("() => { const b = document.getElementById('ask'); b.click(); b.click(); }")
        page.wait_for_function("document.getElementById('answer').textContent.includes('No complete answer')")
        check("double_click_one_post", len(posts) == 1)
        check("response_focuses_result", page.evaluate("document.activeElement.id") == "result")
        check("submitted_question_visible", page.locator("#submittedQuestion").inner_text() == "warfarin?")
        page.locator("#q").fill("a" * 4001)
        page.keyboard.press("Control+Enter")
        check("overlong_question_not_sent", len(posts) == 1 and page.locator("#ask").is_disabled()
              and page.locator("#questionError").is_visible() and len(page.locator("#q").input_value()) == 4001)
        page.locator("#q").fill("\U0001f9ea" * 4000)
        check("unicode_limit_counts_codepoints", page.locator("#questionCount").inner_text() == "4,000 / 4,000 characters"
              and page.locator("#ask").is_enabled() and len(page.locator("#q").input_value()) == 4000)
        page.locator("#q").fill("\U0001f9ea" * 4001)
        page.keyboard.press("Control+Enter")
        check("unicode_overlong_not_sent_or_truncated", len(posts) == 1 and page.locator("#ask").is_disabled()
              and len(page.locator("#q").input_value()) == 4001)
        check("question_count_accessible", "questionCount" in page.locator("#q").get_attribute("aria-describedby")
              and page.locator("#q").get_attribute("aria-invalid") == "true")
        page.locator("#q").fill("Valid keyboard question")
        page.keyboard.press("Control+Enter")
        page.wait_for_function("document.getElementById('submittedQuestion').textContent === 'Valid keyboard question'")
        check("keyboard_shortcut_sends_valid_question", len(posts) == 2)
        close_page(page)

        page = new_page()
        page.route("**/health", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(READY)))
        pending = []
        page.route("**/ask", lambda route: pending.append(route))
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_function("!document.getElementById('ask').disabled")
        page.locator("#q").fill("warfarin?")
        page.locator("#ask").click()
        page.wait_for_function("!document.getElementById('cancel').hidden")
        page.locator("#cancel").click()
        page.wait_for_function("document.getElementById('answer').textContent.includes('Request cancelled')")
        check("cancel_pending_request", len(pending) == 1 and page.locator("#ask").is_enabled())
        # AbortController cancels the browser fetch, but the intentionally held
        # Playwright interception must also be resolved before closing the page.
        pending[0].abort()
        close_page(page)

        page = new_page(viewport={"width": 390, "height": 844})
        page.route("**/health", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(READY)))
        pending = []
        page.route("**/ask", lambda route: pending.append(route))
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_function("!document.getElementById('ask').disabled")
        page.locator("#q").fill("Original warfarin question")
        page.locator("#ask").click()
        page.wait_for_function("!document.getElementById('cancel').hidden")
        check("examples_disabled_while_busy", page.locator(".chip:disabled").count() == 4)
        check("busy_explains_wait_and_cancel", "elapsed" in page.locator("#status").inner_text()
              and "cancel" in page.locator("#status").inner_text().lower())
        check("timer_does_not_repeat_live_announcements", page.locator("#status").get_attribute("aria-live") == "off"
              and "Request started" in page.locator("#busyAnnouncement").inner_text())
        page.locator("#q").fill("New metformin question")
        while not pending:
            page.wait_for_timeout(20)
        pending[0].fulfill(status=200, content_type="application/json", body=json.dumps(structured))
        page.locator("#claimBox").wait_for(state="visible")
        check("inflight_edit_does_not_misattribute_answer", page.locator("#submittedQuestion").inner_text() == "Original warfarin question"
              and page.locator("#q").input_value() == "New metformin question")
        check("busy_cleared_after_result", page.locator(".chip:disabled").count() == 0
              and page.locator("#result").get_attribute("aria-busy") == "false")
        close_page(page)

        page = new_page()
        page.route("**/health", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(READY)))
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_function("!document.getElementById('ask').disabled")
        def error_route(code, message):
            return lambda route: route.fulfill(status=code, content_type="application/json", body=json.dumps({"detail": message}))
        for status_code, detail in ((422, [{"msg": "Invalid question"}]), (429, "Service busy; retry later."),
                                    (503, "Service unavailable; retry later."), (504, "Answer timed out; narrow the question.")):
            page.route("**/ask", error_route(status_code, detail))
            page.locator("#q").fill("Error test")
            page.locator("#ask").click()
            page.wait_for_function("document.getElementById('result').hidden === false && document.getElementById('ask').disabled === false")
            check("http_" + str(status_code) + "_clear_error_state", page.locator("#resultTitle").inner_text() == "Request unavailable"
                  and page.locator("#claimBox").is_hidden() and page.locator("#sourceBox").is_hidden()
                  and page.evaluate("document.activeElement.id") == "result")
        close_page(page)

        api = p.request.new_context(base_url=BASE)
        health = api.get("/health")
        check("real_health", health.status == 200 and health.json()["status"] == "ok")
        blank = api.post("/ask", data={"question": " "})
        check("real_validation_422", blank.status == 422)
        corpus = api.get("/corpus/dailymed-warfarin.md")
        check("corpus_not_served", corpus.status == 404)
        secret = api.get("/%2e%2e/.env")
        check("path_traversal_not_served", secret.status in (400, 404) and "OPENAI_API_KEY" not in secret.text())
        api.dispose()
    finally:
        browser.close()

report = Path(args.report)
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))




