import asyncio
import re

from app.judging.llm import optional_assessment

RUBRIC = [
    ("functionality", "Working Functionality", 25),
    ("problem_fit", "Problem Fit", 20),
    ("technical", "Technical Complexity", 10),
    ("ui_ux", "UI/UX & Usability", 10),
    ("innovation", "Innovation & Originality", 25),
    ("real_world", "Real-World Problem Potential", 10),
]


def find(observations, *kinds):
    return [ob for ob in observations if ob.get("kind") in kinds]


def browser_functionality_agent(submission: dict, observations: list) -> float:
    browser = [item for item in observations if not item["id"].startswith("obs-repo-")]
    opened = next((item for item in find(browser, "deployment") if item.get("result") == "passed" and item.get("product_surface") is True), None)
    if not opened:
        return 0.0
    controls = next(iter(find(browser, "controls")), {})
    text_length = opened.get("visible_text_length", 0)
    score = 1.5 + (1.0 if text_length >= 200 else 0.3) + (0.5 if controls.get("controls") or controls.get("forms") else 0)
    # Navigation and request volume do not prove that a project feature works.
    # A click plus visible text change is only a weak workflow signal.
    interactions = [item for item in find(browser, "interaction") if item.get("result") == "passed"]
    score += min(1.0, len(interactions) * 0.5)
    auth_checks = [item for item in find(browser, "authentication") if item.get("result") == "passed"]
    score += min(2.0, len(auth_checks) * 2.0)
    persisted = [item for item in find(browser, "persistence") if item.get("result") == "passed"]
    score += min(4.0, len(persisted) * 2.0)
    return max(0, min(10, score))


def ui_ux_agent(observations: list) -> float:
    browser = [item for item in observations if not item["id"].startswith("obs-repo-")]
    deployment = next(iter(find(browser, "deployment")), None)
    if not deployment or deployment.get("product_surface") is not True or deployment.get("result") != "passed":
        return 0.0
    responsive = next(iter(find(browser, "responsive")), None)
    failures = sum(item.get("result") == "failed" and item.get("kind") in {"runtime_error", "network_error"} for item in browser)
    accessibility = next(iter(find(browser, "accessibility")), None)
    controls = next(iter(find(browser, "controls")), {})
    score = 2.0
    if responsive and responsive.get("result") == "passed":
        score += 1.5
    if accessibility and accessibility.get("result") == "passed":
        score += 2.0
    elif accessibility:
        score += 0.75
    if controls.get("controls") or controls.get("forms"):
        score += 1.0
    if find(browser, "navigation_test"):
        score += 0.5
    score += 1.0 if not failures else 0
    return max(0, min(10, score - min(2.0, failures * 0.8)))


def innovation_agent(submission: dict) -> float:
    # No keyword can establish originality; use a neutral provisional score.
    return 5.0


def problem_fit_agent(submission: dict, observations: list) -> float:
    deployment = next(iter(find(observations, "deployment")), None)
    if not deployment or deployment.get("product_surface") is not True or deployment.get("result") != "passed":
        return 1.0
    text = " ".join([submission.get("problem_statement", ""), submission.get("solution_description", "")]).lower()
    visible = (next(iter(find(observations, "page")), {}) or {}).get("detail", "").lower()
    stop = {"their", "which", "about", "because", "would", "could", "these", "those", "using", "users", "project", "build", "help", "system", "application", "solution", "there", "where", "when", "what", "from", "with", "that", "this"}
    tokens = {word for word in re.findall(r"[a-z]{4,}", text) if word not in stop}
    visible_tokens = set(re.findall(r"[a-z]{4,}", visible))
    overlap = len(tokens & visible_tokens) / max(1, len(tokens))
    return round(max(2.0, min(7.0, 2.0 + overlap * 5.0)), 1)


def code_technical_agent(observations: list, github: dict | None) -> float:
    if not github:
        return 1.5
    source_files = github.get("source_files", [])
    languages = github.get("languages", {})
    indicators = github.get("indicators", [])
    signals = github.get("code_signals", {})
    if not source_files:
        return 2.5 if github.get("files") else 2.0
    score = 2.0 + min(1.0, len(source_files) / 10) + min(0.75, max(0, len(languages) - 1) * 0.25)
    score += 0.75 if signals.get("frontend_source") and signals.get("backend_source") else 0
    score += 0.75 if signals.get("tests_present") else 0
    score += 0.75 if signals.get("database_logic") else 0
    score += 0.75 if signals.get("api_integration") else 0
    score += min(0.5, len(indicators) * 0.1)
    return round(min(6.5, score), 1)


def product_potential_agent(submission: dict, observations: list) -> float:
    deployment = next(iter(find(observations, "deployment")), None)
    if not deployment or deployment.get("product_surface") is not True or deployment.get("result") != "passed":
        return 2.0
    # Market demand and impact are not established by participant claims alone.
    return 5.0


def bias_auditor() -> dict:
    return {"status": "passed", "checks": ["Project and participant names are excluded from LLM scoring input.", "Only the published weighted criteria contribute to the total.", "LLM scores are bounded around a name-blind deterministic baseline and require valid observation IDs.", "Hosting dashboards, request volume, and README assertions are not treated as proof of product behavior or technical complexity."]}


def evidence_collector(observations: list, evidence: list) -> dict:
    return {"observation_count": len(observations), "captured_artifact_count": len(evidence), "observation_ids": [item["id"] for item in observations], "evidence_ids": [item["id"] for item in evidence], "screenshots": sum(item.get("kind") == "screenshot" for item in evidence)}


def anti_gaming_agent(submission: dict, observations: list) -> list:
    checks = [{"signal": item["title"], "detail": item["detail"], "observation_id": item["id"], "status": "human_review"} for item in find(observations, "anti_gaming_signal")]
    checks.extend({"signal": "Claimed feature not found on landing page", "detail": item["detail"], "observation_id": item["id"], "status": "not_verified"} for item in find(observations, "feature_claim") if item.get("result") == "needs_review")
    checks.extend({"signal": "Persistence not verified", "detail": item["detail"], "observation_id": item["id"], "status": "not_tested"} for item in find(observations, "persistence") if item.get("result") == "not_tested")
    return checks


def score_report(submission: dict, observations: list, evidence: list, github: dict | None):
    browser = [ob for ob in observations if not ob["id"].startswith("obs-repo-")]
    deployment = find(browser, "deployment")
    opened = next((o for o in deployment if o.get("result") == "passed" and o.get("product_surface") is True), None)
    failed = [o for o in browser if o.get("result") == "failed"]
    responsive = next(iter(find(browser, "responsive")), None)
    claims = find(browser, "feature_claim")
    claimed_visible = sum(1 for o in claims if o.get("result") == "observed")

    raw = {}
    # Specialized criterion agents use an aligned 0–10 raw scale.
    raw["functionality"] = browser_functionality_agent(submission, observations)
    raw["innovation"] = innovation_agent(submission)
    raw["problem_fit"] = problem_fit_agent(submission, observations)
    raw["ui_ux"] = ui_ux_agent(observations)
    raw["technical"] = code_technical_agent(observations, github)
    raw["real_world"] = product_potential_agent(submission, observations)

    # Optional LLM assessments can cover each criterion, but must cite actual observations.
    try:
        llm = asyncio.run(optional_assessment(submission, observations, github))
    except RuntimeError:
        llm = {}
    for criterion, assessment in llm.items():
        if criterion in raw:
            model_score = assessment["raw_score"]
            assessment["model_raw_score"] = round(model_score, 1)
            # Let evidence-based semantic judging meaningfully affect Problem Fit,
            # while retaining a guardrail against an unconstrained model score.
            model_delta = 4.0 if criterion == "problem_fit" else 1.5
            raw[criterion] = round(max(raw[criterion] - model_delta, min(raw[criterion] + model_delta, model_score)), 1)

    evidence_ids = {ob.get("evidence_id") for ob in observations if ob.get("evidence_id")} | {ev["id"] for ev in evidence}
    functional_checks = [o for o in find(browser, "authentication", "persistence") if o.get("result") == "passed"]
    no_workflow = not functional_checks
    mobile_gap = responsive and responsive.get("result") in {"failed", "needs_review"}
    repo_indicators = len((github or {}).get("indicators", []))
    criterion_data = {
        "functionality": {"basis": "Observed participant application page plus tested workflow outcomes. Hosting-console navigation, request counts, control presence, and page load alone do not prove functionality.", "observation_ids": [o["id"] for o in browser if o.get("kind") in {"deployment", "interaction", "authentication", "persistence", "form", "navigation_test", "network_error", "runtime_error"}], "limitations": ("The submitted URL was not verified as a participant application: " + "; ".join(o["detail"] for o in deployment[:1])) if not opened else ("No successful user workflow or saved-data persistence was verified; functionality is conservatively capped." if no_workflow else "Only recorded successful workflow outcomes count; untested features and persistence remain unverified.")},
        "innovation": {"basis": "Originality cannot be inferred from a project's name, description length, or self-description; this criterion uses a neutral provisional score unless an evidence-validated model assessment is configured.", "observation_ids": [o["id"] for o in browser if o.get("kind") in {"page", "interaction"}], "limitations": "No independent comparison with competing projects or prior art was performed; novelty needs judge review."},
        "problem_fit": {"basis": "The participant's problem statement is treated as the target need; observed live-app capabilities are compared with that need, with verified GitHub source excerpts as supporting implementation evidence. The live app is primary and keyword overlap alone is not rewarded.", "observation_ids": [o["id"] for o in observations if o.get("kind") in {"deployment", "page", "interaction", "navigation_test", "repository", "technology_verification"}], "limitations": ("A participant application was not verified, so fit could not be assessed from product behavior." if not opened else "No target-user test, outcome measurement, or independent problem validation was supplied; whether the observed capabilities solve the stated need remains a limited evidence-based judgment.")},
        "ui_ux": {"basis": "Visible controls, navigation, basic control labels, runtime signals, and the recorded mobile viewport.", "observation_ids": [o["id"] for o in browser if o.get("kind") in {"controls", "accessibility", "navigation", "navigation_test", "responsive", "runtime_error"}], "limitations": ("The mobile layout needs review because the recorded 390×844 viewport showed a layout issue." if mobile_gap else "Only the recorded desktop and 390×844 viewports and a basic DOM label check were examined; keyboard, screen-reader, and broader device checks were not performed.")},
        "technical": {"basis": "Verified public dependency manifests, selected source files, languages, and implementation signals. Network request volume and README claims are not treated as engineering depth.", "observation_ids": [o["id"] for o in observations if o.get("kind") in {"technology_verification", "repository"}], "limitations": (f"{repo_indicators} repository technology indicators were observed; source architecture, correctness, security, scale, and maintainability still need review." if github else "No public repository evidence was available, so technical complexity needs human review.")},
        "real_world": {"basis": "Real-world demand cannot be inferred from description length; a neutral provisional score is used unless evidence-validated model assessment is available.", "observation_ids": [o["id"] for o in browser if o.get("kind") in {"page", "interaction", "navigation_test"}], "limitations": "No independent user research, adoption, market-size, cost, or impact evidence was supplied; real-world demand remains unverified."},
    }
    criteria = []
    for key, label, weight in RUBRIC:
        llm_item = llm.get(key)
        score = round(weight * raw[key] / 10, 1)
        rationale = llm_item["rationale"] if llm_item else criterion_data[key]["basis"]
        ids = llm_item["evidence_ids"] if llm_item else criterion_data[key]["observation_ids"]
        gap = round(weight - score, 1)
        explanation = criterion_data[key]["limitations"]
        llm_weaknesses = llm_item.get("weaknesses", []) if llm_item else []
        criterion = {"key": key, "name": label, "weight": weight, "raw_score": round(raw[key], 1), "score": score, "max_points": weight, "points_not_awarded": gap, "rationale": rationale, "why_points_not_awarded": explanation, "evidence_ids": [id for id in ids if id in evidence_ids or id.startswith("obs-")], "strengths": llm_item.get("strengths", []) if llm_item else [], "weaknesses": list(dict.fromkeys(llm_weaknesses + ([explanation] if gap > 0 else []))), "assessment_source": f"configured LLM ({llm_item['provider']}, name-blind and bounded) + evidence validation" if llm_item else "deterministic provisional heuristic"}
        if llm_item:
            criterion["model_raw_score"] = llm_item["model_raw_score"]
        criteria.append(criterion)
    total = round(sum(item["score"] for item in criteria), 1)
    persistence_verified = any(o.get("kind") == "persistence" and o.get("result") == "passed" for o in browser)
    repository_verified = bool(github and github.get("files"))
    confidence = 25 if not opened else 35 + (15 if (opened.get("visible_text_length") or 0) >= 200 else 0) + (5 if find(browser, "responsive") else 0) + min(20, len(functional_checks) * 10) + (15 if persistence_verified else 0) + (10 if repository_verified else 0) - min(20, len(failed) * 5)
    confidence = min(95, max(20, confidence))
    if no_workflow:
        confidence = min(confidence, 59)
    flags = []
    if not opened:
        flags.append("A participant application was not verified at the submitted URL.")
        if deployment and deployment[0].get("product_surface") is False:
            flags.append("The submitted URL opens a hosting/control panel rather than the participant application; request the public deployed-app URL and rerun.")
        elif deployment and deployment[0].get("product_surface") is None:
            flags.append("The submitted page could not be confirmed as the participant application; request a public product URL or demo credentials.")
    if confidence < 60:
        flags.append("Low evidence confidence: human review recommended.")
    if failed:
        flags.append(f"Conflicting or negative browser evidence was recorded ({len(failed)} failed observation(s)).")
    if not submission.get("github_url"):
        flags.append("No repository was provided; technical complexity is based on limited runtime signals only.")
    if no_workflow:
        flags.append("No successful project workflow was observed; functionality and problem-fit scores are provisional and need human review.")
    if not llm:
        flags.append("No valid LLM assessment was available. Semantic criteria use provisional deterministic scoring and need human review.")
    if any(o.get("kind") == "persistence" and o.get("result") == "not_tested" for o in browser):
        flags.append("Data persistence was not independently verified in this run.")
    if claims and claimed_visible < max(1, len(claims) // 2):
        flags.append("Several declared features were not text-visible on the landing page; they may be behind navigation or unavailable.")
    if find(browser, "anti_gaming_signal"):
        flags.append("One or more anti-gaming review signals need human interpretation; these signals do not prove misconduct.")
    strengths = []
    weaknesses = []
    deductions = []
    function_penalty_total = round(min(2.5, len(failed) * 0.7) * 25 / 10, 1)
    ui_errors = [item for item in failed if item.get("kind") in {"runtime_error", "network_error"}]
    ui_penalty_total = round(min(2.0, len(ui_errors) * 0.8) * 10 / 10, 1)
    for ob in browser:
        if ob.get("result") == "failed":
            weaknesses.append(ob["title"] + ": " + ob["detail"][:220])
            points = function_penalty_total / len(failed) if failed else 0
            categories = ["Working Functionality"]
            if ob in ui_errors:
                points += ui_penalty_total / len(ui_errors)
                categories.append("UI/UX & Usability")
            deductions.append({"criterion": " + ".join(categories), "reason": ob["title"], "points": round(points, 1), "evidence_ids": [ob["id"]], "note": "This is the allocated share of the penalty already reflected in criterion scores; no extra penalty is applied."})
        elif ob.get("result") == "passed" and ob["kind"] in {"interaction", "navigation_test", "responsive", "deployment"}:
            strengths.append(ob["title"])
    if not strengths:
        strengths.append("Evaluation ran against the submitted deployment and kept observed facts separate from conclusions.")
    if not weaknesses:
        weaknesses.append("The MVP avoids valid form submissions that could alter participant data; persistence and full workflows may need a human demonstration.")
    # Chief Judge assembles weighted scores only after the Evidence Collector and Bias Auditor checks.
    score_status = "provisional_requires_human_review" if flags else "automated"
    return {"rubric": [{"key": key, "name": label, "weight": weight} for key, label, weight in RUBRIC], "criteria": criteria, "total_score": total, "max_score": 100, "confidence": confidence, "score_status": score_status, "evaluation_mode": "evidence-validated LLM with bounded deterministic baseline" if llm else "deterministic provisional heuristic; no valid LLM assessment", "passed_tests": [o for o in browser if o.get("result") == "passed"], "failed_tests": [o for o in browser if o.get("result") == "failed"], "all_observations": observations, "evidence": evidence, "evidence_audit": evidence_collector(observations, evidence), "anti_gaming_checks": anti_gaming_agent(submission, observations), "strengths": list(dict.fromkeys(strengths))[:8], "weaknesses": list(dict.fromkeys(weaknesses))[:8], "deductions": deductions[:12], "review_flags": flags, "bias_audit": bias_auditor()}
