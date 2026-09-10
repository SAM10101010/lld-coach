"""Core domain + API behavior tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.domain import state_machine as sm  # noqa: E402
from app.domain.evaluator import (  # noqa: E402
    EvaluatorError,
    HeuristicEvaluator,
    LLMEvaluator,
    RuleBasedEvaluator,
)
from app.domain.submission import submission_from_dict  # noqa: E402
from tests.conftest import GOOD_PARKING  # noqa: E402


def _problem():
    return {
        "id": "parking-lot",
        "title": "Parking Lot",
        "description": "multi floor parking",
        "requirements": ["multiple floors", "vehicle entry and ticket", "fee calculation"],
        "constraints": [],
        "required_concepts": [
            {"concept": "spot allocation", "keywords": ["spot", "allocat"]},
            {"concept": "ticket", "keywords": ["ticket"]},
            {"concept": "pricing strategy", "keywords": ["pric", "fee"]},
        ],
    }


def test_state_machine_valid_and_invalid():
    assert sm.can_transition("DRAFT", "SUBMITTED")
    assert sm.can_transition("SUBMITTED", "EVALUATING")
    assert sm.can_transition("EVALUATING", "COMPLETED")
    assert sm.can_transition("EVALUATING", "FAILED")
    assert sm.can_transition("FAILED", "EVALUATING")
    assert not sm.can_transition("DRAFT", "COMPLETED")
    assert not sm.can_transition("COMPLETED", "EVALUATING")
    try:
        sm.require_transition("DRAFT", "COMPLETED")
        raise AssertionError("should have raised")
    except sm.InvalidTransitionError:
        pass


def test_submission_validation_requires_sections():
    sub = submission_from_dict({k: "" for k in [
        "assumptions", "class_definitions", "relationships", "behaviors",
        "design_decisions", "tradeoffs", "edge_cases"]})
    errors = sub.validate()
    assert len(errors) == 7
    good = submission_from_dict(GOOD_PARKING)
    assert good.validate() == []
    assert good.get_type() == "structured_text"


def test_rule_evaluator_detects_missing_concepts():
    thin = submission_from_dict({**GOOD_PARKING, "assumptions": "hello world this is long enough text here",
                                 "class_definitions": "hello world this is long enough text here",
                                 "relationships": "hello world this is long enough text here",
                                 "behaviors": "hello world this is long enough text here",
                                 "design_decisions": "hello world this is long enough text here",
                                 "tradeoffs": "hello world this is long enough text here",
                                 "edge_cases": "hello world this is long enough text here"})
    res = RuleBasedEvaluator().evaluate(_problem(), thin)
    assert res.provider == "rule"
    assert res.deterministic["missing_concepts"], "should flag missing ticket/pricing concepts"
    assert res.deterministic["score"] < 60


def test_heuristic_produces_rubric_shaped_feedback():
    sub = submission_from_dict(GOOD_PARKING)
    res = HeuristicEvaluator().evaluate(_problem(), sub)
    assert 0 <= res.overall_score <= 100
    assert len(res.criteria) == 7
    assert sum(c.max_score for c in res.criteria) == 100
    for c in res.criteria:
        assert c.evidence and c.suggestion, f"{c.name} must carry evidence + suggestion"
        assert 0.0 <= c.confidence <= 1.0
    assert res.strengths and res.improvements and res.next_questions


def test_llm_parse_rejects_unknown_criterion():
    sub = submission_from_dict(GOOD_PARKING)
    ev = LLMEvaluator(api_key="dummy")
    bad = {"overallScore": 80, "criteria": [{"name": "Nonsense", "score": 5, "evidence": "x", "concern": "y", "suggestion": "z", "confidence": 0.5}],
           "strengths": [], "improvements": [], "nextQuestions": []}
    try:
        ev.parse(bad, _problem(), sub)
        raise AssertionError("should reject unknown criterion")
    except EvaluatorError:
        pass


def test_llm_parse_rejects_out_of_range_score():
    sub = submission_from_dict(GOOD_PARKING)
    ev = LLMEvaluator(api_key="dummy")
    bad = {"overallScore": 200, "criteria": [{"name": "Responsibilities", "score": 99, "evidence": "x", "concern": "y", "suggestion": "z", "confidence": 0.5}],
           "strengths": [], "improvements": [], "nextQuestions": []}
    try:
        ev.parse(bad, _problem(), sub)
        raise AssertionError("should reject out-of-range score")
    except EvaluatorError:
        pass
