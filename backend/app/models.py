from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    host_account_id: Mapped[str | None] = mapped_column(String(36), index=True)
    application_number: Mapped[str | None] = mapped_column(String(80))
    project_name: Mapped[str] = mapped_column(String(160), nullable=False)
    # Legacy columns remain nullable so existing local databases upgrade in place.
    team_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    participant_names: Mapped[list] = mapped_column(JSON, nullable=False)
    deployed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(80), nullable=True)
    open_innovation_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    solution_description: Mapped[str] = mapped_column(Text, nullable=False)
    core_features: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_pdf_file: Mapped[str | None] = mapped_column(String(255))
    source_pdf_text: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str | None] = mapped_column(String(2048))
    credentials_ciphertext: Mapped[str | None] = mapped_column(Text)
    documentation_url: Mapped[str | None] = mapped_column(String(2048))
    ai_tools_metadata: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    runs: Mapped[list["JudgeRun"]] = relationship(back_populates="submission", cascade="all, delete-orphan")


class GoogleAccount(Base):
    __tablename__ = "google_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    application_number: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class ParticipantRegistration(Base):
    __tablename__ = "participant_registrations"

    application_number: Mapped[str] = mapped_column(String(80), primary_key=True)
    host_account_id: Mapped[str | None] = mapped_column(String(36), index=True)
    participant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(80), nullable=True)
    college_name: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class RegistrationPdfUpload(Base):
    __tablename__ = "registration_pdf_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    host_account_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    participant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class JudgeRun(Base):
    __tablename__ = "judge_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    phase: Mapped[str] = mapped_column(String(80), default="Queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[int | None] = mapped_column(Integer)
    report: Mapped[dict | None] = mapped_column(JSON)
    observations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    review_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission: Mapped[Submission] = relationship(back_populates="runs")
