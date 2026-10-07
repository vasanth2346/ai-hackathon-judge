from app import security
from app.config import Settings
from app.judging import evaluation
from app.judging.browser import public_http_url
from app.pdf_submission import SubmissionPdfError, extract_form_details


def submission(**extra):
    value = {
        "application_number": "1042",
        "project_name": "PantryPal",
        "participant_names": ["Alex", "Sam"],
        "deployed_url": "https://example.com",
        "problem_statement": "Small shops lose money when they cannot track expiry dates.",
        "solution_description": "A simple dashboard helps shop owners track expiry dates and reduce food waste.",
        "github_url": None,
        "ai_tools_metadata": [],
    }
    value.update(extra)
    return value


def observations():
    return [
        {"id": "obs-001", "kind": "deployment", "title": "Deployment opened", "detail": "Loaded URL.", "result": "passed", "http_status": 200},
        {"id": "obs-002", "kind": "page", "title": "Page content observed", "detail": "Expiry alerts dashboard and inventory list."},
        {"id": "obs-003", "kind": "responsive", "title": "Mobile observed", "detail": "No overflow.", "result": "passed"},
        {"id": "obs-004", "kind": "interaction", "title": "Control clicked", "detail": "Visible changed.", "result": "passed"},
        {"id": "obs-005", "kind": "network", "title": "Network observed", "detail": "1 request", "requests": [{"method": "GET"}]},
        {"id": "obs-006", "kind": "persistence", "title": "Persistence not tested", "detail": "No valid form submitted.", "result": "not_tested"},
    ]


def test_rubric_is_exact_and_sums_to_100():
    assert [weight for _, _, weight in evaluation.RUBRIC] == [30, 20, 10, 10, 20, 10]
    assert [key for key, _, _ in evaluation.RUBRIC] == ["functionality", "problem_fit", "technical", "ui_ux", "innovation", "real_world"]
    assert sum(weight for _, _, weight in evaluation.RUBRIC) == 100


def test_postgresql_is_the_application_database_default():
    assert Settings(_env_file=None).database_url.startswith("postgresql+psycopg://")


def test_total_is_weighted_six_criteria_and_ignores_tool_use(monkeypatch):
    async def no_llm(*args):
        return {}
    monkeypatch.setattr(evaluation, "optional_assessment", no_llm)
    first = evaluation.score_report(submission(ai_tools_metadata=["Codex", "Copilot"]), observations(), [], None)
    second = evaluation.score_report(submission(ai_tools_metadata=[]), observations(), [], None)
    assert first["total_score"] == second["total_score"]
    assert len(first["criteria"]) == 6
    assert round(sum(row["score"] for row in first["criteria"]), 1) == first["total_score"]
    assert all(row["weight"] in [30, 20, 10] for row in first["criteria"])
    assert all(row["points_not_awarded"] >= 0 and row["why_points_not_awarded"] for row in first["criteria"])


def test_criterion_references_only_observed_ids(monkeypatch):
    async def no_llm(*args):
        return {}
    monkeypatch.setattr(evaluation, "optional_assessment", no_llm)
    events = observations()
    report = evaluation.score_report(submission(), events, [], None)
    known = {event["id"] for event in events}
    assert all(set(item["evidence_ids"]) <= known for item in report["criteria"])


def test_report_flags_unverified_persistence_and_optional_repository():
    report = evaluation.score_report(submission(), observations(), [], None)
    assert any("persistence" in flag.lower() for flag in report["review_flags"])
    assert any("repository" in flag.lower() for flag in report["review_flags"])
    assert report["evidence_audit"]["observation_count"] == len(observations())


def test_google_form_pdf_fields_are_extracted(monkeypatch):
    import app.pdf_submission as parser

    class Page:
        def extract_text(self):
            return """Project Name
PantryPal
Participant Name(s)
Alex Smith, Sam Jones
Problem Statement
Small shops lose food when expiry dates are not tracked.
Description
A dashboard helps shop owners track products and reduce waste."""

    class Reader:
        pages = [Page()]

    monkeypatch.setattr(parser, "PdfReader", lambda *args, **kwargs: Reader())
    details, text = extract_form_details(b"%PDF-fake")
    assert details["project_name"] == "PantryPal"
    assert details["participant_names"] == ["Alex Smith", "Sam Jones"]
    assert "expiry dates" in details["problem_statement"]
    assert "reduce waste" in details["solution_description"]
    assert "Project Name" in text


def test_pdf_missing_form_fields_is_rejected(monkeypatch):
    import app.pdf_submission as parser

    class Page:
        def extract_text(self):
            return "An unrelated PDF page without the required form fields."

    class Reader:
        pages = [Page()]

    monkeypatch.setattr(parser, "PdfReader", lambda *args, **kwargs: Reader())
    try:
        extract_form_details(b"%PDF-fake")
    except SubmissionPdfError as exc:
        assert "Project Name" in str(exc)
    else:
        raise AssertionError("A PDF without the required labels must not be accepted")


def test_localhost_target_is_blocked_before_browser_navigation():
    assert not public_http_url("http://127.0.0.1:8000")
    assert not public_http_url("file:///etc/passwd")


def test_credentials_are_encrypted_and_round_trip(monkeypatch):
    from cryptography.fernet import Fernet
    test_settings = Settings(judge_encryption_key=Fernet.generate_key().decode())
    monkeypatch.setattr(security, "get_settings", lambda: test_settings)
    secret = '{"username":"judge@example.com","password":"not-a-real-password"}'
    ciphertext = security.encrypt_secret(secret)
    assert secret not in ciphertext
    assert security.decrypt_secret(ciphertext) == secret
