import json
from datetime import datetime, timezone

from celery import Celery

from app.config import get_settings
from app.database import SessionLocal
from app.judging.browser import run_browser_judge
from app.judging.evaluation import score_report
from app.judging.github_repo import inspect_repository
from app.models import JudgeRun, Submission
from app.security import decrypt_secret

settings = get_settings()
celery_app = Celery("hackathon_judge", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC", task_acks_late=True, worker_prefetch_multiplier=1)
@celery_app.task(bind=True, name="app.tasks.evaluate_submission", max_retries=3)
def evaluate_submission(self, run_id: str):
    db = SessionLocal()
    try:
        run = db.get(JudgeRun, run_id)
        if not run:
            return
        submission = db.get(Submission, run.submission_id)
        if not submission:
            run.status = "failed"
            run.error_message = "Submission was not found."
            db.commit()
            return
        run.status, run.phase, run.progress = "running", "Opening deployed app", 5
        run.started_at = datetime.now(timezone.utc)
        db.commit()
        payload = {key: getattr(submission, key) for key in ["application_number", "project_name", "participant_names", "deployed_url", "problem_statement", "solution_description", "github_url", "ai_tools_metadata"]}
        credentials = None
        if submission.credentials_ciphertext:
            try:
                credentials = json.loads(decrypt_secret(submission.credentials_ciphertext))
            except (ValueError, json.JSONDecodeError) as exc:
                run.review_flags = [f"Demo credentials could not be decrypted: {str(exc)[:220]}"]
        observations, evidence = run_browser_judge(payload, run_id, credentials)
        run.phase, run.progress, run.observations, run.evidence = "Reviewing public repository", 65, observations, evidence
        db.commit()
        repo_observations, repo_evidence, repo_summary = __import__("asyncio").run(inspect_repository(payload["github_url"], run_id))
        observations.extend(repo_observations)
        evidence.extend(repo_evidence)
        run.phase, run.progress, run.observations, run.evidence = "Scoring against the published rubric", 82, observations, evidence
        db.commit()
        report = score_report(payload, observations, evidence, repo_summary)
        run.status = "completed"
        run.phase = "Report ready"
        run.progress = 100
        run.total_score = report["total_score"]
        run.confidence = report["confidence"]
        run.report = report
        run.review_flags = report["review_flags"]
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"run_id": run_id, "status": run.status, "total_score": run.total_score}
    except Exception as exc:
        db.rollback()
        run = db.get(JudgeRun, run_id)
        if run:
            run.error_message = f"{type(exc).__name__}: {str(exc)[:1200]}"
            if self.request.retries < self.max_retries:
                run.status = "queued"
                run.phase = "Retry scheduled"
                run.progress = 0
                run.completed_at = None
            else:
                run.status = "failed"
                run.phase = "Evaluation failed"
                run.completed_at = datetime.now(timezone.utc)
            db.commit()
        if self.request.retries < self.max_retries:
            # Retry transient network or worker errors with increasing delays.
            raise self.retry(exc=exc, countdown=min(60 * (2 ** self.request.retries), 300))
        raise
    finally:
        db.close()
