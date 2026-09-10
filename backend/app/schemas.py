"""Pydantic request/response schemas. API routes stay thin; logic lives in domain/application."""
from datetime import datetime

from pydantic import BaseModel, Field


class ProblemOut(BaseModel):
    id: str
    title: str
    description: str
    difficulty: str
    requirements: list[str]
    constraints: list[str]
    evaluation_criteria: list[dict]
    required_concepts: list[dict]
    estimated_minutes: int


class SubmissionIn(BaseModel):
    assumptions: str = ""
    class_definitions: str = Field(default="", alias="classDefinitions")
    relationships: str = ""
    behaviors: str = ""
    design_decisions: str = Field(default="", alias="designDecisions")
    tradeoffs: str = ""
    edge_cases: str = Field(default="", alias="edgeCases")

    model_config = {"populate_by_name": True}


class SubmissionOut(BaseModel):
    id: str
    attempt_id: str
    type: str
    assumptions: str
    class_definitions: str
    relationships: str
    behaviors: str
    design_decisions: str
    tradeoffs: str
    edge_cases: str

    model_config = {"from_attributes": True}


class EvaluationOut(BaseModel):
    id: str
    attempt_id: str
    status: str
    overall_score: int | None
    provider: str
    criterion_results: list[dict]
    strengths: list[str]
    improvements: list[dict] | list[str]
    next_questions: list[str]
    deterministic: dict
    error: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AttemptOut(BaseModel):
    id: str
    problem_id: str
    status: str
    created_at: datetime | None = None
    submitted_at: datetime | None = None
    submission: SubmissionOut | None = None
    evaluation: EvaluationOut | None = None

    model_config = {"from_attributes": True}
