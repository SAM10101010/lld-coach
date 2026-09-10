"""Application services: attempt lifecycle + evaluation orchestration.

Routes stay thin. All state transitions go through the state machine, the
submission is always persisted BEFORE evaluation starts, and duplicate
submit/evaluate requests are handled idempotently.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import config as cfg
from ..domain.evaluator import EvaluationResult, EvaluatorError, LLMEvaluator, RuleBasedEvaluator
from ..domain.state_machine import (
    COMPLETED,
    DRAFT,
    EVALUATING,
    FAILED,
    SUBMITTED,
    InvalidTransitionError,
    require_transition,
)
from ..domain.submission import submission_from_dict
from ..models import AttemptModel, EvaluationModel, ProblemModel, SubmissionModel


def _utcnow():
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def problem_to_dict(p: ProblemModel) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "requirements": list(p.requirements or []),
        "constraints": list(p.constraints or []),
        "required_concepts": list(p.required_concepts or []),
    }


# -- Attempt lifecycle -----------------------------------------------------

def start_attempt(db: Session, problem_id: str) -> AttemptModel:
    problem = db.get(ProblemModel, problem_id)
    if problem is None:
        raise KeyError(f"Unknown problem: {problem_id}")
    attempt = AttemptModel(id=_new_id("att"), problem_id=problem_id, status=DRAFT)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def save_draft(db: Session, attempt_id: str, payload: dict, sub_type: str = "structured_text") -> SubmissionModel:
    attempt = db.get(AttemptModel, attempt_id)
    if attempt is None:
        raise KeyError(f"Unknown attempt: {attempt_id}")
    if attempt.status not in (DRAFT, FAILED):
        raise InvalidTransitionError(f"Cannot edit attempt in status {attempt.status}. Create a new attempt to try again.")
    submission_from_dict(payload, sub_type)  # validates type early; content may be partial for drafts
    existing = db.query(SubmissionModel).filter(SubmissionModel.attempt_id == attempt_id).one_or_none()
    if existing is None:
        existing = SubmissionModel(id=_new_id("sub"), attempt_id=attempt_id, type="structured_text")
        db.add(existing)
    norm = submission_from_dict(payload, sub_type).sections()
    existing.type = "structured_text"
    existing.assumptions = norm.get("assumptions", "") or ""
    existing.class_definitions = norm.get("class_definitions", "") or ""
    existing.relationships = norm.get("relationships", "") or ""
    existing.behaviors = norm.get("behaviors", "") or ""
    existing.design_decisions = norm.get("design_decisions", "") or ""
    existing.tradeoffs = norm.get("tradeoffs", "") or ""
    existing.edge_cases = norm.get("edge_cases", "") or ""
    db.commit()
    db.refresh(existing)
    return existing


def retry_practice(db: Session, attempt_id: str) -> AttemptModel:
    """Try Again: new attempt for the same problem; old attempt stays immutable."""
    old = db.get(AttemptModel, attempt_id)
    if old is None:
        raise KeyError(f"Unknown attempt: {attempt_id}")
    return start_attempt(db, old.problem_id)


# -- Evaluation orchestration ----------------------------------------------

def _submission_payload(sub: SubmissionModel) -> dict:
    return {
        "assumptions": sub.assumptions or "",
        "class_definitions": sub.class_definitions or "",
        "relationships": sub.relationships or "",
        "behaviors": sub.behaviors or "",
        "design_decisions": sub.design_decisions or "",
        "tradeoffs": sub.tradeoffs or "",
        "edge_cases": sub.edge_cases or "",
    }


def _store_completed(db: Session, attempt: AttemptModel, result: EvaluationResult) -> EvaluationModel:
    existing = db.query(EvaluationModel).filter(EvaluationModel.attempt_id == attempt.id).one_or_none()
    if existing is None:
        existing = EvaluationModel(id=_new_id("eval"), attempt_id=attempt.id)
        db.add(existing)
    existing.status = COMPLETED
    existing.overall_score = int(result.overall_score)
    existing.provider = result.provider
    existing.criterion_results = [
        {
            "name": c.name, "score": c.score, "max_score": c.max_score,
            "evidence": c.evidence, "concern": c.concern,
            "suggestion": c.suggestion, "confidence": c.confidence,
        }
        for c in result.criteria
    ]
    existing.strengths = list(result.strengths or [])
    existing.improvements = list(result.improvements or [])
    existing.next_questions = list(result.next_questions or [])
    existing.deterministic = dict(result.deterministic or {})
    existing.error = None
    db.commit()
    db.refresh(existing)
    return existing


def _store_failed(db: Session, attempt: AttemptModel, det: dict, message: str) -> EvaluationModel:
    existing = db.query(EvaluationModel).filter(EvaluationModel.attempt_id == attempt.id).one_or_none()
    if existing is None:
        existing = EvaluationModel(id=_new_id("eval"), attempt_id=attempt.id)
        db.add(existing)
    existing.status = FAILED
    existing.overall_score = None
    existing.provider = "rule+llm"
    existing.criterion_results = []
    existing.strengths = []
    existing.improvements = []
    existing.next_questions = []
    existing.deterministic = dict(det or {})
    existing.error = message[:2000]
    db.commit()
    db.refresh(existing)
    return existing


def _resolve_llm() -> LLMEvaluator:
    """Pick the effective LLM backend at call time (respects env/test overrides).

    AI_PROVIDER=auto (default): OpenRouter if OPENROUTER_API_KEY is set,
    else OpenAI if OPENAI_API_KEY is set, else heuristic fallback (no key).
    Explicit AI_PROVIDER=openai|openrouter|heuristic overrides auto.
    """
    provider = (cfg.AI_PROVIDER or "auto").lower()
    if provider == "auto":
        if cfg.OPENROUTER_API_KEY:
            provider = "openrouter"
        elif cfg.OPENAI_API_KEY:
            provider = "openai"
        else:
            provider = "heuristic"
    if provider == "openrouter":
        return LLMEvaluator(
            model=cfg.AI_MODEL,
            api_key=cfg.OPENROUTER_API_KEY,
            timeout_s=cfg.AI_TIMEOUT_SECONDS,
            base_url=cfg.OPENROUTER_BASE_URL,
            provider="openrouter",
            extra_headers={
                "HTTP-Referer": "http://127.0.0.1:8000/",
                "X-Title": "LLD Coach",
            },
        )
    if provider == "heuristic":
        return LLMEvaluator(model=cfg.AI_MODEL, api_key="", timeout_s=cfg.AI_TIMEOUT_SECONDS)
    return LLMEvaluator(model=cfg.AI_MODEL, api_key=cfg.OPENAI_API_KEY, timeout_s=cfg.AI_TIMEOUT_SECONDS)


def _run_evaluators(problem_dict: dict, submission_obj) -> EvaluationResult:
    rule = RuleBasedEvaluator()
    det_result = rule.evaluate(problem_dict, submission_obj)
    llm = _resolve_llm()
    judged = llm.evaluate(problem_dict, submission_obj)
    # judged already merges deterministic caps; keep the deterministic detail attached
    judged.deterministic = det_result.deterministic
    return judged


def submit_and_evaluate(db: Session, attempt_id: str, payload: dict) -> tuple[AttemptModel, EvaluationModel | None]:
    attempt = db.get(AttemptModel, attempt_id)
    if attempt is None:
        raise KeyError(f"Unknown attempt: {attempt_id}")

    # Idempotency: duplicate submit while already evaluating/completed returns current state.
    if attempt.status == EVALUATING:
        ev = db.query(EvaluationModel).filter(EvaluationModel.attempt_id == attempt_id).one_or_none()
        return attempt, ev
    if attempt.status == COMPLETED:
        ev = db.query(EvaluationModel).filter(EvaluationModel.attempt_id == attempt_id).one_or_none()
        return attempt, ev
    if attempt.status not in (DRAFT, FAILED, SUBMITTED):
        raise InvalidTransitionError(f"Cannot submit attempt in status {attempt.status}")

    problem = db.get(ProblemModel, attempt.problem_id)
    if problem is None:
        raise KeyError(f"Problem not found: {attempt.problem_id}")
    problem_dict = problem_to_dict(problem)

    # 1. Build + validate submission (strict on submit; drafts may be partial).
    try:
        submission_obj = submission_from_dict(payload)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    errors = submission_obj.validate()
    if errors:
        raise ValueError("Submission invalid: " + " | ".join(errors))

    # 2. Persist submission FIRST so it is never lost if evaluation fails.
    save_draft(db, attempt_id, payload)
    db.refresh(attempt)

    # 3. SUBMITTED -> EVALUATING with a commit at each step so a refresh
    #    during a slow AI call still shows honest state and retry works.
    if attempt.status == DRAFT:
        require_transition(attempt.status, SUBMITTED)
        attempt.status = SUBMITTED
        attempt.submitted_at = _utcnow()
        db.commit()
    elif attempt.status == FAILED:
        attempt.submitted_at = _utcnow()
        db.commit()
    # SUBMITTED stays SUBMITTED if it came from a previous partial submit.

    require_transition(attempt.status, EVALUATING)
    attempt.status = EVALUATING
    db.commit()

    sub_row = db.query(SubmissionModel).filter(SubmissionModel.attempt_id == attempt_id).one()

    # 4. Run evaluators. Any EvaluatorError -> FAILED, submission preserved.
    try:
        result = _run_evaluators(problem_dict, submission_obj)
    except EvaluatorError as exc:
        attempt.status = FAILED
        db.commit()
        det_only = RuleBasedEvaluator().evaluate(problem_dict, submission_obj).deterministic
        ev = _store_failed(db, attempt, det_only, str(exc))
        return attempt, ev
    except Exception as exc:  # defensive: never corrupt data on unexpected error
        attempt.status = FAILED
        db.commit()
        det_only = RuleBasedEvaluator().evaluate(problem_dict, submission_obj).deterministic
        ev = _store_failed(db, attempt, det_only, f"Evaluation failed: {exc}")
        return attempt, ev

    # 5. Success -> COMPLETED
    require_transition(attempt.status, COMPLETED)
    attempt.status = COMPLETED
    db.commit()
    ev = _store_completed(db, attempt, result)
    db.refresh(attempt)
    return attempt, ev


def retry_evaluation(db: Session, attempt_id: str) -> tuple[AttemptModel, EvaluationModel | None]:
    attempt = db.get(AttemptModel, attempt_id)
    if attempt is None:
        raise KeyError(f"Unknown attempt: {attempt_id}")
    if attempt.status != FAILED:
        # Idempotent no-op for completed/evaluating; error for drafts that were never evaluated.
        if attempt.status in (COMPLETED, EVALUATING):
            ev = db.query(EvaluationModel).filter(EvaluationModel.attempt_id == attempt_id).one_or_none()
            return attempt, ev
        raise InvalidTransitionError(f"Only FAILED evaluations can be retried (status={attempt.status})")
    require_transition(attempt.status, EVALUATING)
    attempt.status = EVALUATING
    db.commit()

    problem = db.get(ProblemModel, attempt.problem_id)
    sub_row = db.query(SubmissionModel).filter(SubmissionModel.attempt_id == attempt_id).one_or_none()
    if problem is None or sub_row is None:
        attempt.status = FAILED
        db.commit()
        ev = _store_failed(db, attempt, {}, "Cannot retry: submission or problem missing.")
        return attempt, ev

    payload = _submission_payload(sub_row)
    submission_obj = submission_from_dict(payload)
    try:
        result = _run_evaluators(problem_to_dict(problem), submission_obj)
    except EvaluatorError as exc:
        attempt.status = FAILED
        db.commit()
        det_only = RuleBasedEvaluator().evaluate(problem_to_dict(problem), submission_obj).deterministic
        ev = _store_failed(db, attempt, det_only, str(exc))
        return attempt, ev

    require_transition(attempt.status, COMPLETED)
    attempt.status = COMPLETED
    db.commit()
    ev = _store_completed(db, attempt, result)
    db.refresh(attempt)
    return attempt, ev
