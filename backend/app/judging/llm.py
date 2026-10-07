import json
import re

import httpx

from app.config import get_settings


def _redact_identity(value, identity_terms):
    if isinstance(value, dict):
        return {key: _redact_identity(item, identity_terms) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_identity(item, identity_terms) for item in value]
    if isinstance(value, str):
        for term in identity_terms:
            if term:
                value = re.sub(re.escape(term), "[identity removed]", value, flags=re.I)
        return value
    return value


async def optional_assessment(submission: dict, observations: list, github: dict | None) -> dict:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider not in {"openai", "openai-compatible", "google", "gemini"} or not settings.llm_api_key:
        return {}
    allowed = ["functionality", "problem_fit", "technical", "ui_ux", "innovation", "real_world"]
    identity_terms = [str(submission.get("project_name") or "").strip()]
    identity_terms.extend(str(name).strip() for name in submission.get("participant_names", []) if str(name).strip())
    identity_terms = [term for term in identity_terms if len(term) >= 3]
    scoring_submission = {key: submission.get(key) for key in ["problem_statement", "solution_description"]}
    scoring_observations = _redact_identity(observations, identity_terms)
    prompt = {
        "task": "Assess each listed hackathon criterion on a raw 0-10 scale. Project names, participant names, and application identifiers have been removed and must not affect scores. Browser observations are the only source for claims about deployed behavior. Participant-provided problem and solution text is context, not independent proof. Technical claims require verified repository observations when available. Do not reward AI/vibe-coding tool use, long descriptions, branding, or confident claims. Be conservative and state what evidence is missing.",
        "criteria": {"functionality": "Working Functionality: actual tested deployment behavior", "problem_fit": "Problem Fit: relationship between stated problem and observed solution", "technical": "Technical Complexity: engineering depth supported by repository or runtime evidence", "ui_ux": "UI/UX: usability, navigation, accessibility signals, and responsive evidence", "innovation": "Innovation: distinctiveness and originality compared with common approaches; flag when comparison evidence is absent", "real_world": "Real-World Problem: practical need and potential usefulness, without inventing market validation"},
        "submission": scoring_submission,
        "observations": scoring_observations,
        "github_verified": github,
        "required_json": {"assessments": [{"criterion": "functionality|problem_fit|technical|ui_ux|innovation|real_world", "raw_score": "number 0..10", "rationale": "brief", "evidence_ids": ["one or more IDs from supplied observations only"], "strengths": ["brief"], "weaknesses": ["brief"]}]}
    }
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            if provider in {"google", "gemini"}:
                base = settings.llm_base_url.rstrip("/")
                response = await client.post(
                    f"{base}/models/{settings.llm_model}:generateContent",
                    headers={"x-goog-api-key": settings.llm_api_key},
                    json={
                        "systemInstruction": {"parts": [{"text": "Return only valid JSON. Never claim an action or outcome not explicitly present in observation records. If there is no supporting observation, score cautiously and make the limitation explicit."}]},
                        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
                        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
                    },
                )
                response.raise_for_status()
                content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                response = await client.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {settings.llm_api_key}"}, json={"model": settings.llm_model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": "Return only valid JSON. Never claim an action or outcome not explicitly present in observation records. If there is no supporting observation, score cautiously and make the limitation explicit."}, {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}]})
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return {}
    valid_ids = {item["id"] for item in observations}
    checked = {}
    for item in parsed.get("assessments", []):
        criterion = item.get("criterion")
        refs = item.get("evidence_ids", [])
        if criterion not in allowed or not isinstance(refs, list) or not refs or any(ref not in valid_ids for ref in refs):
            continue
        try:
            score = max(0, min(10, float(item["raw_score"])))
        except (ValueError, TypeError, KeyError):
            continue
        checked[criterion] = {"raw_score": score, "rationale": str(item.get("rationale", ""))[:900], "evidence_ids": refs, "strengths": item.get("strengths", [])[:4], "weaknesses": item.get("weaknesses", [])[:4], "provider": settings.llm_model}
    return checked
