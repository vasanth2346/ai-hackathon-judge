import base64
import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode, urlparse
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
import httpx
from sqlalchemy import func, text
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import GoogleAccount, JudgeRun, ParticipantRegistration, RegistrationPdfUpload, Submission
from app.pdf_submission import SubmissionPdfError, extract_form_details, extract_registration_rows
from app.tasks import evaluate_submission

settings = get_settings()
logger = logging.getLogger(__name__)
Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    # Upgrade the original local MVP schema without discarding prior submissions.
    connection.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS application_number VARCHAR(80)"))
    connection.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS source_pdf_file VARCHAR(255)"))
    connection.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS source_pdf_text TEXT"))
    connection.execute(text("ALTER TABLE submissions ALTER COLUMN team_name DROP NOT NULL"))
    connection.execute(text("ALTER TABLE submissions ALTER COLUMN core_features DROP NOT NULL"))
    connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_submissions_application_number ON submissions (application_number)"))
    connection.execute(text("ALTER TABLE google_accounts ALTER COLUMN google_subject DROP NOT NULL"))
    connection.execute(text("ALTER TABLE google_accounts ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"))
    connection.execute(text("ALTER TABLE participant_registrations ADD COLUMN IF NOT EXISTS phone VARCHAR(60) NOT NULL DEFAULT ''"))
    connection.execute(text("ALTER TABLE participant_registrations ADD COLUMN IF NOT EXISTS email VARCHAR(320)"))
    connection.execute(text("ALTER TABLE participant_registrations ADD COLUMN IF NOT EXISTS domain VARCHAR(80)"))
    connection.execute(text("ALTER TABLE participant_registrations ADD COLUMN IF NOT EXISTS open_innovation_details TEXT"))
    connection.execute(text("ALTER TABLE participant_registrations ADD COLUMN IF NOT EXISTS host_account_id VARCHAR(36)"))
    connection.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS host_account_id VARCHAR(36)"))
    connection.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS domain VARCHAR(80)"))
    connection.execute(text("ALTER TABLE judge_runs ADD COLUMN IF NOT EXISTS queued_at TIMESTAMPTZ"))
    connection.execute(text("ALTER TABLE judge_runs ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0"))
    connection.execute(text("UPDATE judge_runs SET queued_at = created_at WHERE queued_at IS NULL"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_participant_registrations_host_account_id ON participant_registrations (host_account_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_submissions_host_account_id ON submissions (host_account_id)"))
    # Keep existing local data visible to the first host account after enabling
    # host-specific dashboards; newly imported data is always scoped to its host.
    connection.execute(text("UPDATE participant_registrations SET host_account_id = (SELECT id FROM google_accounts WHERE role = 'host' ORDER BY created_at, id LIMIT 1) WHERE host_account_id IS NULL"))
    connection.execute(text("UPDATE submissions SET host_account_id = (SELECT id FROM google_accounts WHERE role = 'host' ORDER BY created_at, id LIMIT 1) WHERE host_account_id IS NULL"))
app = FastAPI(title="Hackathon Judge API", version="0.1.0", description="Evidence-first automated hackathon evaluation")
origins = list(dict.fromkeys([settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"]))
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"], allow_credentials=True)


async def _judge_queue_watchdog():
    """Re-dispatch queued evaluations that have not been claimed by a worker."""
    while True:
        await asyncio.sleep(30)
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            cutoff = now.timestamp() - settings.judge_queue_retry_after_seconds
            stale_runs = db.query(JudgeRun).filter(
                JudgeRun.status == "queued",
                JudgeRun.phase == "Waiting for judge worker",
                JudgeRun.queued_at.is_not(None),
                JudgeRun.queued_at <= datetime.fromtimestamp(cutoff, timezone.utc),
            ).with_for_update(skip_locked=True).limit(20).all()
            to_dispatch = []
            for run in stale_runs:
                run.retry_count += 1
                run.queued_at = now
                run.phase = "Waiting for judge worker"
                run.error_message = f"The judge worker has not started yet. Automatic retry {run.retry_count} was requested."
                to_dispatch.append(run.id)
            db.commit()
            for run_id in to_dispatch:
                try:
                    evaluate_submission.delay(run_id)
                except Exception as exc:
                    run = db.get(JudgeRun, run_id)
                    if run and run.status == "queued":
                        run.phase = "Waiting for judge worker"
                        run.queued_at = datetime.now(timezone.utc)
                        run.error_message = f"Automatic retry could not reach the job queue and will be retried: {str(exc)[:500]}"
                        db.commit()
        except Exception:
            logger.exception("Judge queue watchdog failed")
            db.rollback()
        finally:
            db.close()


@app.on_event("startup")
async def start_judge_queue_watchdog():
    asyncio.create_task(_judge_queue_watchdog())

HOST_COOKIE_NAME = "proof_host_session"
PARTICIPANT_COOKIE_NAME = "proof_participant_session"
LEGACY_COOKIE_NAME = "proof_session"
SESSION_SECONDS = 8 * 60 * 60
PARTICIPANT_DOMAINS = {
    "AI for Healthcare",
    "AI for Agriculture",
    "AI for Finance",
    "AI for Cybersecurity",
    "AI for Biotech & Deep Tech",
    "AI for Computer Vision",
    "Open Innovation",
}


def encode_session(payload: dict) -> str:
    if not settings.auth_secret_key:
        raise HTTPException(503, "Secure login is not configured")
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(settings.auth_secret_key.encode(), body.encode(), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def decode_session(token: str | None) -> dict | None:
    if not token or not settings.auth_secret_key:
        return None
    try:
        body, signature = token.split(".", 1)
        expected = base64.urlsafe_b64encode(hmac.new(settings.auth_secret_key.encode(), body.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def set_session(response: Response, payload: dict):
    cookie_name = HOST_COOKIE_NAME if payload.get("role") == "host" else PARTICIPANT_COOKIE_NAME
    response.set_cookie(cookie_name, encode_session(payload), max_age=SESSION_SECONDS, httponly=True, secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite, path="/")


def require_host(proof_session: str | None = Cookie(None, alias=HOST_COOKIE_NAME)):
    session = decode_session(proof_session)
    if not session or session.get("role") != "host":
        raise HTTPException(401, "Host login required")
    return session


def require_participant(proof_session: str | None = Cookie(None, alias=PARTICIPANT_COOKIE_NAME)):
    session = decode_session(proof_session)
    if not session or session.get("role") != "participant":
        raise HTTPException(401, "Participant login required")
    return session


def password_digest(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return "pbkdf2_sha256$310000$" + base64.urlsafe_b64encode(salt).decode().rstrip("=") + "$" + base64.urlsafe_b64encode(derived).decode().rstrip("=")


def password_matches(password: str, stored: str | None) -> bool:
    try:
        algorithm, rounds, salt_text, digest_text = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (AttributeError, ValueError):
        return False


def participant_registration_for_email(email: str, db: Session) -> ParticipantRegistration | None:
    normalized = email.strip().lower()
    if not normalized:
        return None
    registrations = db.query(ParticipantRegistration).filter(
        func.lower(ParticipantRegistration.email) == normalized
    ).all()
    if len(registrations) > 1:
        raise HTTPException(409, "This email appears in more than one host roster. Ask a host to resolve the duplicate registration.")
    return registrations[0] if registrations else None


def issue_account_session(response: Response, account: GoogleAccount, db: Session):
    registration = None
    if account.role == "participant" and account.email_verified:
        registration = participant_registration_for_email(account.email, db)
        account.application_number = registration.application_number if registration else None
        db.commit()
    set_session(response, {"role": account.role, "email": account.email, "sub": account.google_subject or "", "account_id": account.id, "application_number": account.application_number, "exp": int(time.time()) + SESSION_SECONDS})


def normalized_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > 320 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "Enter a valid email address")
    return email


def validate_external_url(value, allowed_hosts=None):
    if not value:
        return
    parsed = urlparse(str(value))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, "URLs must use HTTP(S) and cannot contain embedded credentials")
    if allowed_hosts and parsed.hostname.lower() not in allowed_hosts:
        raise HTTPException(422, "GitHub URL must use github.com")


def run_view(run: JudgeRun):
    return {"id": run.id, "submission_id": run.submission_id, "status": run.status, "phase": run.phase, "progress": run.progress, "total_score": run.total_score, "confidence": run.confidence, "report": run.report, "observations": run.observations or [], "evidence": run.evidence or [], "review_flags": run.review_flags or [], "error_message": run.error_message, "created_at": run.created_at.isoformat() if run.created_at else None, "completed_at": run.completed_at.isoformat() if run.completed_at else None}


def submission_view(submission: Submission, latest: JudgeRun | None = None):
    return {"id": submission.id, "application_number": submission.application_number, "project_name": submission.project_name, "participant_names": submission.participant_names, "deployed_url": submission.deployed_url, "domain": submission.domain, "problem_statement": submission.problem_statement, "solution_description": submission.solution_description, "source_pdf_available": bool(submission.source_pdf_file), "github_url": submission.github_url, "documentation_url": submission.documentation_url, "ai_tools_metadata": submission.ai_tools_metadata, "created_at": submission.created_at.isoformat() if submission.created_at else None, "latest_run": run_view(latest) if latest else None}


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as exc:
        raise HTTPException(503, "Database is unavailable") from exc


@app.get("/api/public/dashboard")
def public_dashboard(db: Session = Depends(get_db)):
    return {
        "project_count": db.query(Submission).count(),
        "judged_count": db.query(JudgeRun).filter(JudgeRun.status == "completed").count(),
    }


def auth_redirect(role: str, error: str | None = None):
    path = "/host-login" if role == "host" else "/participant-login"
    target = settings.frontend_origin.rstrip("/") + path
    if error:
        target += "?error=" + error
    return RedirectResponse(target, status_code=303)


@app.get("/api/auth/google/status")
def google_auth_status():
    client_id_configured = bool(settings.google_client_id.strip())
    client_secret_configured = bool(settings.google_client_secret.strip())
    auth_secret_configured = bool(settings.auth_secret_key.strip())
    redirect_uri_configured = bool(settings.google_redirect_uri.strip())
    return {
        "configured": all((client_id_configured, client_secret_configured, auth_secret_configured, redirect_uri_configured)),
        "checks": {
            "google_client_id": client_id_configured,
            "google_client_secret": client_secret_configured,
            "auth_secret_key": auth_secret_configured,
            "google_redirect_uri": redirect_uri_configured,
        },
    }


@app.post("/api/auth/email/signup", status_code=201)
def email_signup(payload: dict, response: Response, db: Session = Depends(get_db)):
    role = payload.get("role")
    if role not in {"host", "participant"}:
        raise HTTPException(422, "Choose host or participant sign up")
    email = normalized_email(str(payload.get("email", "")))
    if role == "host":
        raise HTTPException(403, "Host accounts are provisioned by the event administrator. Use Host Login.")
    registration = participant_registration_for_email(email, db)
    if not registration:
        raise HTTPException(403, "This email is not listed in a host’s registration document.")
    password = str(payload.get("password", ""))
    if len(password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    account = db.query(GoogleAccount).filter(GoogleAccount.email == email, GoogleAccount.role == role).first()
    if account:
        if account.password_hash:
            raise HTTPException(409, "An account already exists for this email. Sign in instead.")
        account.password_hash = password_digest(password)
        account.email_verified = True
        account.application_number = registration.application_number
    else:
        account = GoogleAccount(email=email, password_hash=password_digest(password), email_verified=True, role=role, application_number=registration.application_number)
        db.add(account)
    try:
        db.commit()
        db.refresh(account)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "An account already exists for this email and role") from exc
    issue_account_session(response, account, db)
    return {"role": role, "email": email}


@app.post("/api/auth/email/signin")
def email_signin(payload: dict, response: Response, db: Session = Depends(get_db)):
    role = payload.get("role")
    if role not in {"host", "participant"}:
        raise HTTPException(422, "Choose host or participant sign in")
    email = normalized_email(str(payload.get("email", "")))
    if role == "host":
        configured_hosts = []
        for host_email, host_password in ((settings.host_login_1_email, settings.host_login_1_password), (settings.host_login_2_email, settings.host_login_2_password)):
            if host_email.strip() and host_password.strip():
                configured_hosts.append((normalized_email(host_email), host_password))
        configured_password = next((host_password for host_email, host_password in configured_hosts if host_email == email), None)
        if not configured_password:
            raise HTTPException(401, "Email or password is incorrect")
        account = db.query(GoogleAccount).filter(GoogleAccount.email == email, GoogleAccount.role == "host").first()
        if not account:
            account = GoogleAccount(email=email, password_hash=password_digest(configured_password), email_verified=True, role="host", application_number=None)
            db.add(account)
            db.commit()
            db.refresh(account)
        elif not password_matches(configured_password, account.password_hash):
            account.password_hash = password_digest(configured_password)
            account.email_verified = True
            db.commit()
        if not password_matches(str(payload.get("password", "")), account.password_hash):
            raise HTTPException(401, "Email or password is incorrect")
        issue_account_session(response, account, db)
        return {"role": role, "email": email}
    registration = participant_registration_for_email(email, db)
    if not registration:
        raise HTTPException(403, "This email is not listed in a host’s registration document.")
    account = db.query(GoogleAccount).filter(GoogleAccount.email == email, GoogleAccount.role == role).first()
    if not account or not password_matches(str(payload.get("password", "")), account.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    if not account.email_verified or account.application_number != registration.application_number:
        account.email_verified = True
        account.application_number = registration.application_number
        db.commit()
    issue_account_session(response, account, db)
    return {"role": role, "email": email}


@app.post("/api/host/registrations", status_code=201)
async def upload_registration_pdf(
    pdf: UploadFile = File(...),
    _host: dict = Depends(require_host),
    db: Session = Depends(get_db),
):
    contents = await pdf.read(10_000_001)
    if len(contents) > 10_000_000:
        raise HTTPException(413, "Registration document must be 10 MB or smaller")
    filename = (pdf.filename or "registrations").replace("\\", "/").split("/")[-1][:255]
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".csv", ".tsv", ".xlsx", ".xlsm"}:
        raise HTTPException(415, "Upload a searchable PDF, CSV, TSV, or Excel .xlsx file")
    if extension == ".pdf" and not contents.startswith(b"%PDF-"):
        raise HTTPException(415, "The selected file is not a valid PDF")
    try:
        rows, skipped_count = extract_registration_rows(contents, filename)
    except SubmissionPdfError as exc:
        raise HTTPException(422, str(exc)) from exc
    host_account_id = _host.get("account_id")
    if not host_account_id:
        raise HTTPException(401, "Sign in again to upload registrations")

    # One verified email must resolve to one host roster so participant submissions
    # can be routed to the correct host without ambiguity.
    for row in rows:
        if not row["email"]:
            continue
        existing_rows = db.query(ParticipantRegistration).filter(
            func.lower(ParticipantRegistration.email) == row["email"]
        ).all()
        if any(existing.host_account_id and existing.host_account_id != host_account_id for existing in existing_rows):
            raise HTTPException(409, "A participant email is already registered in another host roster. Each email must identify one host roster.")

    created = 0
    updated = 0
    results = []
    for row in rows:
        email = row["email"] or None
        registration = None
        if email:
            registration = db.query(ParticipantRegistration).filter(
                ParticipantRegistration.host_account_id == host_account_id,
                func.lower(ParticipantRegistration.email) == email,
            ).first()
        if not registration and row["phone"]:
            candidates = db.query(ParticipantRegistration).filter(ParticipantRegistration.host_account_id == host_account_id, ParticipantRegistration.phone == row["phone"]).all()
            registration = next((candidate for candidate in candidates if candidate.participant_name.strip().casefold() == row["participant_name"].strip().casefold()), None)
        if registration:
            registration.participant_name = row["participant_name"]
            if row["phone"]:
                registration.phone = row["phone"]
            if email:
                registration.email = email
            updated += 1
        else:
            application_number = str(secrets.randbelow(90_000_000) + 10_000_000)
            while db.get(ParticipantRegistration, application_number) or db.query(Submission).filter(Submission.application_number == application_number).first():
                application_number = str(secrets.randbelow(90_000_000) + 10_000_000)
            registration = ParticipantRegistration(application_number=application_number, host_account_id=host_account_id, participant_name=row["participant_name"], phone=row["phone"], email=email, college_name="")
            db.add(registration)
            created += 1
        results.append(registration)
    filename = filename or "registrations"
    upload_record = RegistrationPdfUpload(host_account_id=host_account_id, filename=filename, pdf_data=contents, participant_count=len(results), skipped_count=skipped_count)
    db.add(upload_record)
    db.commit()
    email_missing_count = sum(1 for row in results if not row.email)
    return {"uploaded": True, "participant_count": len(results), "created_count": created, "updated_count": updated, "skipped_count": skipped_count, "email_missing_count": email_missing_count, "status_lines": ["Registration document uploaded successfully.", f"{len(results)} participants found; {email_missing_count} missing email; {skipped_count} unreadable rows."]}


@app.get("/api/host/registrations")
def list_host_registrations(_host: dict = Depends(require_host), db: Session = Depends(get_db)):
    registrations = db.query(ParticipantRegistration).filter(ParticipantRegistration.host_account_id == _host.get("account_id")).order_by(ParticipantRegistration.created_at.desc()).all()
    return [{"application_number": row.application_number, "participant_name": row.participant_name, "phone": row.phone, "email": row.email, "college_name": row.college_name, "submitted": bool(db.query(Submission.id).filter(Submission.application_number == row.application_number).first())} for row in registrations]


@app.get("/api/auth/google/start")
def google_auth_start(
    role: Literal["host", "participant"],
    intent: Literal["signin", "signup"],
    application_number: str | None = None,
    db: Session = Depends(get_db),
):
    if role == "host":
        return auth_redirect("host", "host_google_disabled")
    if not settings.google_client_id or not settings.google_client_secret or not settings.auth_secret_key:
        return auth_redirect(role, "google_not_configured")
    application_number = None

    oauth_state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state_cookie = encode_session({
        "state": oauth_state, "nonce": nonce, "verifier": verifier, "role": role,
        "intent": intent, "application_number": application_number,
        "exp": int(time.time()) + 600,
    })
    response = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": oauth_state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }), status_code=302)
    response.set_cookie("proof_oauth_state", state_cookie, max_age=600, httponly=True, secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite, path="/")
    return response


@app.get("/api/auth/google/callback")
async def google_auth_callback(
    code: str | None = None,
    state: str | None = None,
    provider_error: str | None = None,
    proof_oauth_state: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    oauth = decode_session(proof_oauth_state)
    # A missing/invalid state cookie must not send a participant through to
    # the host login page. Host OAuth is disabled, so only a valid host state
    # is redirected to the host login route.
    if oauth and oauth.get("role") == "host":
        return auth_redirect("host", "host_google_disabled")
    role = "participant"
    if not oauth or not state or not secrets.compare_digest(str(oauth.get("state", "")), state):
        return auth_redirect(role, "oauth_state_invalid")
    if provider_error or not code or not settings.google_client_id or not settings.google_client_secret:
        return auth_redirect(role, "google_signin_failed")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token_response = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": oauth["verifier"],
            })
            token_response.raise_for_status()
            token_data = token_response.json()
        claims = id_token.verify_oauth2_token(token_data["id_token"], google_requests.Request(), settings.google_client_id)
        if not secrets.compare_digest(str(claims.get("nonce", "")), str(oauth.get("nonce", ""))):
            return auth_redirect(role, "oauth_state_invalid")
        if not claims.get("email_verified"):
            return auth_redirect(role, "google_email_unverified")
        subject = str(claims["sub"])
        email = str(claims["email"]).strip().lower()
        account = db.query(GoogleAccount).filter(GoogleAccount.google_subject == subject).first()
        if not account:
            account = db.query(GoogleAccount).filter(GoogleAccount.email == email, GoogleAccount.role == role).first()
            if account and account.google_subject:
                return auth_redirect(role, "account_role_mismatch")
            if account:
                account.google_subject = subject
        if account:
            if account.role != role:
                return auth_redirect(role, "account_role_mismatch")
            account.email = email
            account.email_verified = True
        elif oauth.get("intent") == "signin":
            return auth_redirect(role, "account_not_found")
        else:
            application_number = None
            account = GoogleAccount(google_subject=subject, email=email, email_verified=True, role=role, application_number=application_number)
            db.add(account)
            try:
                db.commit()
                db.refresh(account)
            except IntegrityError:
                db.rollback()
                account = db.query(GoogleAccount).filter(GoogleAccount.google_subject == subject).first()
                if not account or account.role != role:
                    return auth_redirect(role, "account_role_mismatch")
        db.commit()
        if role == "participant":
            registration = participant_registration_for_email(account.email, db) if account.email_verified else None
            account.application_number = registration.application_number if registration else None
            db.commit()
        destination = "/host-dashboard" if role == "host" else "/participant"
        response = RedirectResponse(settings.frontend_origin.rstrip("/") + destination, status_code=303)
        set_session(response, {
            "role": account.role, "email": account.email, "sub": account.google_subject,
            "account_id": account.id, "application_number": account.application_number,
            "exp": int(time.time()) + SESSION_SECONDS,
        })
        response.delete_cookie("proof_oauth_state", path="/", httponly=True, secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite)
        return response
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        db.rollback()
        return auth_redirect(role, "google_signin_failed")


@app.get("/api/auth/me")
def auth_me(
    host_session: str | None = Cookie(None, alias=HOST_COOKIE_NAME),
    participant_session: str | None = Cookie(None, alias=PARTICIPANT_COOKIE_NAME),
    legacy_session: str | None = Cookie(None, alias=LEGACY_COOKIE_NAME),
):
    session = decode_session(host_session) or decode_session(participant_session) or decode_session(legacy_session)
    if not session:
        raise HTTPException(401, "Sign in required")
    if session.get("role") == "host":
        account_id = session.get("account_id")
        configured_emails = {value.strip().lower() for value in (settings.host_login_1_email, settings.host_login_2_email) if value.strip()}
        if not configured_emails:
            return {"role": "host", "email": session.get("email")}
        if str(session.get("email", "")).strip().lower() not in configured_emails:
            raise HTTPException(401, "Host account is no longer authorized")
    return {"role": session.get("role"), "email": session.get("email")}


@app.post("/api/auth/logout")
def logout(
    response: Response,
    role: Literal["host", "participant"] | None = Query(None),
    host_session: str | None = Cookie(None, alias=HOST_COOKIE_NAME),
    participant_session: str | None = Cookie(None, alias=PARTICIPANT_COOKIE_NAME),
    legacy_session: str | None = Cookie(None, alias=LEGACY_COOKIE_NAME),
):
    # Clear only the role that initiated logout so signing out of one dashboard
    # does not terminate the other account in another tab.
    session = decode_session(participant_session) or decode_session(host_session) or decode_session(legacy_session)
    logout_role = role or (session.get("role") if session else "host")
    cookie_name = PARTICIPANT_COOKIE_NAME if logout_role == "participant" else HOST_COOKIE_NAME
    response.delete_cookie(cookie_name, path="/", httponly=True, secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite)
    response.delete_cookie(LEGACY_COOKIE_NAME, path="/", httponly=True, secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite)
    response.delete_cookie("proof_oauth_state", path="/", httponly=True, secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite)
    return {"ok": True}


@app.get("/api/participant/me")
def participant_details(session: dict = Depends(require_participant), db: Session = Depends(get_db)):
    account = db.get(GoogleAccount, session.get("account_id"))
    email = account.email.strip().lower() if account else str(session.get("email", "")).strip().lower()
    registration = participant_registration_for_email(email, db) if account and account.email_verified else None
    if not registration:
        registration_message = (
            "Sign in with Google to verify the email used in the host’s roster."
            if not account or not account.email_verified
            else "No host registration matches this Google email. Ask the host to add this email to their roster."
        )
        return {
            "linked": False, "needs_profile": False, "application_number": None, "participant_name": "", "phone": "",
            "email": email, "domain": None, "college_name": "", "project_name": "", "problem_statement": "",
            "solution_description": "", "deployed_url": "", "github_url": None,
            "has_submission": False, "evaluation_status": "not_started",
            "registration_message": registration_message,
        }
    application_number = registration.application_number
    if account.application_number != application_number:
        account.application_number = application_number
        db.commit()
    submission = db.query(Submission).options(selectinload(Submission.runs)).filter(Submission.application_number == application_number).first()
    latest = sorted(submission.runs, key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[0] if submission and submission.runs else None
    return {
        "linked": True,
        "needs_profile": not bool(registration.domain),
        "application_number": application_number,
        "participant_name": registration.participant_name if registration else (submission.participant_names[0] if submission.participant_names else ""),
        "phone": registration.phone if registration else "",
        "email": account.email if account else session.get("email", ""),
        "college_name": registration.college_name if registration else "",
        "project_name": submission.project_name if submission else "",
        "problem_statement": submission.problem_statement if submission else "",
        # Project descriptions remain available to the host and judge, but are
        # not exposed in the participant dashboard response.
        "deployed_url": submission.deployed_url if submission else "",
        "github_url": submission.github_url if submission else None,
        "domain": (submission.domain or registration.domain) if submission else registration.domain,
        "has_submission": bool(submission),
        "evaluation_status": latest.status if latest else "not_started",
        "registration_message": "",
    }


@app.post("/api/participant/verify-registration")
def verify_participant_registration(
    participant_name: str = Form(..., min_length=2, max_length=200),
    phone: str = Form(..., min_length=7, max_length=60),
    domain: str = Form(..., min_length=2, max_length=80),
    open_innovation_details: str = Form("", max_length=4000),
    session: dict = Depends(require_participant),
    db: Session = Depends(get_db),
):
    account = db.get(GoogleAccount, session.get("account_id"))
    if not account or account.role != "participant" or not account.email_verified:
        raise HTTPException(403, "Sign in with the verified email from the host’s registration document")
    registration = participant_registration_for_email(account.email, db)
    if not registration:
        raise HTTPException(403, "This verified email is not listed in a host’s registration document")
    if domain not in PARTICIPANT_DOMAINS:
        raise HTTPException(422, "Choose one of the listed project domains")
    if domain == "Open Innovation" and len(open_innovation_details.strip()) < 10:
        raise HTTPException(422, "Describe the project you are working on for Open Innovation")
    registration.participant_name = participant_name.strip()
    registration.phone = phone.strip()
    registration.domain = domain
    registration.open_innovation_details = open_innovation_details.strip() if domain == "Open Innovation" else None
    account.application_number = registration.application_number
    db.commit()
    return {"verified": True, "email": account.email}


@app.post("/api/participant/submission", status_code=201)
def participant_submission(
    project_name: str = Form(..., min_length=2, max_length=160),
    deployed_url: str = Form(..., min_length=8, max_length=2048),
    github_url: str = Form(..., min_length=8, max_length=2048),
    problem_statement: str = Form(..., min_length=10, max_length=4000),
    solution_description: str = Form("", max_length=4000),
    session: dict = Depends(require_participant),
    db: Session = Depends(get_db),
):
    account = db.get(GoogleAccount, session.get("account_id"))
    if not account or account.role != "participant" or not account.email_verified:
        raise HTTPException(403, "Use Google sign-in to verify the participant email")
    registration = participant_registration_for_email(account.email, db)
    if not registration:
        raise HTTPException(403, "No host registration matches this email")
    application_number = registration.application_number
    account.application_number = application_number
    if db.query(Submission).filter(Submission.application_number == application_number).first():
        raise HTTPException(409, "A project has already been submitted for this registration ID")
    validate_external_url(deployed_url)
    validate_external_url(github_url, {"github.com"})
    project_description = solution_description.strip()
    if registration.open_innovation_details:
        project_description = (project_description + "\n\nOpen Innovation project details: " + registration.open_innovation_details).strip()
    submission = Submission(application_number=application_number, host_account_id=registration.host_account_id, project_name=project_name.strip(), team_name=None, participant_names=[registration.participant_name], deployed_url=deployed_url.strip(), domain=registration.domain, problem_statement=problem_statement.strip(), solution_description=project_description, core_features=None, github_url=github_url.strip(), ai_tools_metadata=[])
    db.add(submission)
    db.commit()
    db.refresh(submission)
    run = JudgeRun(submission_id=submission.id, status="queued", phase="Waiting for judge worker", progress=0, observations=[], evidence=[], review_flags=[])
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        evaluate_submission.delay(run.id)
    except Exception:
        run.status = "failed"
        run.phase = "Queue unavailable"
        run.error_message = "The project was delivered to the host, but automatic evaluation could not start. The host can retry when the judge worker is available."
        db.commit()
    return submission_view(submission, run)


@app.post("/api/submissions", status_code=201)
async def create_submission(
    application_number: str = Form(..., min_length=1, max_length=80),
    deployed_url: str = Form(..., min_length=8, max_length=2048),
    github_url: str | None = Form(None, max_length=2048),
    pdf: UploadFile = File(...),
    _host: dict = Depends(require_host),
    db: Session = Depends(get_db),
):
    application_number = application_number.strip()
    if not application_number.isdigit():
        raise HTTPException(422, "Application ID must contain numbers only")
    validate_external_url(deployed_url)
    validate_external_url(github_url, {"github.com"})
    if db.query(Submission).filter(Submission.application_number == application_number).first():
        raise HTTPException(409, "That application ID has already been submitted")
    contents = await pdf.read(10_000_001)
    if len(contents) > 10_000_000:
        raise HTTPException(413, "PDF must be 10 MB or smaller")
    if not contents.startswith(b"%PDF-"):
        raise HTTPException(415, "Upload a participant details PDF")
    try:
        details, extracted_text = extract_form_details(contents)
    except SubmissionPdfError as exc:
        raise HTTPException(422, str(exc)) from exc
    project_name = str(details["project_name"]).strip()
    problem = str(details["problem_statement"]).strip()
    description = str(details["solution_description"]).strip()
    participants = details["participant_names"]
    if len(project_name) < 2 or len(problem) < 10 or len(description) < 10 or len(participants) != 1:
        raise HTTPException(422, "The PDF must contain a project name, one participant name, a problem statement, and a description")
    if db.query(Submission).filter(Submission.application_number == application_number).first():
        raise HTTPException(409, "That application ID has already been submitted")

    submission_id = str(uuid4())
    pdf_name = "participant-details.pdf"
    pdf_path = settings.evidence_dir / "submissions" / submission_id / pdf_name
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(contents)
    submission = Submission(
        id=submission_id,
        host_account_id=_host.get("account_id"),
        application_number=application_number,
        project_name=project_name[:160],
        team_name=None,
        participant_names=participants,
        deployed_url=deployed_url,
        problem_statement=problem[:4000],
        solution_description=description[:4000],
        core_features=None,
        source_pdf_file=pdf_name,
        source_pdf_text=extracted_text,
        github_url=github_url,
        ai_tools_metadata=[],
    )
    try:
        db.add(submission)
        db.commit()
        db.refresh(submission)
    except Exception:
        db.rollback()
        pdf_path.unlink(missing_ok=True)
        raise
    return submission_view(submission)


@app.get("/api/submissions")
def list_submissions(_host: dict = Depends(require_host), db: Session = Depends(get_db)):
    submissions = db.query(Submission).options(selectinload(Submission.runs)).filter(Submission.host_account_id == _host.get("account_id")).order_by(Submission.created_at.desc()).all()
    return [submission_view(item, sorted(item.runs, key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[0] if item.runs else None) for item in submissions]


@app.get("/api/submissions/{submission_id}")
def get_submission(submission_id: str, _host: dict = Depends(require_host), db: Session = Depends(get_db)):
    submission = db.query(Submission).options(selectinload(Submission.runs)).filter(Submission.id == submission_id, Submission.host_account_id == _host.get("account_id")).first()
    if not submission:
        raise HTTPException(404, "Submission not found")
    latest = sorted(submission.runs, key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[0] if submission.runs else None
    return submission_view(submission, latest)


@app.get("/api/submissions/{submission_id}/source-pdf")
def get_source_pdf(submission_id: str, _host: dict = Depends(require_host), db: Session = Depends(get_db)):
    submission = db.query(Submission).filter(Submission.id == submission_id, Submission.host_account_id == _host.get("account_id")).first()
    if not submission or not submission.source_pdf_file:
        raise HTTPException(404, "Source PDF not found")
    path = (settings.evidence_dir / "submissions" / submission_id / submission.source_pdf_file).resolve()
    if path.parent != (settings.evidence_dir / "submissions" / submission_id).resolve() or not path.is_file():
        raise HTTPException(404, "Source PDF not found")
    return FileResponse(path, media_type="application/pdf", filename="participant-details.pdf")


@app.post("/api/submissions/{submission_id}/judge", status_code=202)
def start_judging(submission_id: str, _host: dict = Depends(require_host), db: Session = Depends(get_db)):
    submission = db.query(Submission).filter(Submission.id == submission_id, Submission.host_account_id == _host.get("account_id")).first()
    if not submission:
        raise HTTPException(404, "Submission not found")
    active = db.query(JudgeRun).filter(JudgeRun.submission_id == submission_id, JudgeRun.status.in_(["queued", "running"])).order_by(JudgeRun.created_at.desc()).first()
    if active:
        now = datetime.now(timezone.utc)
        reference_time = (active.queued_at if active.status == "queued" else active.started_at) or active.created_at
        if reference_time:
            if reference_time.tzinfo is None:
                reference_time = reference_time.replace(tzinfo=timezone.utc)
            age_seconds = (now - reference_time).total_seconds()
        else:
            age_seconds = 0
        retry_window = settings.judge_queue_retry_after_seconds if active.status == "queued" else settings.judge_stale_after_seconds
        if age_seconds < retry_window:
            if active.status == "queued":
                raise HTTPException(409, "This project is waiting for a judge worker. The system automatically retries after five minutes.")
            raise HTTPException(409, "This evaluation is still active. Re-evaluation becomes available after 15 minutes without completion.")
        active.status = "failed"
        active.phase = "Timed out; re-evaluation requested"
        active.error_message = "This run did not finish within the retry window. A new evaluation was requested."
        active.completed_at = now
        db.commit()
    run = JudgeRun(submission_id=submission_id, status="queued", phase="Waiting for judge worker", progress=0, observations=[], evidence=[], review_flags=[])
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        evaluate_submission.delay(run.id)
    except Exception as exc:
        run.status = "failed"
        run.phase = "Queue unavailable"
        run.error_message = "The job queue is unavailable. Start Redis and the Celery worker, then retry."
        db.commit()
        raise HTTPException(503, run.error_message) from exc
    return run_view(run)


@app.get("/api/judge/status")
def judge_configuration_status(_host: dict = Depends(require_host)):
    provider = settings.llm_provider.lower()
    supported = provider in {"openai", "openai-compatible", "google", "gemini"}
    configured = bool(settings.llm_api_key.strip())
    return {"provider": provider, "model": settings.llm_model, "key_configured": configured, "ai_assessment_configured": supported and configured}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, _host: dict = Depends(require_host), db: Session = Depends(get_db)):
    run = db.query(JudgeRun).join(Submission).filter(JudgeRun.id == run_id, Submission.host_account_id == _host.get("account_id")).first()
    if not run:
        raise HTTPException(404, "Judge run not found")
    return run_view(run)


@app.get("/api/runs/{run_id}/evidence/{filename}")
def get_evidence(run_id: str, filename: str, _host: dict = Depends(require_host), db: Session = Depends(get_db)):
    run = db.query(JudgeRun).join(Submission).filter(JudgeRun.id == run_id, Submission.host_account_id == _host.get("account_id")).first()
    if not run or not any(Path(item.get("path", "")).name == filename for item in (run.evidence or [])):
        raise HTTPException(404, "Evidence not found")
    path = (settings.evidence_dir / run_id / filename).resolve()
    if path.parent != (settings.evidence_dir / run_id).resolve() or not path.is_file():
        raise HTTPException(404, "Evidence not found")
    media = "image/png" if path.suffix.lower() == ".png" else "text/plain; charset=utf-8"
    return FileResponse(path, media_type=media, filename=filename)


@app.get("/api/leaderboard")
def leaderboard(_host: dict = Depends(require_host), db: Session = Depends(get_db)):
    runs = db.query(JudgeRun).join(Submission).filter(JudgeRun.status == "completed", Submission.host_account_id == _host.get("account_id")).order_by(JudgeRun.completed_at.desc()).all()
    latest_by_submission = {}
    for run in runs:
        if run.submission_id in latest_by_submission:
            continue
        if not run.report or run.report.get("score_status") != "automated":
            continue
        submission = db.get(Submission, run.submission_id)
        if not submission:
            continue
        latest_by_submission[run.submission_id] = {"submission_id": submission.id, "application_number": submission.application_number, "project_name": submission.project_name, "participant_names": submission.participant_names, "total_score": run.total_score, "confidence": run.confidence, "needs_review": bool(run.review_flags), "run_id": run.id, "completed_at": run.completed_at}
    ranked = sorted(latest_by_submission.values(), key=lambda item: (-(item["total_score"] or 0), item["completed_at"].isoformat() if item["completed_at"] else "9999"))
    return [{"rank": index + 1, **{key: value for key, value in item.items() if key != "completed_at"}} for index, item in enumerate(ranked)]
