from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SubmissionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_name: str
    application_number: str | None
    participant_names: list[str]
    deployed_url: str
    problem_statement: str
    solution_description: str
    source_pdf_available: bool = False
    github_url: str | None
    documentation_url: str | None
    ai_tools_metadata: list[str]
    created_at: str
    latest_run: dict | None = None


class JudgeRunView(BaseModel):
    id: str
    submission_id: str
    status: str
    phase: str
    progress: int
    total_score: float | None
    confidence: int | None
    report: dict | None
    observations: list
    evidence: list
    review_flags: list
    error_message: str | None
    created_at: str
    completed_at: str | None
