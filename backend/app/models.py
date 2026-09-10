"""SQLAlchemy persistence models.

Tables:
  problems    - seeded LLD problems
  attempts    - learner attempt with explicit status state machine
  submissions - structured solution payload (one per attempt)
  evaluations - merged deterministic + AI feedback (one per attempt)
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _now():
    return datetime.now(timezone.utc)


class ProblemModel(Base):
    __tablename__ = "problems"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, default="Intermediate")
    requirements: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    constraints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluation_criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_concepts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=45)


class AttemptModel(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    problem_id: Mapped[str] = mapped_column(String(64), ForeignKey("problems.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class SubmissionModel(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(64), ForeignKey("attempts.id"), nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, default="structured_text")
    assumptions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    class_definitions: Mapped[str] = mapped_column("class_definitions", Text, nullable=False, default="")
    relationships: Mapped[str] = mapped_column(Text, nullable=False, default="")
    behaviors: Mapped[str] = mapped_column(Text, nullable=False, default="")
    design_decisions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tradeoffs: Mapped[str] = mapped_column(Text, nullable=False, default="")
    edge_cases: Mapped[str] = mapped_column("edge_cases", Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class EvaluationModel(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(64), ForeignKey("attempts.id"), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="EVALUATING", index=True)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="heuristic")
    criterion_results: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    strengths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    improvements: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    next_questions: Mapped[list] = mapped_column("next_questions", JSON, nullable=False, default=list)
    deterministic: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
