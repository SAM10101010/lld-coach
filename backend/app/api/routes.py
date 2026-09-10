"""Problem + attempt + evaluation HTTP API. Routes are thin; services own behavior."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..application import services
from ..database import get_db
from ..domain.state_machine import InvalidTransitionError
from ..models import AttemptModel, EvaluationModel, ProblemModel, SubmissionModel
from ..schemas import AttemptOut, EvaluationOut, ProblemOut, SubmissionIn

router = APIRouter(prefix="/api")


def _problem_out(p: ProblemModel) -> dict:
    return {
        "id": p.id, "title": p.title, "description": p.description,
        "difficulty": p.difficulty, "requirements": list(p.requirements or []),
        "constraints": list(p.constraints or []),
        "evaluation_criteria": list(p.evaluation_criteria or []),
        "required_concepts": list(p.required_concepts or []),
        "estimated_minutes": p.estimated_minutes,
    }


def _attempt_out(db: Session, a: AttemptModel) -> dict:
    sub = db.query(SubmissionModel).filter(SubmissionModel.attempt_id == a.id).one_or_none()
    ev = db.query(EvaluationModel).filter(EvaluationModel.attempt_id == a.id).one_or_none()
    return {
        "id": a.id, "problem_id": a.problem_id, "status": a.status,
        "created_at": a.created_at, "submitted_at": a.submitted_at,
        "submission": ({
            "id": sub.id, "attempt_id": sub.attempt_id, "type": sub.type,
            "assumptions": sub.assumptions, "class_definitions": sub.class_definitions,
            "relationships": sub.relationships, "behaviors": sub.behaviors,
            "design_decisions": sub.design_decisions, "tradeoffs": sub.tradeoffs,
            "edge_cases": sub.edge_cases,
        } if sub else None),
        "evaluation": ({
            "id": ev.id, "attempt_id": ev.attempt_id, "status": ev.status,
            "overall_score": ev.overall_score, "provider": ev.provider,
            "criterion_results": list(ev.criterion_results or []),
            "strengths": list(ev.strengths or []),
            "improvements": list(ev.improvements or []),
            "next_questions": list(ev.next_questions or []),
            "deterministic": dict(ev.deterministic or {}),
            "error": ev.error, "created_at": ev.created_at,
        } if ev else None),
    }


@router.get("/problems", response_model=list[ProblemOut])
def list_problems(db: Session = Depends(get_db)):
    return [_problem_out(p) for p in db.query(ProblemModel).order_by(ProblemModel.id).all()]


@router.get("/problems/{problem_id}", response_model=ProblemOut)
def get_problem(problem_id: str, db: Session = Depends(get_db)):
    p = db.get(ProblemModel, problem_id)
    if p is None:
        raise HTTPException(404, f"Unknown problem: {problem_id}")
    return _problem_out(p)


@router.post("/problems/{problem_id}/attempts", response_model=AttemptOut)
def create_attempt(problem_id: str, db: Session = Depends(get_db)):
    try:
        a = services.start_attempt(db, problem_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _attempt_out(db, a)


@router.get("/attempts", response_model=list[AttemptOut])
def list_attempts(problem_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(AttemptModel).order_by(AttemptModel.created_at.desc())
    if problem_id:
        q = q.filter(AttemptModel.problem_id == problem_id)
    return [_attempt_out(db, a) for a in q.limit(100).all()]


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
def get_attempt(attempt_id: str, db: Session = Depends(get_db)):
    a = db.get(AttemptModel, attempt_id)
    if a is None:
        raise HTTPException(404, f"Unknown attempt: {attempt_id}")
    return _attempt_out(db, a)


@router.put("/attempts/{attempt_id}", response_model=AttemptOut)
def put_draft(attempt_id: str, body: SubmissionIn, db: Session = Depends(get_db)):
    try:
        services.save_draft(db, attempt_id, body.model_dump(by_alias=False))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    a = db.get(AttemptModel, attempt_id)
    return _attempt_out(db, a)


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptOut)
def submit_attempt(attempt_id: str, body: SubmissionIn, db: Session = Depends(get_db)):
    try:
        attempt, _ = services.submit_and_evaluate(db, attempt_id, body.model_dump(by_alias=False))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _attempt_out(db, attempt)


@router.get("/attempts/{attempt_id}/evaluation", response_model=EvaluationOut | None)
def get_evaluation(attempt_id: str, db: Session = Depends(get_db)):
    a = db.get(AttemptModel, attempt_id)
    if a is None:
        raise HTTPException(404, f"Unknown attempt: {attempt_id}")
    ev = db.query(EvaluationModel).filter(EvaluationModel.attempt_id == attempt_id).one_or_none()
    if ev is None:
        raise HTTPException(404, "No evaluation yet for this attempt")
    return {
        "id": ev.id, "attempt_id": ev.attempt_id, "status": ev.status,
        "overall_score": ev.overall_score, "provider": ev.provider,
        "criterion_results": list(ev.criterion_results or []),
        "strengths": list(ev.strengths or []),
        "improvements": list(ev.improvements or []),
        "next_questions": list(ev.next_questions or []),
        "deterministic": dict(ev.deterministic or {}),
        "error": ev.error, "created_at": ev.created_at,
    }


@router.post("/attempts/{attempt_id}/retry-evaluation", response_model=AttemptOut)
def retry_evaluation(attempt_id: str, db: Session = Depends(get_db)):
    try:
        attempt, _ = services.retry_evaluation(db, attempt_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _attempt_out(db, attempt)


@router.post("/attempts/{attempt_id}/retry", response_model=AttemptOut)
def retry_practice(attempt_id: str, db: Session = Depends(get_db)):
    try:
        a = services.retry_practice(db, attempt_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _attempt_out(db, a)
